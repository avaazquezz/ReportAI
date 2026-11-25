"""Who is calling the MCP endpoint. Every request carries a personal API key as a bearer token
(services/api_keys.py); the key's person is checked on every request, so a revoked key, a person
switched off or a suspended company stop working at once, with nothing cached in between.

Not the SDK's own auth (TokenVerifier + AuthSettings): that makes the server an OAuth resource
server that publishes an authorization server, and there is none here. A client that read that
document would try to sign in through a server that doesn't exist instead of reporting a bad key.

# ponytail: API keys only; OAuth (TokenVerifier with a real authorization server) when ReportAI
# is listed in a connector directory that requires it.
"""

from contextvars import ContextVar

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core import rate_limit
from app.core.database import AsyncSessionLocal
from app.core.exceptions import RateLimitException
from app.services import api_keys
from app.services.api_keys import Principal

_principal: ContextVar[Principal | None] = ContextVar("mcp_principal", default=None)


def current_principal() -> Principal:
    """The caller of the tool running now. Only reachable through ApiKeyAuth, so a None is a bug."""
    principal = _principal.get()
    if principal is None:
        raise RuntimeError("An MCP tool ran outside an authenticated request")
    return principal


def _bearer(scope: Scope) -> str | None:
    scheme, _, secret = Headers(scope=scope).get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return secret.strip() or None


class ApiKeyAuth:
    """ASGI middleware in front of the MCP app: 401 without a valid key, 429 over the key's limit,
    otherwise the request runs with the caller in `current_principal()`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        secret = _bearer(scope)
        async with AsyncSessionLocal() as db:
            principal = await api_keys.authenticate(db, secret) if secret else None
            if principal is not None:
                try:
                    await rate_limit.mcp_by_key.check(db, str(principal.key_id))
                except RateLimitException as exc:
                    await JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)(scope, receive, send)
                    return
                await rate_limit.mcp_by_key.record(db, str(principal.key_id))
        if principal is None:
            response = JSONResponse(
                {"detail": "Missing, unknown, revoked or expired ReportAI API key. Make one in ReportAI under API keys."},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="ReportAI"'},
            )
            await response(scope, receive, send)
            return
        token = _principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            _principal.reset(token)
