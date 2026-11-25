"""Which apps may ask a person for access, and where they may send the answer.

Two ways to be known. An app registers itself (Dynamic Client Registration, RFC 7591) and gets a
client_id from us. Or its client_id is the https URL of a metadata document it publishes (Client ID
Metadata Documents, what claude.ai uses), which this server fetches and caches for a day. Either way
the same rule holds for where the answer goes: an https address, or the person's own computer
(http on a loopback address, on the very port it registered: the SDK compares redirect URIs
exactly), so an approval can't be sent to a page someone else runs over plain HTTP.

The document is fetched from an address a stranger chose, by an unauthenticated request: it is the
one place this server reaches out on someone else's say-so, so the fetch is fenced (https on 443,
public addresses only, no redirects, two at a time, 5 seconds in all, 64 KB of JSON), counted per
caller's address, and made with no database transaction open, so slow answers can't tie up the
connection pool. A document that fails any check is an unknown client, and the reason goes to the
log.

Two kinds of failure, told apart. A document refused stops being served at once, cached or not:
the address is not one to fetch (not public, not a valid URL), the publisher answered 410 Gone, or
its JSON says something this server won't take (not its own client_id, a missing field, redirect
URIs or an auth method it won't serve). Anything else means it can't be had right now (any other
status, a body that is not a JSON document or is too big, timeout, DNS, network) and leaves the copy
fetched before in service for up to a week, so a publisher's outage or a misconfigured CDN doesn't
cut off everyone connected through it. Either is remembered for ten minutes, so a failing address
isn't fetched again on every request.
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
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.crypto import decrypt, encrypt
from app.core.exceptions import RateLimitException
from app.models.oauth import OAuthClient, OAuthMetadataFetchFailure
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
METADATA_DOCUMENT_TIMEOUT_SECONDS: float = 5  # waiting for a slot, resolving the host and downloading
# The timeout above frees the request that waits, not the thread a hung DNS lookup holds: the
# loop's resolver runs in its default executor, a small pool asyncio.to_thread shares. Without a
# bound, strangers naming slow hosts could take every thread and stall the process's lookups and
# file work. A fetch that gets no slot in its time is "unavailable", as if the publisher were down.
# ponytail: per process, so a deployment's ceiling is this times its API processes. Upgrade path:
# a limiter shared by every process (a Postgres advisory lock per slot, say) if that is too many.
METADATA_FETCHES_AT_ONCE = 2
_fetch_slots = asyncio.Semaphore(METADATA_FETCHES_AT_ONCE)
# A failed fetch, of either kind, is not tried again for this long.
FETCH_FAILURE_TTL = timedelta(minutes=10)
# ponytail: a document that can't be fetched is served from its last copy for up to 7 days past
# that fetch; after that the app is unknown until its publisher answers again. Upgrade path: a
# longer ceiling, or an alert to the operator, if a publisher's outage ever lasts that long.
STALE_DOCUMENT_CEILING = timedelta(days=7)
# The fields of a client's metadata this server reads (to check it, to validate a redirect or a
# token request, to name the app): nothing else a client sends is stored.
_STORED_FIELDS = frozenset(
    {
        "redirect_uris",
        "token_endpoint_auth_method",
        "grant_types",
        "response_types",
        "client_name",
        "client_id_issued_at",
        "client_secret_expires_at",
    }
)
# Tests swap these for an httpx.MockTransport and a fake resolver: the HTTP boundary, nothing else.
_transport: httpx.AsyncBaseTransport | None = None


class ClientMetadataError(Exception):
    """A client metadata document this server won't use: why, for the log (never shown to anyone)."""


class MetadataDocumentUnavailable(ClientMetadataError):
    """A document that could not be had right now (any status but 200 and 410, a body that is not a
    JSON document or is too big, DNS, network, timeout, no fetch slot): its last copy, if any,
    stays in service. Any other ClientMetadataError is a refusal."""


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
    return client.model_dump(mode="json", include=set(_STORED_FIELDS), exclude_none=True)


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


