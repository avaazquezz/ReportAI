"""OAuth sign-in for AI assistants, over HTTP with the app in-process, the way claude.ai goes through
it: register (or a metadata document), authorize, the person approves in the panel, the code buys
tokens, the tokens reach /mcp as that person and nothing more, and every way of ending it ends it.
"""

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import httpx2
import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import seal
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.oauth import (
    OAuthClient,
    OAuthCode,
    OAuthGrant,
    OAuthMetadataFetchFailure,
    OAuthToken,
)
from app.models.report import Report
from app.services.oauth import (
    SCOPE,
    clients,
    issuer,
    resource_metadata_url,
    resource_url,
    token_hash,
)
from tests.test_mcp_server import (  # noqa: F401
    _company,
    _connect,
    _data,
    _delivered,
    _link,
    _open,
    _running,
)
from tests.test_tenant_isolation import _auth

REDIRECT = "https://claude.ai/api/mcp/auth_callback"
_real_resolve = clients._resolve  # before any test swaps it for a fake


@pytest.fixture(autouse=True)
def _oauth_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MCP_OAUTH_ENABLED", True)


@pytest.fixture
async def http() -> AsyncIterator[httpx2.AsyncClient]:
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def companies(db: AsyncSession) -> tuple[dict[str, Any], dict[str, Any]]:
    return await _company(db, "Acme"), await _company(db, "Rival")


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


async def _register(http: httpx2.AsyncClient, redirect_uris: list[str] | None = None, **extra: Any) -> httpx2.Response:
    return await http.post(
        "/oauth/register",
        json={"redirect_uris": redirect_uris or [REDIRECT], "client_name": "Claude", "token_endpoint_auth_method": "none", **extra},
    )


async def _client_id(http: httpx2.AsyncClient) -> str:
    registered = await _register(http)
    assert registered.status_code == 201, registered.text
    return str(registered.json()["client_id"])


async def _authorize(http: httpx2.AsyncClient, client_id: str, challenge: str, **params: str) -> httpx2.Response:
    query = {
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "st4te", "scope": SCOPE, "resource": resource_url(), **params,
    }
    return await http.get("/oauth/authorize", params=query)


def _consent_request(response: httpx2.Response) -> str:
    assert response.status_code == 302, response.text
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{settings.FRONTEND_ORIGIN}/oauth/consent"
    return parse_qs(location.query)["request"][0]


async def _answer(http: httpx2.AsyncClient, user: Any, sealed: str, approve: bool = True) -> dict[str, list[str]]:
    answered = await http.post("/oauth/consent", json={"request": sealed, "approve": approve}, headers=_auth(user))
    assert answered.status_code == 200, answered.text
    redirect = urlsplit(answered.json()["redirect_to"])
    assert f"{redirect.scheme}://{redirect.netloc}{redirect.path}" == REDIRECT
    return parse_qs(redirect.query)


async def _code(http: httpx2.AsyncClient, user: Any, client_id: str, challenge: str) -> str:
    query = await _answer(http, user, _consent_request(await _authorize(http, client_id, challenge)))
    assert query["state"] == ["st4te"]
    return query["code"][0]


async def _exchange(http: httpx2.AsyncClient, client_id: str, code: str, verifier: str, **extra: str) -> httpx2.Response:
    return await http.post(
        "/oauth/token",
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "client_id": client_id, "code_verifier": verifier, **extra},
    )


async def _refresh(http: httpx2.AsyncClient, client_id: str, refresh_token: str) -> httpx2.Response:
    return await http.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id})


async def _connected(http: httpx2.AsyncClient, user: Any) -> dict[str, str]:
    client_id = await _client_id(http)
    verifier, challenge = _pkce()
    tokens = await _exchange(http, client_id, await _code(http, user, client_id, challenge), verifier)
    assert tokens.status_code == 200, tokens.text
    return {"client_id": client_id, **tokens.json()}


