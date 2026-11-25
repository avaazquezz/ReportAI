"""Which apps may ask a person for access, and where they may send the answer.

Two ways to be known. An app registers itself (Dynamic Client Registration, RFC 7591) and gets a
client_id from us. Or its client_id is the https URL of a metadata document it publishes (Client ID
Metadata Documents, what claude.ai uses), which this server fetches and caches for a day. Either way
the same rule holds for where the answer goes: an https address, or the person's own computer
(http on a loopback address, any port), so an approval can't be sent to a page someone else runs
over plain HTTP.

The document is fetched from an address a stranger chose, by an unauthenticated request: it is the
one place this server reaches out on someone else's say-so, so the fetch is fenced (https on 443,
public addresses only, no redirects, 5 seconds, 64 KB of JSON). A document that fails any check is
an unknown client, and the reason goes to the log.
"""

import asyncio
import ipaddress
import json
import logging
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp.server.auth.provider import RegistrationError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt, encrypt
from app.models.oauth import OAuthClient
from app.services.oauth import SCOPE

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_GRANT_TYPES = frozenset({"authorization_code", "refresh_token"})
_MAX_REDIRECT_URIS = 10
_MAX_URI_CHARS = 2000
_MAX_NAME_CHARS = 200
MAX_CLIENT_ID_CHARS = 2048  # oauth_clients.client_id

METADATA_DOCUMENT_TTL = timedelta(hours=24)
METADATA_DOCUMENT_MAX_BYTES = 64 * 1024
METADATA_DOCUMENT_TIMEOUT_SECONDS = 5
# Tests swap these for an httpx.MockTransport and a fake resolver: the HTTP boundary, nothing else.
_transport: httpx.AsyncBaseTransport | None = None


class ClientMetadataError(Exception):
    """A client metadata document this server won't use: why, for the log (never shown to anyone)."""


def redirect_uri_allowed(uri: str) -> bool:
    """https anywhere, or http to the person's own computer (RFC 8252 §7.3): nothing else, and no
    fragment or user info, which have no place in a redirect and only serve to disguise one."""
    parts = urlsplit(uri)
    if parts.fragment or parts.username is not None or parts.password is not None or len(uri) > _MAX_URI_CHARS:
        return False
    if parts.scheme == "https":
        return bool(parts.hostname)
    return parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS


def _check(client: OAuthClientInformationFull, *, metadata_document: bool) -> None:
    """Raises RegistrationError unless the client is one this server can serve safely."""
    uris = [str(uri) for uri in client.redirect_uris or []]
    if not uris or len(uris) > _MAX_REDIRECT_URIS:
        raise RegistrationError("invalid_redirect_uri", f"Give between 1 and {_MAX_REDIRECT_URIS} redirect_uris")
    refused = [uri for uri in uris if not redirect_uri_allowed(uri)]
    if refused:
        raise RegistrationError(
            "invalid_redirect_uri", "redirect_uris must be https, or http on a loopback address (127.0.0.1, [::1], localhost)"
        )
    if not set(client.grant_types) <= _GRANT_TYPES or "authorization_code" not in client.grant_types:
        raise RegistrationError("invalid_client_metadata", "grant_types may only be authorization_code and refresh_token")
    if set(client.response_types) != {"code"}:
        raise RegistrationError("invalid_client_metadata", "response_types must be ['code']")
    # A metadata document can't carry a secret (it is public), so its client authenticates with
    # nothing but PKCE.
    allowed_methods = {"none"} if metadata_document else {"none", "client_secret_post", "client_secret_basic"}
    if (client.token_endpoint_auth_method or "none") not in allowed_methods:
        raise RegistrationError("invalid_client_metadata", f"token_endpoint_auth_method must be one of {sorted(allowed_methods)}")
    if client.client_name is not None and len(client.client_name) > _MAX_NAME_CHARS:
        raise RegistrationError("invalid_client_metadata", f"client_name has more than {_MAX_NAME_CHARS} characters")


def _as_client(row: OAuthClient) -> OAuthClientInformationFull:
    # The scope is ours to give, whatever the app asked for: the one there is.
    return OAuthClientInformationFull.model_validate(
        {
            **row.client_metadata,
            "client_id": row.client_id,
            "client_secret": decrypt(row.client_secret) if row.client_secret else None,
            "scope": SCOPE,
        }
    )


def _stored_metadata(client: OAuthClientInformationFull) -> dict[str, Any]:
    return client.model_dump(mode="json", exclude={"client_id", "client_secret", "scope"}, exclude_none=True)


async def register(db: AsyncSession, client: OAuthClientInformationFull) -> None:
    """Stores a client that registered itself (RFC 7591), and commits. Raises RegistrationError for
    one this server won't serve."""
    _check(client, metadata_document=False)
    db.add(
        OAuthClient(
            client_id=client.client_id,
            kind="dcr",
            client_metadata=_stored_metadata(client),
            client_secret=encrypt(client.client_secret) if client.client_secret else None,
        )
    )
    await db.commit()


