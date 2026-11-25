"""The authorization server's state, behind the MCP SDK's own OAuth handlers: they parse the
requests and check PKCE, code expiry and redirect URIs; this decides who gets what.

The flow: /authorize sends the person to the panel's consent page with the request sealed in the
URL (nothing is stored until they answer). Approving makes a one-use code, bound to the app, the
person, the redirect URI and the PKCE challenge. The code buys a grant (the connection the panel
lists) with an access token (an hour) and a refresh token (30 days). A refresh token works once and
is replaced by a new pair; one presented again means two holders, so the whole grant ends.
"""

import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull
from mcp.shared.auth import OAuthToken as TokenResponse
from pydantic import AnyUrl
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import seal, unseal
from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.scoping import require_tenant_id
from app.models.oauth import OAuthClient, OAuthCode, OAuthGrant, OAuthToken
from app.models.tenant_user import TenantUser
from app.services.credentials import acting_person
from app.services.oauth import SCOPE, clients, is_this_resource, resource_url, token_hash
from app.services.oauth.grants import ACCESS_PREFIX, REFRESH_PREFIX, make_room_for, revoke_grant

logger = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=10)
CONSENT_TTL = timedelta(minutes=10)
ACCESS_TTL = timedelta(hours=1)
REFRESH_TTL = timedelta(days=30)
# Every sealed link shares one key, so a token sealed for something else must not pass for this.
_CONSENT_PURPOSE = "oauth_consent"
# RFC 7636 §4.2: an S256 challenge is base64url, 43 characters; 128 is the longest allowed.
_CODE_CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43,128}")
_MAX_SECRET_CHARS = 100


class StoredCode(AuthorizationCode):
    code_hash: str
    oauth_client_id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID


class StoredRefreshToken(RefreshToken):
    token_hash: str
    grant_id: uuid.UUID


class StoredAccessToken(AccessToken):
    grant_id: uuid.UUID


@dataclass(frozen=True)
class ConsentRequest:
    """An authorization request waiting for the person's answer, as the consent page carries it."""

    client_id: str
    redirect_uri: str
    redirect_uri_explicit: bool
    code_challenge: str
    resource: str
    state: str | None


def _secret() -> str:
    return secrets.token_urlsafe(32)  # 256 random bits