async def _mcp(http: httpx2.AsyncClient, access_token: str) -> httpx2.Response:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    return await http.post("/mcp", json=body, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json, text/event-stream"})


async def _grant(db: AsyncSession, access_token: str) -> OAuthGrant:
    grant = await db.scalar(
        select(OAuthGrant).join(OAuthToken).where(OAuthToken.token_hash == token_hash(access_token)).execution_options(populate_existing=True)
    )
    assert grant is not None
    return grant


async def test_a_person_connects_an_app_that_then_acts_as_them_until_its_grant_ends(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    acme, _ = companies
    technician = acme["technician"]
    client_id = await _client_id(http)
    verifier, challenge = _pkce()

    sealed = _consent_request(await _authorize(http, client_id, challenge))
    shown = await http.get("/oauth/consent", params={"request": sealed}, headers=_auth(technician))
    assert shown.status_code == 200
    assert shown.json() == {
        "client_name": "Claude", "client_id": client_id, "published_by": None, "redirect_host": "claude.ai", "scopes": [SCOPE]
    }
    approved = await _answer(http, technician, sealed)
    tokens = await _exchange(http, client_id, approved["code"][0], verifier, resource=resource_url())
    assert tokens.status_code == 200, tokens.text
    first = tokens.json()
    assert first["token_type"] == "Bearer" and first["expires_in"] == 3600 and first["scope"] == SCOPE
    assert first["access_token"].startswith("rpo_") and first["refresh_token"].startswith("rpr_")
    assert tokens.headers["cache-control"] == "no-store"

    # As the technician: their own report, not a colleague's, not another company's.
    async with _connect(first["access_token"]) as mcp:
        assert len((await mcp.list_tools()).tools) == 5
        found = _data(await mcp.call_tool("reportai_search_reports", {}))
    assert [item["id"] for item in found["items"]] == [str(acme["own"].id)]
    grant = await _grant(db, first["access_token"])
    assert (grant.user_id, grant.tenant_id, grant.resource) == (technician.id, acme["tenant"].id, resource_url())

    # A PDF link handed over through the grant is worth what the grant is.
    report = await _delivered(db, acme["own"], tmp_path)
    async with _connect(first["access_token"]) as mcp:
        link = _link(await mcp.call_tool("reportai_get_report_pdf", {"report_id": str(report.id)}))
    assert (await _open(link)).status_code == 200

    rotated = await _refresh(http, client_id, first["refresh_token"])
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()
    assert second["access_token"] != first["access_token"] and second["refresh_token"] != first["refresh_token"]
    assert (await _mcp(http, second["access_token"])).status_code == 200

    # The spent refresh token again: someone holds a copy, so the whole grant ends.
    reused = await _refresh(http, client_id, first["refresh_token"])
    assert reused.status_code == 400 and reused.json()["error"] == "invalid_grant"
    assert (await _grant(db, first["access_token"])).revoked_at is not None
    assert (await _refresh(http, client_id, second["refresh_token"])).status_code == 400
    refused = await _mcp(http, second["access_token"])
    assert refused.status_code == 401
    assert (await _open(link)).status_code == 404


async def test_a_draft_started_by_an_app_records_its_grant(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    tokens = await _connected(http, acme["technician"])

    async with _connect(tokens["access_token"]) as mcp:
        draft = _data(await mcp.call_tool("reportai_create_report_draft", {"document_type_id": str(acme["visit"].id), "text": "Obra Acme Este."}))

    report = await db.scalar(select(Report).where(Report.id == uuid.UUID(draft["id"])))
    assert report is not None
    grant = await _grant(db, tokens["access_token"])
    assert report.channel_meta == {"via": "mcp", "oauth_grant_id": str(grant.id)}


async def test_the_code_needs_the_verifier_and_works_once(
    http: httpx2.AsyncClient, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    client_id = await _client_id(http)
    verifier, challenge = _pkce()
    code = await _code(http, acme["approver"], client_id, challenge)

    wrong = await _exchange(http, client_id, code, _pkce()[0])
    first = await _exchange(http, client_id, code, verifier)
    again = await _exchange(http, client_id, code, verifier)

    assert wrong.status_code == 400 and wrong.json()["error"] == "invalid_grant"
    assert first.status_code == 200
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"


async def test_an_expired_code_buys_nothing(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    client_id = await _client_id(http)
    verifier, challenge = _pkce()
    code = await _code(http, acme["approver"], client_id, challenge)
    await db.execute(update(OAuthCode).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    await db.commit()

    expired = await _exchange(http, client_id, code, verifier)

    assert expired.status_code == 400 and expired.json()["error"] == "invalid_grant"


async def test_a_code_is_for_the_app_it_was_given_to(
    http: httpx2.AsyncClient, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    client_id, other = await _client_id(http), await _client_id(http)
    verifier, challenge = _pkce()
    code = await _code(http, acme["approver"], client_id, challenge)

    stolen = await _exchange(http, other, code, verifier)

    assert stolen.status_code == 400 and stolen.json()["error"] == "invalid_grant"


async def test_an_unregistered_redirect_uri_is_refused_without_redirecting(
    http: httpx2.AsyncClient, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    client_id = await _client_id(http)

    response = await _authorize(http, client_id, _pkce()[1], redirect_uri="https://evil.example/callback")

    assert response.status_code == 400 and "location" not in response.headers
    assert response.json()["error"] == "invalid_request"


async def test_an_unknown_client_is_refused(http: httpx2.AsyncClient) -> None:
    response = await _authorize(http, str(uuid.uuid4()), _pkce()[1])

    assert response.status_code == 400 and "location" not in response.headers


@pytest.mark.parametrize(
    ("redirect_uri", "accepted"),
    [
        ("https://claude.ai/api/mcp/auth_callback", True),
        ("http://127.0.0.1:33418/callback", True),
        ("http://[::1]:5000/cb", True),
        ("http://localhost/callback", True),
        ("http://evil.example/callback", False),
        ("http://192.168.1.20/callback", False),
        ("cursor://anysphere.cursor/oauth", False),
        ("https://claude.ai/cb#fragment", False),
        ("https://user:pass@claude.ai/cb", False),
    ],
)
async def test_registration_takes_https_or_loopback_redirects_only(
    http: httpx2.AsyncClient, db: AsyncSession, redirect_uri: str, accepted: bool
) -> None:
    response = await _register(http, [redirect_uri])

    if accepted:
        assert response.status_code == 201, response.text
        assert response.json()["scope"] == SCOPE
    else:
        assert response.status_code == 400 and response.json()["error"] == "invalid_redirect_uri"
        assert await db.scalar(select(OAuthClient)) is None


@pytest.mark.parametrize(
    "metadata",
    [
        {"grant_types": ["authorization_code", "client_credentials"]},
        {"grant_types": ["refresh_token"]},
        {"scope": "reportai admin"},
        {"client_name": "x" * 201},
    ],
)
async def test_registration_refuses_what_this_server_does_not_do(http: httpx2.AsyncClient, metadata: dict[str, Any]) -> None:
    response = await _register(http, **metadata)

    assert response.status_code == 400 and response.json()["error"] == "invalid_client_metadata"


async def test_a_registered_secret_is_stored_encrypted_and_required(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    registered = (await _register(http, token_endpoint_auth_method="client_secret_post")).json()
    stored = await db.scalar(select(OAuthClient))
    assert stored is not None and stored.client_secret and registered["client_secret"] not in stored.client_secret
    verifier, challenge = _pkce()
    code = await _code(http, acme["approver"], registered["client_id"], challenge)

    without = await _exchange(http, registered["client_id"], code, verifier)
    with_secret = await _exchange(http, registered["client_id"], code, verifier, client_secret=registered["client_secret"])

    assert without.status_code == 401 and without.json()["error"] == "invalid_client"
    assert with_secret.status_code == 200


@pytest.mark.parametrize("sent", ["with its length", "in chunks"])
async def test_a_registration_over_16_kb_is_refused_unread(http: httpx2.AsyncClient, db: AsyncSession, sent: str) -> None:
    body = json.dumps({"redirect_uris": [REDIRECT], "client_name": "Claude", "contacts": ["x" * 17_000]}).encode()

    async def chunks() -> AsyncIterator[bytes]:
        for start in range(0, len(body), 4096):
            yield body[start : start + 4096]

    content = body if sent == "with its length" else chunks()
    response = await http.post("/oauth/register", content=content, headers={"Content-Type": "application/json"})

    assert response.status_code == 413
    assert await db.scalar(select(OAuthClient)) is None


async def test_a_registration_stores_only_what_the_server_reads(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    extra = {
        "contacts": ["ops@app.example"], "jwks": {"keys": [{"kty": "oct", "k": "x" * 1000}]}, "logo_uri": "https://app.example/logo.png",
        "client_uri": "https://app.example", "software_id": "x" * 500, "tos_uri": "https://app.example/tos",
    }
    registered = await _register(http, **extra)
    assert registered.status_code == 201, registered.text

    stored = await db.scalar(select(OAuthClient))
    assert stored is not None
    assert set(stored.client_metadata) <= {
        "redirect_uris", "token_endpoint_auth_method", "grant_types", "response_types", "client_name", "client_id_issued_at",
        "client_secret_expires_at",
    }
    assert stored.client_metadata["client_name"] == "Claude" and stored.client_metadata["redirect_uris"] == [REDIRECT]
    # And it connects as before.
    client_id, (verifier, challenge) = registered.json()["client_id"], _pkce()
    assert (await _exchange(http, client_id, await _code(http, acme["approver"], client_id, challenge), verifier)).status_code == 200


async def test_registration_is_rate_limited_per_address(http: httpx2.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.oauth_register_by_ip, "max_attempts", 2)

    statuses = [(await _register(http)).status_code for _ in range(3)]

    assert statuses == [201, 201, 429]


async def test_a_token_for_another_server_is_never_issued(
    http: httpx2.AsyncClient, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    client_id = await _client_id(http)
    verifier, challenge = _pkce()

    asked = await _authorize(http, client_id, challenge, resource="https://other.example/mcp")
    error = parse_qs(urlsplit(asked.headers["location"]).query)
    code = await _code(http, acme["approver"], client_id, challenge)
    elsewhere = await _exchange(http, client_id, code, verifier, resource="https://other.example/mcp")
    here = await _exchange(http, client_id, code, verifier, resource=resource_url() + "/")

    assert asked.status_code == 302 and error["error"] == ["invalid_target"] and error["state"] == ["st4te"]
    assert elsewhere.status_code == 400 and elsewhere.json()["error"] == "invalid_target"
    assert here.status_code == 200  # refused before the code was spent


async def test_only_the_one_scope_is_given(http: httpx2.AsyncClient) -> None:
    client_id = await _client_id(http)

    asked = await _authorize(http, client_id, _pkce()[1], scope="reportai admin")

    assert parse_qs(urlsplit(asked.headers["location"]).query)["error"] == ["invalid_scope"]


@pytest.mark.parametrize("change", ["issued for another server", "expired", "person switched off", "company suspended", "revoked"])
async def test_mcp_takes_only_a_live_token_for_itself_of_a_person_who_may_act(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], change: str
) -> None:
    acme, _ = companies
    tokens = await _connected(http, acme["approver"])
    assert (await _mcp(http, tokens["access_token"])).status_code == 200
    grant = await _grant(db, tokens["access_token"])
    if change == "issued for another server":
        grant.resource = "https://other.example/mcp"
    elif change == "expired":
        await db.execute(update(OAuthToken).where(OAuthToken.kind == "access").values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    elif change == "person switched off":
        acme["approver"].is_active = False
    elif change == "company suspended":
        acme["tenant"].is_active = False
    else:
        grant.revoked_at = datetime.now(UTC)
    await db.commit()

    refused = await _mcp(http, tokens["access_token"])

    assert refused.status_code == 401
    assert f'resource_metadata="{resource_metadata_url()}"' in refused.headers["www-authenticate"]


async def test_a_person_let_back_in_finds_their_apps_working_again(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    tokens = await _connected(http, acme["approver"])
    acme["approver"].is_active = False
    await db.commit()
    assert (await _refresh(http, tokens["client_id"], tokens["refresh_token"])).status_code == 400

    acme["approver"].is_active = True
    await db.commit()

    assert (await _mcp(http, tokens["access_token"])).status_code == 200
    assert (await _refresh(http, tokens["client_id"], tokens["refresh_token"])).status_code == 200


async def test_a_code_approved_by_someone_since_switched_off_buys_nothing(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    client_id = await _client_id(http)
    verifier, challenge = _pkce()
    code = await _code(http, acme["approver"], client_id, challenge)
    acme["approver"].is_active = False
    await db.commit()

    response = await _exchange(http, client_id, code, verifier)

    assert response.status_code == 400 and response.json()["error"] == "invalid_grant"
    assert await db.scalar(select(OAuthGrant)) is None


async def test_the_app_can_sign_itself_out(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    tokens = await _connected(http, acme["approver"])
    other = await _client_id(http)

    by_another = await http.post("/oauth/revoke", data={"token": tokens["refresh_token"], "client_id": other})
    assert by_another.status_code == 200 and (await _mcp(http, tokens["access_token"])).status_code == 200
    revoked = await http.post("/oauth/revoke", data={"token": tokens["refresh_token"], "client_id": tokens["client_id"]})

    assert revoked.status_code == 200
    assert (await _grant(db, tokens["access_token"])).revoked_at is not None
    assert (await _mcp(http, tokens["access_token"])).status_code == 401


async def test_denying_tells_the_app_and_is_audited(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    client_id = await _client_id(http)
    sealed = _consent_request(await _authorize(http, client_id, _pkce()[1]))

    query = await _answer(http, acme["viewer"], sealed, approve=False)

    assert query == {"error": ["access_denied"], "state": ["st4te"]}
    assert await db.scalar(select(OAuthCode)) is None
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "oauth.denied"))
    assert event is not None and event.actor_id == acme["viewer"].id and event.details["client_id"] == client_id


async def test_approving_is_audited(http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]) -> None:
    acme, _ = companies
    await _connected(http, acme["approver"])

    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "oauth.approved"))

    assert event is not None and event.actor_id == acme["approver"].id and event.details["client_name"] == "Claude"


async def test_a_bad_or_expired_consent_request_is_refused(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    acme, _ = companies
    headers = _auth(acme["approver"])
    client_id = await _client_id(http)
    sealed = _consent_request(await _authorize(http, client_id, _pkce()[1]))
    forged = seal({"purpose": "report_pdf", "client_id": client_id})
    from app.services.oauth import provider

    statuses = [
        (await http.get("/oauth/consent", params={"request": bad}, headers=headers)).status_code
        for bad in (sealed[:-6] + "AAAAAA", forged)
    ]
    await db.execute(update(OAuthClient).values(client_id="gone"))
    await db.commit()
    gone = await http.get("/oauth/consent", params={"request": sealed}, headers=headers)
    monkeypatch.setattr(provider, "CONSENT_TTL", timedelta(seconds=-1))
    expired = await http.post("/oauth/consent", json={"request": sealed, "approve": True}, headers=headers)
    anonymous = await http.get("/oauth/consent", params={"request": sealed})

    assert statuses == [400, 400]
    assert gone.status_code == 404 and expired.status_code == 400 and anonymous.status_code == 401


async def test_the_read_only_demo_account_can_not_approve(
    http: httpx2.AsyncClient, companies: tuple[dict[str, Any], dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    acme, _ = companies
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", acme["approver"].email)
    sealed = _consent_request(await _authorize(http, await _client_id(http), _pkce()[1]))

    response = await http.post("/oauth/consent", json={"request": sealed, "approve": True}, headers=_auth(acme["approver"]))

    assert response.status_code == 403


async def test_the_documents_describe_this_server(http: httpx2.AsyncClient) -> None:
    server = (await http.get("/oauth/metadata")).json()
    resource = (await http.get("/oauth/protected-resource")).json()

    api = f"{settings.FRONTEND_ORIGIN}{settings.API_ROOT_PATH}"
    assert server == {
        "issuer": issuer(),
        "authorization_endpoint": f"{api}/oauth/authorize",
        "token_endpoint": f"{api}/oauth/token",
        "registration_endpoint": f"{api}/oauth/register",
        "revocation_endpoint": f"{api}/oauth/revoke",
        "scopes_supported": [SCOPE],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "revocation_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
        "client_id_metadata_document_supported": True,
    }
    assert resource == {
        "resource": f"{api}/mcp",
        "authorization_servers": [issuer()],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "ReportAI",
    }


async def test_a_reused_refresh_token_is_logged_and_audited_with_its_app(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], caplog: pytest.LogCaptureFixture
) -> None:
    acme, _ = companies
    tokens = await _connected(http, acme["approver"])
    assert (await _refresh(http, tokens["client_id"], tokens["refresh_token"])).status_code == 200

    assert (await _refresh(http, tokens["client_id"], tokens["refresh_token"])).status_code == 400

    grant = await _grant(db, tokens["access_token"])
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "oauth.revoked_reuse"))
    assert event is not None and event.actor_id is None and event.tenant_id == acme["tenant"].id
    assert event.target == str(grant.id) and event.details == {"client_id": tokens["client_id"]}
    assert any(tokens["client_id"] in r.getMessage() and str(grant.id) in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


async def test_a_token_for_another_resource_is_logged_apart_from_an_unknown_one(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], caplog: pytest.LogCaptureFixture
) -> None:
    acme, _ = companies
    tokens = await _connected(http, acme["approver"])
    grant = await _grant(db, tokens["access_token"])
    grant.resource = "https://other.example/mcp"
    await db.commit()

    with caplog.at_level(logging.WARNING, logger="app.services.oauth.grants"):
        assert (await _mcp(http, tokens["access_token"])).status_code == 401
        assert (await _mcp(http, "rpo_unknown")).status_code == 401

    warnings = [r.getMessage() for r in caplog.records if r.name == "app.services.oauth.grants"]
    assert len(warnings) == 1  # the unknown token is not worth a warning
    assert str(grant.id) in warnings[0] and "https://other.example/mcp" in warnings[0] and resource_url() in warnings[0]


@pytest.mark.parametrize(("client_id", "says"), [("x" * 3000, "3000 characters"), ("http://app.example/client.json", "https address")])
async def test_a_client_id_refused_on_sight_is_logged(
    http: httpx2.AsyncClient, caplog: pytest.LogCaptureFixture, client_id: str, says: str
) -> None:
    with caplog.at_level(logging.INFO, logger="app.services.oauth.clients"):
        refused = await _authorize(http, client_id, _pkce()[1])

    assert refused.status_code == 400
    assert any(says in r.getMessage() for r in caplog.records if r.name == "app.services.oauth.clients")


async def test_consent_for_a_redirect_the_document_no_longer_lists_is_logged(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], fetches: "Fetches",
    caplog: pytest.LogCaptureFixture,
) -> None:
    acme, _ = companies
    sealed = _consent_request(await _authorize(http, DOCUMENT_URL, _pkce()[1]))
    await db.execute(update(OAuthClient).values(fetched_at=datetime.now(UTC) - timedelta(hours=25)))
    await db.commit()
    fetches.response = httpx.Response(200, json=_document(redirect_uris=["https://elsewhere.example/cb"]))

    with caplog.at_level(logging.WARNING, logger="app.services.oauth.provider"):
        shown = await http.get("/oauth/consent", params={"request": sealed}, headers=_auth(acme["approver"]))

    assert shown.status_code == 404
    assert any(DOCUMENT_URL in r.getMessage() and "claude.ai" in r.getMessage() for r in caplog.records if r.name == "app.services.oauth.provider")


async def test_a_401_from_mcp_says_where_to_sign_in(http: httpx2.AsyncClient) -> None:
    response = await _mcp(http, "rpo_made-up")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        f'Bearer realm="ReportAI", resource_metadata="{settings.FRONTEND_ORIGIN}/.well-known/oauth-protected-resource'
        f'{settings.API_ROOT_PATH}/mcp", scope="{SCOPE}"'
    )


async def test_with_oauth_off_nothing_of_it_exists(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    acme, _ = companies
    tokens = await _connected(http, acme["approver"])
    grant = await _grant(db, tokens["access_token"])
    monkeypatch.setattr(settings, "MCP_OAUTH_ENABLED", False)
    headers = _auth(acme["tenant_admin"])

    statuses = [
        (await http.get("/oauth/metadata")).status_code,
        (await http.get("/oauth/protected-resource")).status_code,
        (await _authorize(http, tokens["client_id"], _pkce()[1])).status_code,
        (await _refresh(http, tokens["client_id"], tokens["refresh_token"])).status_code,
        (await _register(http)).status_code,
        (await http.post("/oauth/revoke", data={"token": tokens["refresh_token"], "client_id": tokens["client_id"]})).status_code,
        (await http.get("/oauth/consent", params={"request": "x"}, headers=headers)).status_code,
        (await http.get("/oauth/grants", headers=headers)).status_code,
        (await http.delete(f"/oauth/grants/{grant.id}", headers=headers)).status_code,
    ]
    refused = await _mcp(http, tokens["access_token"])

    assert statuses == [404] * 9
    assert refused.status_code == 401 and refused.headers["www-authenticate"] == 'Bearer realm="ReportAI"'
    assert "API key" in refused.json()["detail"]
    assert (await _grant(db, tokens["access_token"])).revoked_at is None


async def test_the_panel_lists_and_revokes_connected_apps_like_keys(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, rival = companies
    own = await _connected(http, acme["technician"])
    colleague = await _connected(http, acme["approver"])
    await _connected(http, rival["approver"])
    own_grant, colleague_grant = await _grant(db, own["access_token"]), await _grant(db, colleague["access_token"])

    mine = (await http.get("/oauth/grants", headers=_auth(acme["technician"]))).json()
    company = (await http.get("/oauth/grants", headers=_auth(acme["tenant_admin"]))).json()
    not_theirs = await http.delete(f"/oauth/grants/{colleague_grant.id}", headers=_auth(acme["technician"]))
    by_admin = await http.delete(f"/oauth/grants/{colleague_grant.id}", headers=_auth(acme["tenant_admin"]))
    by_owner = await http.delete(f"/oauth/grants/{own_grant.id}", headers=_auth(acme["technician"]))

    assert [(g["id"], g["client_name"], g["owner_name"]) for g in mine] == [(str(own_grant.id), "Claude", "Acme technician")]
    assert {g["id"] for g in company} == {str(own_grant.id), str(colleague_grant.id)}
    assert not_theirs.status_code == 404
    assert by_admin.status_code == 204 and by_owner.status_code == 204
    assert (await _mcp(http, colleague["access_token"])).status_code == 401
    assert (await _mcp(http, own["access_token"])).status_code == 401
    assert (await http.get("/oauth/grants", headers=_auth(acme["tenant_admin"]))).json() == []
    events = (await db.scalars(select(AuditEvent.target).where(AuditEvent.action == "oauth.revoked"))).all()
    assert sorted(events) == sorted([str(own_grant.id), str(colleague_grant.id)])


async def test_approving_an_app_again_replaces_its_connection(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    first = await _connected(http, acme["approver"])
    colleague = await _exchange(
        http, first["client_id"], await _code(http, acme["technician"], first["client_id"], (pkce := _pkce())[1]), pkce[0]
    )
    verifier, challenge = _pkce()

    again = await _exchange(http, first["client_id"], await _code(http, acme["approver"], first["client_id"], challenge), verifier)

    assert again.status_code == 200
    assert (await _grant(db, first["access_token"])).revoked_at is not None
    assert (await _mcp(http, first["access_token"])).status_code == 401
    assert (await _mcp(http, again.json()["access_token"])).status_code == 200
    # Someone else's connection to the same app is theirs, and stays.
    assert (await _mcp(http, colleague.json()["access_token"])).status_code == 200


async def test_a_person_connects_at_most_ten_apps(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    from app.services.oauth.grants import MAX_CONNECTED_APPS_PER_USER

    acme, _ = companies
    connected = [await _connected(http, acme["approver"]) for _ in range(MAX_CONNECTED_APPS_PER_USER)]
    one_more = await _client_id(http)
    sealed = _consent_request(await _authorize(http, one_more, _pkce()[1]))

    refused = await http.post("/oauth/consent", json={"request": sealed, "approve": True}, headers=_auth(acme["approver"]))

    assert refused.status_code == 409 and "10 connected apps" in refused.json()["detail"]
    assert await db.scalar(select(func.count()).select_from(OAuthCode)) == 0
    assert (await _mcp(http, connected[0]["access_token"])).status_code == 200  # refusing ended nothing
    # A colleague has ten of their own.
    assert await _code(http, acme["technician"], one_more, _pkce()[1])
    # A connection that ended makes room...
    grant = await _grant(db, connected[1]["access_token"])
    assert (await http.delete(f"/oauth/grants/{grant.id}", headers=_auth(acme["approver"]))).status_code == 204
    verifier, challenge = _pkce()
    assert (await _exchange(http, one_more, await _code(http, acme["approver"], one_more, challenge), verifier)).status_code == 200
    # ...and, back at ten, approving one of them again replaces its connection: no more room needed.
    assert await _code(http, acme["approver"], connected[0]["client_id"], _pkce()[1])


async def test_signing_someone_out_everywhere_disconnects_their_apps(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    acme, _ = companies
    theirs, colleague = await _connected(http, acme["technician"]), await _connected(http, acme["approver"])

    signed_out = await http.post(f"/team/{acme['technician'].id}/sign-out", headers=_auth(acme["tenant_admin"]))

    assert signed_out.status_code == 204
    assert (await _mcp(http, theirs["access_token"])).status_code == 401
    assert (await _refresh(http, theirs["client_id"], theirs["refresh_token"])).status_code == 400
    assert (await _mcp(http, colleague["access_token"])).status_code == 200
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "team.signed_out"))
    assert event is not None and event.details["oauth_grants_revoked"] == 1


# ── Client ID Metadata Documents ───────────────────────────────────────────────────────────────

DOCUMENT_URL = "https://app.example/oauth/client.json"


def _document(**changes: Any) -> dict[str, Any]:
    return {"client_id": DOCUMENT_URL, "client_name": "Example AI", "redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none", **changes}


class Fetches:
    """The fetch at the HTTP boundary: app.example resolves to a public address and answers with
    `response`, after `delay` seconds; every request made lands in `requests`."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.response: httpx.Response | httpx.HTTPError = httpx.Response(200, json=_document())
        self.delay = 0.0
        self.during: Callable[[], None] | None = None  # runs while the request is in flight

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.during is not None:
            self.during()
        await asyncio.sleep(self.delay)
        if isinstance(self.response, httpx.HTTPError):
            raise self.response
        return self.response


@pytest.fixture
def fetches(monkeypatch: pytest.MonkeyPatch, db: AsyncSession) -> Fetches:
    # `db`, used or not: it empties the tables after the test, and a failed fetch leaves a row.
    fake = Fetches()

    async def resolve(host: str) -> set[str]:
        return {"93.184.215.14"}

    monkeypatch.setattr(clients, "_transport", httpx.MockTransport(fake.handle))
    monkeypatch.setattr(clients, "_resolve", resolve)
    return fake


async def test_an_app_known_by_its_metadata_document_connects(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], fetches: Fetches
) -> None:
    acme, _ = companies
    verifier, challenge = _pkce()

    sealed = _consent_request(await _authorize(http, DOCUMENT_URL, challenge))
    shown = (await http.get("/oauth/consent", params={"request": sealed}, headers=_auth(acme["approver"]))).json()
    code = (await _answer(http, acme["approver"], sealed))["code"][0]
    tokens = await _exchange(http, DOCUMENT_URL, code, verifier)

    assert (shown["client_name"], shown["client_id"], shown["published_by"]) == ("Example AI", DOCUMENT_URL, "app.example")
    assert tokens.status_code == 200, tokens.text
    assert (await _mcp(http, tokens.json()["access_token"])).status_code == 200
    # Fetched once, then cached for a day.
    assert [str(request.url) for request in fetches.requests] == [DOCUMENT_URL]
    assert fetches.requests[0].headers["accept"] == "application/json"
    stored = await db.scalar(select(OAuthClient))
    assert stored is not None and stored.kind == "cimd" and stored.client_secret is None


async def test_a_metadata_document_a_day_old_is_fetched_again(
    http: httpx2.AsyncClient, db: AsyncSession, fetches: Fetches
) -> None:
    await _authorize(http, DOCUMENT_URL, _pkce()[1])
    await db.execute(update(OAuthClient).values(fetched_at=datetime.now(UTC) - timedelta(hours=25)))
    await db.commit()
    fetches.response = httpx.Response(200, json=_document(client_name="Renamed AI"))

    await _authorize(http, DOCUMENT_URL, _pkce()[1])

    assert len(fetches.requests) == 2
    stored = await db.scalar(select(OAuthClient).execution_options(populate_existing=True))
    assert stored is not None and stored.client_metadata["client_name"] == "Renamed AI"


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(200, json=_document(client_id="https://app.example/other.json")), "client_id is not its own URL"),
        (httpx.Response(200, json=_document(client_name=None)), "no client_name"),
        (httpx.Response(200, json=_document(redirect_uris=["http://evil.example/cb"])), "redirect_uris must be https"),
        (httpx.Response(200, json=_document(token_endpoint_auth_method="client_secret_post")), "token_endpoint_auth_method"),
        (httpx.Response(302, headers={"location": "http://169.254.169.254/latest"}), "answered 302"),
        (httpx.Response(200, content=json.dumps(_document()).encode() + b" " * 70_000, headers={"content-type": "application/json"}), "larger than"),
        (httpx.Response(200, text=json.dumps(_document())), "not JSON"),
        (httpx.Response(200, content=b"{not json", headers={"content-type": "application/json"}), "not JSON"),
        # Nested past the parser's depth: a RecursionError, not a ValueError.
        (httpx.Response(200, content=b"[" * 60_000, headers={"content-type": "application/json"}), "not JSON"),
        # The log says which field, and what the network said.
        (httpx.Response(200, json=_document(redirect_uris=["not a url"])), "at redirect_uris.0"),
        (httpx.ConnectError("connection refused by peer"), "ConnectError: connection refused by peer"),
    ],
)
async def test_a_metadata_document_that_fails_a_check_is_an_unknown_client(
    http: httpx2.AsyncClient, db: AsyncSession, fetches: Fetches, caplog: pytest.LogCaptureFixture,
    response: httpx.Response | httpx.HTTPError, reason: str,
) -> None:
    fetches.response = response

    refused = await _authorize(http, DOCUMENT_URL, _pkce()[1])

    assert refused.status_code == 400 and "location" not in refused.headers
    assert len(fetches.requests) == 1  # a redirect is not followed
    assert any(reason in record.getMessage() for record in caplog.records), [r.getMessage() for r in caplog.records]
    assert await db.scalar(select(OAuthClient)) is None


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "fd00::1", "::ffff:192.168.1.1", "0.0.0.0", "100.64.0.1"])
async def test_a_metadata_document_on_a_private_address_is_never_fetched(
    http: httpx2.AsyncClient, fetches: Fetches, monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    async def resolve(host: str) -> set[str]:
        return {"93.184.215.14", address}  # one private answer among public ones is enough

    monkeypatch.setattr(clients, "_resolve", resolve)

    refused = await _authorize(http, DOCUMENT_URL, _pkce()[1])

    assert refused.status_code == 400
    assert fetches.requests == []


@pytest.mark.parametrize(
    "url", ["https://app.example:8443/client.json", "https://app.example/", "https://app.example", "https://u:p@app.example/c.json"]
)
async def test_a_metadata_document_url_must_be_plain_https_on_443_with_a_path(
    http: httpx2.AsyncClient, fetches: Fetches, url: str
) -> None:
    refused = await _authorize(http, url, _pkce()[1])

    assert refused.status_code == 400
    assert fetches.requests == []


@pytest.mark.parametrize(
    "url", ["https://a..com/client.json", f"https://{'a' * 64}.example/client.json", "https://app.example:port/client.json"]
)
async def test_a_metadata_document_url_that_can_not_be_read_is_an_unknown_client(
    http: httpx2.AsyncClient, fetches: Fetches, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    # The real resolver: these names fail before any lookup leaves the machine (IDNA encoding).
    monkeypatch.setattr(clients, "_resolve", _real_resolve)

    refused = await _authorize(http, url, _pkce()[1])

    assert refused.status_code == 400 and refused.json()["error"] == "invalid_request"  # not a server_error
    assert fetches.requests == []


@pytest.mark.parametrize("hangs", ["resolver", "server"])
async def test_a_fetch_that_hangs_is_cut_at_the_time_allowed(
    http: httpx2.AsyncClient, fetches: Fetches, monkeypatch: pytest.MonkeyPatch, hangs: str
) -> None:
    monkeypatch.setattr(clients, "METADATA_DOCUMENT_TIMEOUT_SECONDS", 0.2)
    if hangs == "resolver":
        async def slow(host: str) -> set[str]:
            await asyncio.sleep(5)
            return {"93.184.215.14"}

        monkeypatch.setattr(clients, "_resolve", slow)
    else:
        fetches.delay = 5
    started = time.monotonic()

    refused = await _authorize(http, DOCUMENT_URL, _pkce()[1])

    assert refused.status_code == 400
    assert time.monotonic() - started < 2


async def test_no_database_transaction_is_open_while_the_document_is_fetched(db: AsyncSession, fetches: Fetches) -> None:
    open_during: list[bool] = []
    fetches.during = lambda: open_during.append(db.in_transaction())

    client = await clients.get_client(db, DOCUMENT_URL, client_ip="203.0.113.7")

    assert client is not None and client.client_name == "Example AI"
    assert open_during == [False]


@pytest.mark.parametrize(
    "failure",
    [httpx.Response(503), httpx.ConnectError("connection refused"), httpx.Response(404), httpx.Response(200, json=_document(client_name=None))],
)
async def test_a_failing_document_is_fetched_once_in_ten_minutes(
    http: httpx2.AsyncClient, db: AsyncSession, fetches: Fetches, failure: httpx.Response | httpx.HTTPError
) -> None:
    fetches.response = failure

    first = await _authorize(http, DOCUMENT_URL, _pkce()[1])
    again = await _authorize(http, DOCUMENT_URL, _pkce()[1])

    assert first.status_code == again.status_code == 400
    assert len(fetches.requests) == 1
    await db.execute(update(OAuthMetadataFetchFailure).values(failed_at=datetime.now(UTC) - timedelta(minutes=11)))
    await db.commit()
    fetches.response = httpx.Response(200, json=_document())
    assert (await _authorize(http, DOCUMENT_URL, _pkce()[1])).status_code == 302
    assert len(fetches.requests) == 2
    assert await db.scalar(select(OAuthMetadataFetchFailure)) is None


async def test_document_fetches_are_counted_per_address_and_a_cached_one_is_free(
    http: httpx2.AsyncClient, fetches: Fetches, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.oauth_metadata_fetch_by_ip, "max_attempts", 1)

    fetched = await _authorize(http, DOCUMENT_URL, _pkce()[1])
    another = await _authorize(http, "https://app.example/another.json", _pkce()[1])
    cached = await _authorize(http, DOCUMENT_URL, _pkce()[1])

    assert fetched.status_code == 302 and cached.status_code == 302
    assert another.status_code == 400 and another.json()["error"] == "invalid_request"  # an unknown client
    assert [str(request.url) for request in fetches.requests] == [DOCUMENT_URL]


@pytest.mark.parametrize(
    "outage", [httpx.Response(503), httpx.Response(429), httpx.ConnectError("connection refused"), httpx.ReadTimeout("slow"), "hangs"]
)
async def test_while_its_publisher_is_down_an_app_keeps_its_last_document_for_a_week(
    http: httpx2.AsyncClient, db: AsyncSession, fetches: Fetches, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
    outage: httpx.Response | httpx.HTTPError | str,
) -> None:
    assert (await _authorize(http, DOCUMENT_URL, _pkce()[1])).status_code == 302
    await db.execute(update(OAuthClient).values(fetched_at=datetime.now(UTC) - timedelta(hours=25)))
    await db.commit()
    if isinstance(outage, str):
        monkeypatch.setattr(clients, "METADATA_DOCUMENT_TIMEOUT_SECONDS", 0.2)
        fetches.delay = 5
    else:
        fetches.response = outage

    with caplog.at_level(logging.ERROR, logger=clients.__name__):
        during = await _authorize(http, DOCUMENT_URL, _pkce()[1])

    assert during.status_code == 302
    assert any(record.levelno == logging.ERROR and "Serving its copy" in record.getMessage() for record in caplog.records)
    # Past a week, the copy is too old to vouch for the app.
    await db.execute(update(OAuthClient).values(fetched_at=datetime.now(UTC) - timedelta(days=8)))
    await db.execute(delete(OAuthMetadataFetchFailure))
    await db.commit()
    assert (await _authorize(http, DOCUMENT_URL, _pkce()[1])).status_code == 400


async def test_a_refused_document_ends_its_cached_copy_but_not_its_grants(
    http: httpx2.AsyncClient, db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], fetches: Fetches
) -> None:
    acme, _ = companies
    verifier, challenge = _pkce()
    code = (await _answer(http, acme["approver"], _consent_request(await _authorize(http, DOCUMENT_URL, challenge))))["code"][0]
    tokens = (await _exchange(http, DOCUMENT_URL, code, verifier)).json()
    await db.execute(update(OAuthClient).values(fetched_at=datetime.now(UTC) - timedelta(hours=25)))
    await db.commit()
    fetches.response = httpx.Response(200, json=_document(redirect_uris=["http://evil.example/cb"]))

    refused = await _refresh(http, DOCUMENT_URL, tokens["refresh_token"])

    assert refused.status_code == 401 and refused.json()["error"] == "invalid_client"
    stored = await db.scalar(select(OAuthClient).execution_options(populate_existing=True))
    assert stored is not None and stored.fetched_at is None
    assert (await _grant(db, tokens["access_token"])).revoked_at is None  # back once the document is fixed


async def test_the_fetch_ignores_proxies_from_the_environment(
    http: httpx2.AsyncClient, fetches: Fetches, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A proxy from the environment would make the request from somewhere the address check never
    # saw. httpx ignores the environment's proxies whenever a transport is given, as the tests'
    # mock is, so what is checked is how the client is built.
    built: list[dict[str, Any]] = []

    class Recorded(httpx.AsyncClient):
        def __init__(self, **kwargs: Any) -> None:
            built.append(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(clients.httpx, "AsyncClient", Recorded)

    assert (await _authorize(http, DOCUMENT_URL, _pkce()[1])).status_code == 302
    assert [kwargs["trust_env"] for kwargs in built] == [False]
    assert built[0]["follow_redirects"] is False
