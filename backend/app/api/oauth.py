"""OAuth sign-in for AI assistants (services/oauth/): the authorization server's endpoints, the
consent the panel asks the person for, and the connected apps they can see and revoke.

Only with MCP_OAUTH_ENABLED: off, every route here is a 404, as if it did not exist. The
protocol endpoints (authorize, token, register) are the MCP SDK's own handlers, mounted here so
they sit under the API next to /mcp; their metadata documents are relayed by the panel from the
issuer's /.well-known/ addresses (frontend/server/routes/.well-known/).
"""

import uuid
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request, Response
from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.handlers.metadata import MetadataHandler, ProtectedResourceMetadataHandler
from mcp.server.auth.handlers.register import RegistrationHandler
from mcp.server.auth.handlers.revoke import RevocationErrorResponse
from mcp.server.auth.handlers.token import TokenErrorResponse, TokenHandler
from mcp.server.auth.json_response import PydanticJSONResponse
from mcp.server.auth.middleware.client_auth import AuthenticationError, ClientAuthenticator
from mcp.server.auth.settings import ClientRegistrationOptions
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_company_user
from app.core.exceptions import ResourceNotFoundException
from app.models.tenant_user import TenantUser
from app.schemas.oauth import (
    MAX_CONSENT_REQUEST_CHARS,
    ConsentAnswer,
    ConsentDetails,
    ConsentRedirect,
    OAuthGrantResponse,
)
from app.services import audit
from app.services.oauth import (
    SCOPE,
    authorization_server_metadata,
    grants,
    is_this_resource,
    protected_resource_metadata,
)
from app.services.oauth.provider import (
    ReportAIProvider,
    approve,
    consent_client,
    deny,
    read_consent_request,
)


async def _enabled() -> None:
    if not settings.MCP_OAUTH_ENABLED:
        raise ResourceNotFoundException()


router = APIRouter(prefix="/oauth", tags=["oauth"], dependencies=[Depends(_enabled)])

_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.get("/metadata")
async def authorization_server(request: Request) -> Response:
    """RFC 8414, served by the panel at /.well-known/oauth-authorization-server."""
    return await MetadataHandler(authorization_server_metadata()).handle(request)


@router.get("/protected-resource")
async def protected_resource(request: Request) -> Response:
    """RFC 9728, served by the panel at /.well-known/oauth-protected-resource/…/mcp."""
    return await ProtectedResourceMetadataHandler(protected_resource_metadata()).handle(request)


@router.get("/authorize")
async def authorize(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """Sends the browser to the panel's consent page, or back to the app with an error."""
    return await AuthorizationHandler(ReportAIProvider(db)).handle(request)


@router.post("/authorize")
async def authorize_by_form(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """The same, with the parameters in a form (RFC 6749 §3.1 allows either)."""
    return await AuthorizationHandler(ReportAIProvider(db)).handle(request)


@router.post("/token")
async def token(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    # RFC 8707: a token asked for another server is refused here, before any code is spent. The
    # SDK reads `resource` but leaves this check to the server.
    resource = (await request.form()).get("resource")
    if isinstance(resource, str) and resource and not is_this_resource(resource):
        return PydanticJSONResponse(
            content=TokenErrorResponse(error="invalid_target", error_description="This server issues tokens for its own MCP server only"),
            status_code=400,
            headers=_NO_STORE,
        )
    provider = ReportAIProvider(db)
    response: Response = await TokenHandler(provider, ClientAuthenticator(provider)).handle(request)  # untyped in the SDK
    return response


@router.post("/register")
async def register(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """Dynamic Client Registration (RFC 7591), for clients without a metadata document."""
    ip = audit.client_ip(request)
    await rate_limit.oauth_register_by_ip.check(db, ip)
    await rate_limit.oauth_register_by_ip.record(db, ip)
    options = ClientRegistrationOptions(enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE])
    return await RegistrationHandler(ReportAIProvider(db), options).handle(request)


@router.post("/revoke")
async def revoke(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """RFC 7009: an app signing out. Not the SDK's RevocationHandler: it requires a client_secret
    field even from a public client, which has none, so every such app would get a 400."""
    provider = ReportAIProvider(db)
    try:
        client = await ClientAuthenticator(provider).authenticate_request(request)
    except AuthenticationError as exc:
        return PydanticJSONResponse(
            content=RevocationErrorResponse(error="unauthorized_client", error_description=exc.message), status_code=401
        )
    secret = (await request.form()).get("token")
    if not isinstance(secret, str) or not secret:
        return PydanticJSONResponse(content=RevocationErrorResponse(error="invalid_request", error_description="token is required"), status_code=400)
    found = await provider.load_access_token(secret) or await provider.load_refresh_token(client, secret)
    # Another app's token, or none at all: 200 all the same (RFC 7009 §2.2), and nothing revoked.
    if found is not None and found.client_id == client.client_id:
        await provider.revoke_token(found)
    return Response(status_code=200, headers=_NO_STORE)


@router.get("/consent")
async def consent_details(
    sealed: str = Query(alias="request", min_length=1, max_length=MAX_CONSENT_REQUEST_CHARS),
    current_user: TenantUser = Depends(require_company_user),
    db: AsyncSession = Depends(get_db),
) -> ConsentDetails:
    consent = read_consent_request(sealed)
    client = await consent_client(db, consent)
    return ConsentDetails(
        client_name=client.client_name or client.client_id,
        client_id=client.client_id,
        redirect_host=urlsplit(consent.redirect_uri).netloc,
        scopes=[SCOPE],
    )


@router.post("/consent")
async def answer_consent(
    body: ConsentAnswer,
    request: Request,
    current_user: TenantUser = Depends(require_company_user),
    db: AsyncSession = Depends(get_db),
) -> ConsentRedirect:
    consent = read_consent_request(body.request)
    client = await consent_client(db, consent)
    if body.approve:
        redirect_to = await approve(db, current_user, consent)
    else:
        redirect_to = deny(consent)
    await audit.record(
        db, "oauth.approved" if body.approve else "oauth.denied", actor=current_user, request=request,
        client_id=client.client_id, client_name=client.client_name, redirect_host=urlsplit(consent.redirect_uri).netloc,
    )
    await db.commit()
    return ConsentRedirect(redirect_to=redirect_to)


@router.get("/grants")
async def list_grants(
    current_user: TenantUser = Depends(require_company_user), db: AsyncSession = Depends(get_db)
) -> list[OAuthGrantResponse]:
    """The apps connected by signing in; also how the panel learns OAuth is on (a 404 when off)."""
    return [
        OAuthGrantResponse(
            id=grant.id, client_name=grants.client_name(client), owner_id=grant.user_id, owner_name=owner,
            created_at=grant.created_at, last_used_at=grant.last_used_at,
        )
        for grant, client, owner in await grants.visible_grants(db, current_user)
    ]


@router.delete("/grants/{grant_id}", status_code=204)
async def disconnect_app(
    grant_id: uuid.UUID,
    request: Request,
    current_user: TenantUser = Depends(require_company_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    grant = await grants.revocable_grant(db, current_user, grant_id)
    if grant.revoked_at is None:
        await grants.revoke_grant(db, grant.id)
        await audit.record(db, "oauth.revoked", actor=current_user, target=grant.id, request=request)
        await db.commit()
    return Response(status_code=204)
