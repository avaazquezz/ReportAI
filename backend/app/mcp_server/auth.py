"""Who is calling the MCP endpoint. Every request carries a bearer token: a personal API key
(services/api_keys.py, "rpt_…"), or, with MCP_OAUTH_ENABLED, the access token of an app the person
connected by signing in (services/oauth/). Its person is checked on every request, so a revoked
key or grant, a person switched off or a suspended company stop working at once, with nothing
cached in between.

Not the SDK's own auth (TokenVerifier + AuthSettings): it knows bearer tokens of one kind, and
here API keys must keep working exactly as they did, with or without OAuth. What OAuth adds to a
401 is where to sign in (RFC 9728's resource_metadata), which only exists while it is on.
"""

from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core import rate_limit
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import RateLimitException
from app.models.tenant_user import TenantUser
from app.services import api_keys
from app.services.credentials import Credential, Principal
from app.services.oauth import SCOPE, grants, resource_metadata_url

_principal: ContextVar[Principal | None] = ContextVar("mcp_principal", default=None)


def current_principal() -> Principal:
    """The caller of the tool running now. Only reachable through McpAuth, so a None is a bug."""
    principal = _principal.get()
    if principal is None:
        raise RuntimeError("An MCP tool ran outside an authenticated request")
    return principal


async def authenticate(db: AsyncSession, secret: str) -> Principal | None:
    if secret.startswith(api_keys.PREFIX):
        return await api_keys.authenticate(db, secret)
    if settings.MCP_OAUTH_ENABLED:
        return await grants.authenticate(db, secret)
    return None


async def person_of(db: AsyncSession, credential: Credential) -> TenantUser | None:
    """Who the credential acts as right now, or None once it is revoked or expired or its person
    may not act: what something an assistant got through it (a PDF link) is worth when used. An
    app's grant is worth nothing while OAuth is off, as at /mcp."""
    if credential.kind == "api_key":
        return await api_keys.person_of(db, credential.id)
    if settings.MCP_OAUTH_ENABLED:
        return await grants.person_of(db, credential.id)
    return None


def _bearer(scope: Scope) -> str | None:
    scheme, _, secret = Headers(scope=scope).get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return secret.strip() or None


def _unauthorized(*, presented: bool) -> JSONResponse:
    """The 401; `presented` when the request carried a bearer token, refused."""
    if not settings.MCP_OAUTH_ENABLED:
        return JSONResponse(
            {"detail": "Missing, unknown, revoked or expired ReportAI API key. Make one in ReportAI under API keys."},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="ReportAI"'},
        )
    # RFC 9728 §5.1: where a client learns how to sign in. RFC 6750 §3.1: a token that was refused
    # is named as such, so the client refreshes or signs in again instead of retrying it.
    refused = ', error="invalid_token"' if presented else ""
    challenge = f'Bearer realm="ReportAI"{refused}, resource_metadata="{resource_metadata_url()}", scope="{SCOPE}"'
    return JSONResponse(
        {"detail": "Missing, unknown, revoked or expired ReportAI credential. Sign in to ReportAI again, or use an API key."},
        status_code=401,
        headers={"WWW-Authenticate": challenge},
    )


class McpAuth:
    """ASGI middleware in front of the MCP app: 401 without a valid credential, 429 over its
    limit, otherwise the request runs with the caller in `current_principal()`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        secret = _bearer(scope)
        async with AsyncSessionLocal() as db:
            principal = await authenticate(db, secret) if secret else None
            if principal is not None:
                limiter = rate_limit.mcp_by_key if principal.credential.kind == "api_key" else rate_limit.mcp_by_grant
                try:
                    await limiter.check(db, str(principal.credential.id))
                except RateLimitException as exc:
                    await JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)(scope, receive, send)
                    return
                await limiter.record(db, str(principal.credential.id))
        if principal is None:
            await _unauthorized(presented=secret is not None)(scope, receive, send)
            return
        token = _principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            _principal.reset(token)