async def get_client(db: AsyncSession, client_id: str) -> OAuthClientInformationFull | None:
    """The client `client_id` names, or None: an id nobody registered, or a metadata document that
    can't be fetched or fails a check. May commit (a document fetched is cached)."""
    if len(client_id) > MAX_CLIENT_ID_CHARS:
        return None
    if client_id.startswith("https://"):
        return await _metadata_document_client(db, client_id)
    row = await db.scalar(select(OAuthClient).where(OAuthClient.client_id == client_id, OAuthClient.kind == "dcr"))
    return None if row is None else _as_client(row)


async def _metadata_document_client(db: AsyncSession, url: str) -> OAuthClientInformationFull | None:
    row = await db.scalar(select(OAuthClient).where(OAuthClient.client_id == url, OAuthClient.kind == "cimd"))
    if row is not None and row.fetched_at is not None and row.fetched_at > datetime.now(UTC) - METADATA_DOCUMENT_TTL:
        return _as_client(row)
    try:
        client = await fetch_metadata_document(url)
    except ClientMetadataError as exc:
        logger.warning("Refused the client metadata document at %s: %s", url[:200], exc)
        return None
    statement = insert(OAuthClient).values(
        client_id=url, kind="cimd", client_metadata=_stored_metadata(client), fetched_at=datetime.now(UTC)
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[OAuthClient.client_id],
            set_={"metadata": statement.excluded["metadata"], "fetched_at": statement.excluded.fetched_at},
        )
    )
    await db.commit()
    return client.model_copy(update={"scope": SCOPE})


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


async def _resolve(host: str) -> set[str]:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ClientMetadataError(f"the host does not resolve ({exc})") from exc
    return {str(info[4][0]) for info in infos}


async def fetch_metadata_document(url: str) -> OAuthClientInformationFull:
    """The client a Client ID Metadata Document describes, fetched from `url`. Raises
    ClientMetadataError for an address it must not fetch or a document it must not trust."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None:
        raise ClientMetadataError("not a plain https URL")
    if parts.port not in (None, 443) or parts.fragment or parts.path in ("", "/"):
        raise ClientMetadataError("an https URL on port 443 with a path is required")
    addresses = await _resolve(parts.hostname)
    if not addresses or not all(_public(address) for address in addresses):
        raise ClientMetadataError("the host resolves to an address that is not public")
    # ponytail: the host is resolved here and again by httpx when it connects, so a DNS answer
    # that changes in between (DNS rebinding) could still point the request at a private address.
    # Upgrade path: connect to the vetted address itself, with the host only for TLS (SNI) and
    # the Host header, through a custom httpx transport.
    try:
        async with asyncio.timeout(METADATA_DOCUMENT_TIMEOUT_SECONDS):
            body = await _download(url)
    except TimeoutError as exc:
        raise ClientMetadataError("no complete answer within the time allowed") from exc
    try:
        document = json.loads(body)
    except ValueError as exc:
        raise ClientMetadataError("the document is not JSON") from exc
    if not isinstance(document, dict):
        raise ClientMetadataError("the document is not a JSON object")
    if document.get("client_id") != url:
        raise ClientMetadataError("the document's client_id is not its own URL")
    if not isinstance(document.get("client_name"), str) or not document["client_name"].strip():
        raise ClientMetadataError("the document has no client_name")
    if not document.get("redirect_uris"):
        raise ClientMetadataError("the document has no redirect_uris")
    if "client_secret" in document:
        raise ClientMetadataError("a public document can't carry a client secret")
    try:
        client = OAuthClientInformationFull.model_validate(document)
        _check(client, metadata_document=True)
    except ValidationError as exc:
        raise ClientMetadataError(f"the document is not valid client metadata ({exc.error_count()} errors)") from exc
    except RegistrationError as exc:
        raise ClientMetadataError(exc.error_description or exc.error) from exc
    return client.model_copy(update={"token_endpoint_auth_method": "none"})


async def _download(url: str) -> bytes:
    # trust_env off: a proxy from the environment must not route around the address check.
    async with httpx.AsyncClient(
        transport=_transport, timeout=METADATA_DOCUMENT_TIMEOUT_SECONDS, follow_redirects=False, trust_env=False
    ) as http:
        try:
            async with http.stream("GET", url, headers={"Accept": "application/json"}) as response:
                if response.status_code != 200:
                    raise ClientMetadataError(f"the server answered {response.status_code}, not 200")
                content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type != "application/json" and not content_type.endswith("+json"):
                    raise ClientMetadataError(f"the document is {content_type or 'untyped'}, not JSON")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > METADATA_DOCUMENT_MAX_BYTES:
                        raise ClientMetadataError(f"the document is larger than {METADATA_DOCUMENT_MAX_BYTES} bytes")
        except httpx.HTTPError as exc:
            raise ClientMetadataError(f"the request failed ({type(exc).__name__})") from exc
    return bytes(body)