class ReportAIProvider(OAuthAuthorizationServerProvider[StoredCode, StoredRefreshToken, StoredAccessToken]):
    """What the SDK's handlers call, for one request: everything goes through its database session.
    `client_ip` is who sent the request, which a metadata document fetch is counted against."""

    def __init__(self, db: AsyncSession, *, client_ip: str) -> None:
        self.db = db
        self.client_ip = client_ip

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return await clients.get_client(self.db, client_id, client_ip=self.client_ip)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await clients.register(self.db, client_info)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        # The SDK has already checked the client and that the redirect URI is one of its own.
        if params.resource is not None and not is_this_resource(params.resource):
            raise AuthorizeError("invalid_target", "This server issues tokens for its own MCP server only")
        if params.scopes is not None and set(params.scopes) != {SCOPE}:
            raise AuthorizeError("invalid_scope", f"The only scope is {SCOPE}")
        if not _CODE_CHALLENGE.fullmatch(params.code_challenge):
            raise AuthorizeError("invalid_request", "code_challenge must be an S256 challenge")
        request = seal(
            {
                "purpose": _CONSENT_PURPOSE,
                "client_id": client.client_id,
                "redirect_uri": str(params.redirect_uri),
                "explicit": params.redirect_uri_provided_explicitly,
                "code_challenge": params.code_challenge,
                # Bound to this server even when the app didn't say: it is the only resource.
                "resource": resource_url(),
                "state": params.state,
            }
        )
        return construct_redirect_uri(f"{settings.FRONTEND_ORIGIN}/oauth/consent", request=request)

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> StoredCode | None:
        if len(authorization_code) > _MAX_SECRET_CHARS:
            return None
        found = (
            await self.db.execute(
                select(OAuthCode, OAuthClient.client_id)
                .join(OAuthClient, OAuthCode.oauth_client_id == OAuthClient.id)
                .where(OAuthCode.code_hash == token_hash(authorization_code))
            )
        ).first()
        if found is None or found.client_id != client.client_id:
            return None
        code: OAuthCode = found.OAuthCode
        return StoredCode(
            code=authorization_code,
            scopes=code.scope.split(),
            expires_at=code.expires_at.timestamp(),
            client_id=client.client_id,
            code_challenge=code.code_challenge,
            redirect_uri=AnyUrl(code.redirect_uri),
            redirect_uri_provided_explicitly=code.redirect_uri_explicit,
            resource=code.resource,
            subject=str(code.user_id),
            code_hash=code.code_hash,
            oauth_client_id=code.oauth_client_id,
            user_id=code.user_id,
            tenant_id=code.tenant_id,
        )

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: StoredCode) -> TokenResponse:
        # Deleted as it is read, in the transaction that makes the grant: of two exchanges at once,
        # the second waits on the row and then finds nothing.
        spent = await self.db.execute(
            delete(OAuthCode)
            .where(OAuthCode.code_hash == authorization_code.code_hash, OAuthCode.expires_at > func.now())
            .returning(OAuthCode.code_hash)
        )
        if spent.first() is None:
            raise TokenError("invalid_grant", "authorization code does not exist")
        if await acting_person(self.db, authorization_code.user_id, authorization_code.tenant_id) is None:
            await self.db.commit()  # the code stays spent
            raise TokenError("invalid_grant", "The person who approved this can no longer use ReportAI")
        grant = OAuthGrant(
            tenant_id=authorization_code.tenant_id,
            user_id=authorization_code.user_id,
            oauth_client_id=authorization_code.oauth_client_id,
            scope=" ".join(authorization_code.scopes),
            resource=authorization_code.resource or resource_url(),
        )
        self.db.add(grant)
        await self.db.flush()
        tokens = self._issue(grant.id)
        await self._client_used(grant.oauth_client_id)
        await self.db.commit()
        return tokens

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> StoredRefreshToken | None:
        """A refresh token of `client`'s live grant, spent or not: exchanging a spent one is what
        reveals a copy (exchange_refresh_token)."""
        if not refresh_token.startswith(REFRESH_PREFIX) or len(refresh_token) > _MAX_SECRET_CHARS:
            return None
        found = (
            await self.db.execute(
                select(OAuthToken, OAuthGrant, OAuthClient.client_id)
                .join(OAuthGrant, OAuthToken.grant_id == OAuthGrant.id)
                .join(OAuthClient, OAuthGrant.oauth_client_id == OAuthClient.id)
                .where(
                    OAuthToken.token_hash == token_hash(refresh_token),
                    OAuthToken.kind == "refresh",
                    OAuthGrant.revoked_at.is_(None),
                )
            )
        ).first()
        if found is None or found.client_id != client.client_id:
            return None
        token: OAuthToken = found.OAuthToken
        grant: OAuthGrant = found.OAuthGrant
        return StoredRefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=grant.scope.split(),
            expires_at=int(token.expires_at.timestamp()),
            resource=grant.resource,
            subject=str(grant.user_id),
            token_hash=token.token_hash,
            grant_id=grant.id,
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: StoredRefreshToken, scopes: list[str]
    ) -> TokenResponse:
        spent = await self.db.execute(
            update(OAuthToken)
            .where(OAuthToken.token_hash == refresh_token.token_hash, OAuthToken.used_at.is_(None))
            .values(used_at=func.now())
            .returning(OAuthToken.token_hash)
        )
        if spent.first() is None:
            # Spent already: whoever comes second holds a copy, and there is no telling which one is
            # the app (RFC 9700 §4.14.2). The grant ends for both; the person approves it again.
            await revoke_grant(self.db, refresh_token.grant_id)
            await self.db.commit()
            logger.warning("A spent refresh token was presented again: revoked OAuth grant %s", refresh_token.grant_id)
            raise TokenError("invalid_grant", "refresh token is no longer valid")
        grant = await self.db.get(OAuthGrant, refresh_token.grant_id)
        if grant is None or await acting_person(self.db, grant.user_id, grant.tenant_id) is None:
            await self.db.rollback()  # unspent: it works again if the person is let back in
            raise TokenError("invalid_grant", "The person who approved this can no longer use ReportAI")
        tokens = self._issue(grant.id)
        await self._client_used(grant.oauth_client_id)
        await self.db.commit()
        return tokens

    async def load_access_token(self, token: str) -> StoredAccessToken | None:
        if not token.startswith(ACCESS_PREFIX) or len(token) > _MAX_SECRET_CHARS:
            return None
        found = (
            await self.db.execute(
                select(OAuthToken, OAuthGrant, OAuthClient.client_id)
                .join(OAuthGrant, OAuthToken.grant_id == OAuthGrant.id)
                .join(OAuthClient, OAuthGrant.oauth_client_id == OAuthClient.id)
                .where(
                    OAuthToken.token_hash == token_hash(token),
                    OAuthToken.kind == "access",
                    OAuthToken.expires_at > func.now(),
                    OAuthGrant.revoked_at.is_(None),
                )
            )
        ).first()
        if found is None:
            return None
        grant: OAuthGrant = found.OAuthGrant
        return StoredAccessToken(
            token=token,
            client_id=found.client_id,
            scopes=grant.scope.split(),
            expires_at=int(found.OAuthToken.expires_at.timestamp()),
            resource=grant.resource,
            subject=str(grant.user_id),
            grant_id=grant.id,
        )

    async def revoke_token(self, token: StoredAccessToken | StoredRefreshToken) -> None:
        # Either token ends the whole grant: the app is signing out (RFC 7009 §2.1 allows it).
        await revoke_grant(self.db, token.grant_id)
        await self.db.commit()

    def _issue(self, grant_id: uuid.UUID) -> TokenResponse:
        access, refresh = ACCESS_PREFIX + _secret(), REFRESH_PREFIX + _secret()
        self.db.add_all(
            [
                OAuthToken(token_hash=token_hash(access), grant_id=grant_id, kind="access", expires_at=func.now() + ACCESS_TTL),
                OAuthToken(token_hash=token_hash(refresh), grant_id=grant_id, kind="refresh", expires_at=func.now() + REFRESH_TTL),
            ]
        )
        return TokenResponse(access_token=access, expires_in=int(ACCESS_TTL.total_seconds()), scope=SCOPE, refresh_token=refresh)

    async def _client_used(self, oauth_client_id: uuid.UUID) -> None:
        await self.db.execute(update(OAuthClient).where(OAuthClient.id == oauth_client_id).values(last_used_at=func.now()))