async def get_client(db: AsyncSession, client_id: str, *, client_ip: str) -> OAuthClientInformationFull | None:
    """The client `client_id` names, or None: an id nobody registered, one too long or not printable
    ASCII (refused before any lookup), or a metadata document that can't be fetched or fails a
    check. `client_ip` is who asked: fetches are counted against it.
    May commit whatever `db` holds, before a fetch and after it (the document cached)."""
    if len(client_id) > MAX_CLIENT_ID_CHARS:
        logger.info("Refused a client_id of %s characters, more than %s", len(client_id), MAX_CLIENT_ID_CHARS)
        return None
    # A UUID of ours, or a URL (non-ASCII is percent-encoded in one): so each character is a byte,
    # and an id within the length above fits the columns' btree indexes, which take ~2700 bytes.
    if not (client_id.isascii() and client_id.isprintable()):
        logger.info("Refused a client_id that is not printable ASCII: %r", client_id[:200])
        return None
    if client_id.startswith("https://"):
        return await _metadata_document_client(db, client_id, client_ip)
    if "://" in client_id:  # this server's own ids are UUIDs: this one is an address, not https
        logger.info("Refused the client_id %s: a metadata document must be at an https address", client_id[:200])
        return None
    row = await db.scalar(select(OAuthClient).where(OAuthClient.client_id == client_id, OAuthClient.kind == "dcr"))
    return None if row is None else _as_client(row)


def _fetched_within(row: OAuthClient | None, age: timedelta, now: datetime) -> bool:
    return row is not None and row.fetched_at is not None and row.fetched_at > now - age


async def _metadata_document_client(db: AsyncSession, url: str, client_ip: str) -> OAuthClientInformationFull | None:
    now = datetime.now(UTC)
    row = await db.scalar(select(OAuthClient).where(OAuthClient.client_id == url, OAuthClient.kind == "cimd"))
    if row is not None and _fetched_within(row, METADATA_DOCUMENT_TTL, now):
        return _as_client(row)
    # What is served when the document can't be fetched now: its last copy, if recent enough.
    fallback = _as_client(row) if row is not None and _fetched_within(row, STALE_DOCUMENT_CEILING, now) else None
    failed_at = await db.scalar(select(OAuthMetadataFetchFailure.failed_at).where(OAuthMetadataFetchFailure.url == url))
    if failed_at is not None and failed_at > now - FETCH_FAILURE_TTL:
        return fallback
    try:
        await rate_limit.oauth_metadata_fetch_by_ip.check(db, client_ip)
    except RateLimitException:
        logger.warning("Did not fetch the client metadata document at %s: %s has fetched too many lately", url[:200], client_ip)
        return fallback
    # Counting the fetch commits: no transaction, and no pooled connection, is held while a
    # stranger's server takes its time to answer.
    await rate_limit.oauth_metadata_fetch_by_ip.record(db, client_ip)
    try:
        client = await fetch_metadata_document(url)
    except MetadataDocumentUnavailable as exc:
        await _remember_failure(db, url)
        await db.commit()
        if row is None or fallback is None:
            logger.warning("Could not fetch the client metadata document at %s: %s", url[:200], exc)
        else:
            logger.error(
                "Could not fetch the client metadata document at %s: %s. Serving its copy fetched at %s",
                url[:200], exc, row.fetched_at,
            )
        return fallback
    except ClientMetadataError as exc:
        logger.warning("Refused the client metadata document at %s: %s", url[:200], exc)
        await _remember_failure(db, url)
        # Its copy is no longer the app's word: never served again, fresh or stale. The row, and
        # the grants hanging off it, stay in case the publisher fixes the document.
        await db.execute(update(OAuthClient).where(OAuthClient.client_id == url, OAuthClient.kind == "cimd").values(fetched_at=None))
        await db.commit()
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
    await db.execute(delete(OAuthMetadataFetchFailure).where(OAuthMetadataFetchFailure.url == url))
    await db.commit()
    return client.model_copy(update={"scope": SCOPE})


