"""OAuth 2.1 sign-in for AI assistants: an app (claude.ai, ChatGPT, Cursor) asks to use ReportAI, the
person signs in to the panel and approves it, and the app gets tokens that act as that person on the
MCP server, exactly as a personal API key would (services/api_keys.py), and never more.

ReportAI is its own authorization server: the issuer is the panel's origin, whose well-known
documents the panel serves by asking the API (frontend/server/routes/.well-known/), and the one
resource is the MCP server. The SDK's handlers do the protocol (PKCE, code expiry, redirect URI
checks); this package is what they call: clients.py (which apps may ask), provider.py (codes and
tokens), grants.py (what a token is worth, and what the panel lists and revokes).

What lives here: the URLs and the one scope, shared by all three.
"""

import hashlib

from mcp.shared.auth import OAuthMetadata, ProtectedResourceMetadata

from app.core.config import settings

# What a personal API key can do: read what the person sees, start drafts. Never approve or send.
SCOPE = "reportai"


def token_hash(secret: str) -> str:
    """Codes and tokens have 256 random bits: a fast hash is enough, nothing to brute-force."""
    return hashlib.sha256(secret.encode()).hexdigest()


def issuer() -> str:
    return settings.FRONTEND_ORIGIN.rstrip("/")


def _api(path: str) -> str:
    # Every installation serves the API under its panel's origin (as pdf_links.py assumes too). In
    # development, with the API on a port of its own, these addresses name the panel's port, so a
    # real client can't follow them there: tests call the routes directly.
    return f"{issuer()}{settings.API_ROOT_PATH}{path}"


def resource_url() -> str:
    """The MCP server, as clients name it in `resource` (RFC 8707) and as its tokens are bound."""
    return _api("/mcp")


def resource_metadata_url() -> str:
    """Where the MCP server's RFC 9728 document is: the panel serves it, from /oauth/protected-resource."""
    return f"{issuer()}/.well-known/oauth-protected-resource{settings.API_ROOT_PATH}/mcp"


def is_this_resource(resource: str) -> bool:
    # A trailing slash names the same server; anything else is someone else's.
    return resource.rstrip("/") == resource_url()


def authorization_server_metadata() -> OAuthMetadata:
    """RFC 8414: what a client reads at the issuer's /.well-known/oauth-authorization-server."""
    auth_methods = ["none", "client_secret_post", "client_secret_basic"]
    return OAuthMetadata.model_validate(
        {
            "issuer": issuer(),
            "authorization_endpoint": _api("/oauth/authorize"),
            "token_endpoint": _api("/oauth/token"),
            "registration_endpoint": _api("/oauth/register"),
            "revocation_endpoint": _api("/oauth/revoke"),
            "scopes_supported": [SCOPE],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": auth_methods,
            "revocation_endpoint_auth_methods_supported": auth_methods,
            "code_challenge_methods_supported": ["S256"],
            "client_id_metadata_document_supported": True,
        }
    )


def protected_resource_metadata() -> ProtectedResourceMetadata:
    """RFC 9728: what the MCP server's 401 points a client to."""
    return ProtectedResourceMetadata.model_validate(
        {
            "resource": resource_url(),
            "authorization_servers": [issuer()],
            "scopes_supported": [SCOPE],
            "bearer_methods_supported": ["header"],
            "resource_name": "ReportAI",
        }
    )