# ── The consent page ────────────────────────────────────────────────────────────────────────

_EXPIRED = "This sign-in request is wrong or has expired: start again from your AI assistant"


def read_consent_request(token: str) -> ConsentRequest:
    """The request the consent page carries; ValidationException (400) if it isn't one of ours or
    is more than 10 minutes old."""
    try:
        claims: dict[str, Any] = unseal(token, CONSENT_TTL)
    except ValueError as exc:
        raise ValidationException(_EXPIRED) from exc
    if claims.get("purpose") != _CONSENT_PURPOSE:
        raise ValidationException(_EXPIRED)
    return ConsentRequest(
        client_id=claims["client_id"],
        redirect_uri=claims["redirect_uri"],
        redirect_uri_explicit=claims["explicit"],
        code_challenge=claims["code_challenge"],
        resource=claims["resource"],
        state=claims["state"],
    )


async def consent_client(db: AsyncSession, request: ConsentRequest, *, client_ip: str) -> OAuthClientInformationFull:
    """The app asking, as it is now: 404 if it is gone, or no longer lists the redirect URI (its
    metadata document changed in the meantime). May commit (clients.get_client)."""
    client = await clients.get_client(db, request.client_id, client_ip=client_ip)
    if client is None or request.redirect_uri not in {str(uri) for uri in client.redirect_uris or []}:
        raise ResourceNotFoundException(_EXPIRED)
    return client


async def approve(db: AsyncSession, user: TenantUser, request: ConsentRequest, client: OAuthClientInformationFull) -> str:
    """Makes the code for `user`'s approval of `client`, as consent_client returned it (not
    committed), and returns where to send the browser. Ends the connection `user` had to it, if
    any; ConflictException (409) if they are connected to too many other apps."""
    tenant_id = require_tenant_id(user)
    oauth_client_id = await db.scalar(select(OAuthClient.id).where(OAuthClient.client_id == client.client_id))
    assert oauth_client_id is not None  # consent_client found it, and get_client stores what it fetches
    await make_room_for(db, user, oauth_client_id)
    code = _secret()
    db.add(
        OAuthCode(
            code_hash=token_hash(code),
            oauth_client_id=oauth_client_id,
            tenant_id=tenant_id,
            user_id=user.id,
            redirect_uri=request.redirect_uri,
            redirect_uri_explicit=request.redirect_uri_explicit,
            code_challenge=request.code_challenge,
            scope=SCOPE,
            resource=request.resource,
            expires_at=func.now() + CODE_TTL,
        )
    )
    return construct_redirect_uri(request.redirect_uri, code=code, state=request.state)


def deny(request: ConsentRequest) -> str:
    return construct_redirect_uri(request.redirect_uri, error="access_denied", state=request.state)