async def _remember_failure(db: AsyncSession, url: str) -> None:
    statement = insert(OAuthMetadataFetchFailure).values(url=url, failed_at=datetime.now(UTC))
    await db.execute(
        statement.on_conflict_do_update(index_elements=[OAuthMetadataFetchFailure.url], set_={"failed_at": statement.excluded.failed_at})
    )


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
    except UnicodeError as exc:  # IDNA: an empty label ("a..com"), or one longer than 63 characters
        raise ClientMetadataError(f"the host name is not valid ({exc})") from exc
    except OSError as exc:
        raise MetadataDocumentUnavailable(f"the host does not resolve ({exc})") from exc
    return {str(info[4][0]) for info in infos}


async def fetch_metadata_document(url: str) -> OAuthClientInformationFull:
    """The client a Client ID Metadata Document describes, fetched from `url`. Raises
    ClientMetadataError for an address it must not fetch (not https on 443 with a path, not public,
    not a URL httpx can request), a 410, or a JSON document it must not trust (another client_id,
    a field, redirect URI or auth method this server won't take); MetadataDocumentUnavailable for
    anything else: any other status, a body that is not JSON or too big, DNS, network, timeout."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:  # a malformed IPv6 host, or a port that is not a number
        raise ClientMetadataError(f"not a valid URL ({exc})") from exc
    if parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None:
        raise ClientMetadataError("not a plain https URL")
    if port not in (None, 443) or parts.fragment or parts.path in ("", "/"):
        raise ClientMetadataError("an https URL on port 443 with a path is required")
    got_a_slot = False
    try:
        # One budget for all three: a resolver that hangs is as slow as a server that does, and a
        # queue of other fetches as slow as either.
        async with asyncio.timeout(METADATA_DOCUMENT_TIMEOUT_SECONDS), _fetch_slots:
            got_a_slot = True
            addresses = await _resolve(parts.hostname)
            if not addresses or not all(_public(address) for address in addresses):
                raise ClientMetadataError("the host resolves to an address that is not public")
            # ponytail: the host is resolved here and again by httpx when it connects, so a DNS
            # answer that changes in between (DNS rebinding) could still point the request at a
            # private address. Upgrade path: connect to the vetted address itself, with the host
            # only for TLS (SNI) and the Host header, through a custom httpx transport.
            body = await _download(url)
    except TimeoutError as exc:
        if not got_a_slot:
            raise MetadataDocumentUnavailable(
                f"no fetch slot came free within {METADATA_DOCUMENT_TIMEOUT_SECONDS} seconds ({METADATA_FETCHES_AT_ONCE} busy)"
            ) from exc
        raise MetadataDocumentUnavailable(f"no complete answer within {METADATA_DOCUMENT_TIMEOUT_SECONDS} seconds") from exc
    try:
        document = json.loads(body)
    except (ValueError, RecursionError) as exc:  # RecursionError: "[[[[…" nested past the parser's depth
        raise MetadataDocumentUnavailable("the document is not JSON") from exc
    # From here on it is JSON the publisher serves as its document, so what it says is its word.
    if not isinstance(document, dict):  # then it names no client_id: as good as naming another
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
        fields = ", ".join(".".join(str(part) for part in error["loc"]) or "(the document)" for error in exc.errors())
        raise ClientMetadataError(f"the document is not valid client metadata (at {fields})") from exc
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
                # Only Gone says the publisher withdrew the document. Any other status, like a body
                # that is not the document, is as likely a CDN, a proxy or a deploy gone wrong.
                if response.status_code == 410:
                    raise ClientMetadataError("the server answered 410: the document is gone for good")
                if response.status_code != 200:
                    raise MetadataDocumentUnavailable(f"the server answered {response.status_code}, not 200")
                content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type != "application/json" and not content_type.endswith("+json"):
                    raise MetadataDocumentUnavailable(f"the document is {content_type or 'untyped'}, not JSON")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > METADATA_DOCUMENT_MAX_BYTES:
                        raise MetadataDocumentUnavailable(f"the document is larger than {METADATA_DOCUMENT_MAX_BYTES} bytes")
        except httpx.InvalidURL as exc:  # not an HTTPError: an address no request can be made to
            raise ClientMetadataError(f"not a valid URL ({exc})") from exc
        except httpx.HTTPError as exc:
            raise MetadataDocumentUnavailable(f"the request failed ({type(exc).__name__}: {exc})") from exc
    return bytes(body)
