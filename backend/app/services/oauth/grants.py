"""What a connected app's grant is worth: who an access token acts as on the MCP server, and the
connections the panel lists and revokes.

Like a personal API key, a grant is worth what its person is, checked on every request (the same
`acting_person` as keys): switch them off or suspend the company and their apps stop at once; let
them back in and the apps work again. Revoking a grant, from the panel, by the app signing out or
by "sign out everywhere", ends it for good.
"""

import logging
import uuid
from datetime import timedelta

from sqlalchemy import ColumnElement, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.core.scoping import get_scoped_or_404, require_tenant_id
from app.models.oauth import OAuthClient, OAuthGrant, OAuthToken
from app.models.tenant_user import TenantUser
from app.repositories.base import BaseRepository
from app.services.credentials import Credential, Principal, acting_person
from app.services.oauth import is_this_resource, resource_url, token_hash

logger = logging.getLogger(__name__)
# Not "rpt_", the API keys' prefix: /mcp tells the two kinds apart by it.
ACCESS_PREFIX = "rpo_"
REFRESH_PREFIX = "rpr_"
# last_used_at is a hint for the panel, as for keys: written at most this often.
_TOUCH_AFTER = timedelta(minutes=5)
_MAX_TOKEN_CHARS = 100
# As for API keys: a person rarely needs more, and a stolen session can't connect apps by the hundred.
MAX_CONNECTED_APPS_PER_USER = 10

# Not revoked, and holding a refresh token still good: what the panel shows as connected. A grant
# whose refresh token ran out can do nothing more, so it is listed no longer.
_CONNECTED: ColumnElement[bool] = OAuthGrant.revoked_at.is_(None) & exists().where(
    OAuthToken.grant_id == OAuthGrant.id,
    OAuthToken.kind == "refresh",
    OAuthToken.used_at.is_(None),
    OAuthToken.expires_at > func.now(),
)


async def authenticate(db: AsyncSession, token: str) -> Principal | None:
    """Who an access token acts as, or None: unknown, expired, of a revoked grant, issued for
    another server (RFC 8707), or of a person who may not act now. Commits when it records use."""
    if not token.startswith(ACCESS_PREFIX) or len(token) > _MAX_TOKEN_CHARS:
        return None
    grant = await db.scalar(
        select(OAuthGrant)
        .join(OAuthToken, OAuthToken.grant_id == OAuthGrant.id)
        .where(
            OAuthToken.token_hash == token_hash(token),
            OAuthToken.kind == "access",
            OAuthToken.expires_at > func.now(),
            OAuthGrant.revoked_at.is_(None),
        )
    )
    if grant is None:
        return None
    if not is_this_resource(grant.resource):
        logger.warning("OAuth grant %s is for %s, not this server's %s: its token refused", grant.id, grant.resource[:200], resource_url())
        return None
    user = await acting_person(db, grant.user_id, grant.tenant_id)
    if user is None:
        return None
    principal = Principal(credential=Credential("oauth", grant.id), user_id=user.id, tenant_id=grant.tenant_id)
    touched = await db.execute(
        update(OAuthGrant)
        .where(OAuthGrant.id == grant.id, OAuthGrant.last_used_at.is_(None) | (OAuthGrant.last_used_at < func.now() - _TOUCH_AFTER))
        .values(last_used_at=func.now())
    )
    if touched.rowcount:  # type: ignore[attr-defined]
        await db.commit()
    return principal


async def person_of(db: AsyncSession, grant_id: uuid.UUID) -> TenantUser | None:
    """Who the grant acts as right now, or None once it is revoked or its person may not act."""
    grant = await db.scalar(select(OAuthGrant).where(OAuthGrant.id == grant_id, OAuthGrant.revoked_at.is_(None)))
    return None if grant is None else await acting_person(db, grant.user_id, grant.tenant_id)


async def make_room_for(db: AsyncSession, user: TenantUser, oauth_client_id: uuid.UUID) -> None:
    """Gets `user` ready for a new grant to the app (not committed): ConflictException if they are
    connected to MAX_CONNECTED_APPS_PER_USER other apps already, else revokes what they hold for this
    one, since approving an app again replaces its connection: one per person and app."""
    others = await db.scalar(
        select(func.count()).select_from(OAuthGrant).where(OAuthGrant.user_id == user.id, OAuthGrant.oauth_client_id != oauth_client_id, _CONNECTED)
    )
    if (others or 0) >= MAX_CONNECTED_APPS_PER_USER:
        raise ConflictException(f"You already have {MAX_CONNECTED_APPS_PER_USER} connected apps: disconnect one you no longer use")
    await db.execute(
        update(OAuthGrant)
        .where(OAuthGrant.user_id == user.id, OAuthGrant.oauth_client_id == oauth_client_id, OAuthGrant.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )


async def revoke_grant(db: AsyncSession, grant_id: uuid.UUID) -> None:
    """Ends the grant and every token it holds (not committed); nothing if it already ended."""
    await db.execute(update(OAuthGrant).where(OAuthGrant.id == grant_id, OAuthGrant.revoked_at.is_(None)).values(revoked_at=func.now()))


async def revoke_all(db: AsyncSession, user: TenantUser) -> int:
    """Revokes every grant of `user` not yet revoked (not committed), and says how many."""
    result = await db.execute(
        update(OAuthGrant).where(OAuthGrant.user_id == user.id, OAuthGrant.revoked_at.is_(None)).values(revoked_at=func.now())
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


async def visible_grants(db: AsyncSession, user: TenantUser) -> list[tuple[OAuthGrant, OAuthClient, str]]:
    """The connected apps `user` may see, with the app and its person's name: a company admin sees
    the company's, as with keys; everyone else, their own."""
    query = (
        select(OAuthGrant, OAuthClient, TenantUser.full_name)
        .join(OAuthClient, OAuthGrant.oauth_client_id == OAuthClient.id)
        .join(TenantUser, OAuthGrant.user_id == TenantUser.id)
        .where(OAuthGrant.tenant_id == require_tenant_id(user), _CONNECTED)
        .order_by(OAuthGrant.created_at.desc())
    )
    if user.role != "tenant_admin":
        query = query.where(OAuthGrant.user_id == user.id)
    return [(grant, client, owner) for grant, client, owner in (await db.execute(query)).all()]


async def revocable_grant(db: AsyncSession, user: TenantUser, grant_id: uuid.UUID) -> OAuthGrant:
    """A grant `user` may revoke: their own, or any of the company's for its admin. Anything else
    is a 404, as if it did not exist."""
    grant = await get_scoped_or_404(BaseRepository(OAuthGrant, db), grant_id, tenant_id=require_tenant_id(user))
    if grant.user_id != user.id and user.role != "tenant_admin":
        raise ResourceNotFoundException()
    return grant


def client_name(client: OAuthClient) -> str:
    """What the app calls itself, as the consent page and the panel show it; or its address."""
    name = client.client_metadata.get("client_name")
    return name.strip() if isinstance(name, str) and name.strip() else client.client_id
