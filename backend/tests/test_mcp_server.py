"""The MCP server, spoken to over HTTP by the SDK's own client, the way Claude reaches it: a key is
its person and nothing more (their company, their role, a technician's own reports only), and the
one write is a draft that waits for a person."""

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import settings
from app.core.security import hash_password
from app.main import app
from app.mcp_server.server import endpoint
from app.models.api_key import ApiKey
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.job import Job
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import instance_settings

_HASH = hash_password("x")
SCHEMA = {
    "obra": {"type": "str", "label": "Obra"},  # required: fields are, unless they say otherwise
    "deficiencias": {"type": "str", "label": "Deficiencias", "required": False},
    "foto": {"type": "image", "label": "Foto"},
}


@pytest.fixture(autouse=True)
async def _running(own_sessions: None, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    async def configured(session: object = None) -> dict[str, str]:
        return {"extraction_api_key": "k"}

    monkeypatch.setattr(instance_settings, "load", configured)
    # The SDK's task group must be entered and left by one task; pytest-asyncio sets a fixture up
    # and tears it down in different ones, so the server runs in a task of its own.
    started, stop = asyncio.Event(), asyncio.Event()

    async def serve() -> None:
        async with endpoint.running():
            started.set()
            await stop.wait()

    server = asyncio.create_task(serve())
    await started.wait()
    yield
    stop.set()
    await server


# "auto" negotiates the newest protocol; "legacy" is the initialize handshake older clients (and
# today's connectors, possibly) use. Each runs the tool on a different code path in the SDK.
MODES = ["auto", "legacy"]


@asynccontextmanager
async def _connect(secret: str, mode: str = "auto") -> AsyncIterator[Client]:
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test", headers={"Authorization": f"Bearer {secret}"},
        timeout=httpx2.Timeout(30, read=60),
    )
    async with http, Client(streamable_http_client("http://test/mcp", http_client=http), mode=mode) as client:
        yield client


async def _call(secret: str, tool: str, mode: str = "auto", **arguments: Any) -> CallToolResult:
    async with _connect(secret, mode) as client:
        return await client.call_tool(tool, arguments)


def _data(result: CallToolResult) -> dict[str, Any]:
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return result.structured_content


def _error(result: CallToolResult) -> str:
    assert result.is_error, result.structured_content
    return " ".join(getattr(block, "text", "") for block in result.content)


async def _key(db: AsyncSession, user: TenantUser) -> str:
    secret = f"rpt_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    assert user.tenant_id is not None
    db.add(ApiKey(tenant_id=user.tenant_id, user_id=user.id, name="Claude", key_hash=hashlib.sha256(secret.encode()).hexdigest(), prefix=secret[:12]))
    await db.commit()
    return secret


async def _company(db: AsyncSession, name: str) -> dict[str, Any]:
    tenant = Tenant(name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    people = {
        role: TenantUser(
            tenant_id=tenant.id, email=f"{role}-{uuid.uuid4().hex[:6]}@{name.lower()}.test", hashed_password=_HASH,
            full_name=f"{name} {role}", role=role, is_active=True,
        )
        for role in ("tenant_admin", "approver", "viewer", "technician")
    }
    colleague = TenantUser(
        tenant_id=tenant.id, email=f"luis-{uuid.uuid4().hex[:6]}@{name.lower()}.test", hashed_password=_HASH,
        full_name=f"{name} Luis", role="technician", is_active=True,
    )
    visit = DocumentType(tenant_id=tenant.id, name=f"{name} visita", field_schema=SCHEMA, is_active=True)
    no_template = DocumentType(tenant_id=tenant.id, name=f"{name} sin plantilla", field_schema={}, is_active=True)
    db.add_all([*people.values(), colleague, visit, no_template])
    await db.flush()
    db.add(DocumentTemplate(tenant_id=tenant.id, document_type_id=visit.id, file_path="/nonexistent.docx", is_active=True))

    def report(by: TenantUser, site: str, status: str = "awaiting_approval") -> Report:
        return Report(
            tenant_id=tenant.id, document_type_id=visit.id, status=status, requester_channel="web",
            requester_identifier=str(by.id), requester_user_id=by.id, source_text=f"Visita a {site}.",
            extracted_fields={"obra": site, "deficiencias": None},
        )

    own, colleagues = report(people["technician"], f"{name} Norte"), report(colleague, f"{name} Sur", "delivered")
    db.add_all([own, colleagues])
    await db.commit()
    return {"tenant": tenant, "visit": visit, "no_template": no_template, "own": own, "colleagues": colleagues, "colleague": colleague, **people}


@pytest.fixture
async def companies(db: AsyncSession) -> tuple[dict[str, Any], dict[str, Any]]:
    return await _company(db, "Acme"), await _company(db, "Rival")


async def test_without_a_live_key_nothing_answers(db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]) -> None:
    acme, _ = companies
    revoked = await _key(db, acme["approver"])
    key = await db.scalar(select(ApiKey))
    assert key is not None
    key.revoked_at = datetime.now(UTC)
    await db.commit()
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}

    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as http:
        responses = [
            await http.post("/mcp", json=body, headers=headers)
            for headers in ({}, {"Authorization": "Bearer rpt_made-up"}, {"Authorization": f"Bearer {revoked}"}, {"Authorization": f"Basic {revoked}"})
        ]

    assert [r.status_code for r in responses] == [401, 401, 401, 401]
    assert responses[0].headers["WWW-Authenticate"].startswith("Bearer")


async def test_there_is_no_stream_to_open(db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]) -> None:
    acme, _ = companies
    headers = {"Authorization": f"Bearer {await _key(db, acme['approver'])}", "Accept": "text/event-stream"}

    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test", timeout=5) as http:
        responses = [await http.request(method, "/mcp", headers=headers) for method in ("GET", "DELETE")]

    # A stateless server pushes nothing; the SDK would otherwise hold an older client's GET open.
    assert [r.status_code for r in responses] == [405, 405]


async def test_the_server_offers_four_tools_and_only_one_writes(db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]) -> None:
    acme, _ = companies

    async with _connect(await _key(db, acme["viewer"])) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) == {"reportai_list_document_types", "reportai_search_reports", "reportai_get_report", "reportai_create_report_draft"}
    writers = {name for name, tool in tools.items() if not (tool.annotations and tool.annotations.read_only_hint)}
    assert writers == {"reportai_create_report_draft"}
    assert all(tool.output_schema for tool in tools.values())


async def test_document_types_are_the_company_s_that_can_make_a_report(db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]) -> None:
    acme, _ = companies

    types = _data(await _call(await _key(db, acme["technician"]), "reportai_list_document_types"))["items"]

    assert [t["name"] for t in types] == ["Acme visita"]
    assert types[0]["fields"] == [
        {"name": "obra", "label": "Obra", "type": "str", "required": True},
        {"name": "deficiencias", "label": "Deficiencias", "type": "str", "required": False},
    ]  # the photo slot is not something to dictate


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(("role", "sees"), [("approver", {"own", "colleagues"}), ("viewer", {"own", "colleagues"}), ("technician", {"own"})])
async def test_search_shows_what_the_panel_shows_that_person(
    db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], role: str, sees: set[str], mode: str
) -> None:
    acme, _ = companies

    page = _data(await _call(await _key(db, acme[role]), "reportai_search_reports", mode))

    assert {item["id"] for item in page["items"]} == {str(acme[name].id) for name in sees}
    assert page["total"] == len(sees) and page["next_offset"] is None
    assert "Rival" not in str(page)


async def test_search_filters_and_pages(db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]) -> None:
    acme, _ = companies
    secret = await _key(db, acme["approver"])

    by_words = _data(await _call(secret, "reportai_search_reports", query="Sur"))
    by_status = _data(await _call(secret, "reportai_search_reports", status="awaiting_approval"))
    first = _data(await _call(secret, "reportai_search_reports", limit=1))
    second = _data(await _call(secret, "reportai_search_reports", limit=1, offset=first["next_offset"]))

    assert [i["id"] for i in by_words["items"]] == [str(acme["colleagues"].id)]
    assert [i["id"] for i in by_status["items"]] == [str(acme["own"].id)]
    assert first["next_offset"] == 1 and second["next_offset"] is None
    assert {first["items"][0]["id"], second["items"][0]["id"]} == {str(acme["own"].id), str(acme["colleagues"].id)}
    assert first["items"][0]["url"].startswith(f"{settings.FRONTEND_ORIGIN}/admin/reports/")


async def test_a_report_in_full(db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]) -> None:
    acme, _ = companies

    report = _data(await _call(await _key(db, acme["technician"]), "reportai_get_report", report_id=str(acme["own"].id)))

    assert report["status"] == "awaiting_approval" and report["document_type"] == "Acme visita"
    assert report["fields"] == [
        {"name": "obra", "label": "Obra", "value": "Acme Norte"},
        {"name": "deficiencias", "label": "Deficiencias", "value": None},
    ]
    assert report["missing_required"] == [] and report["transcript"] == "Visita a Acme Norte."
    assert report["sender"] == "Acme technician"


@pytest.mark.parametrize(("role", "whose"), [("approver", "rival"), ("technician", "rival"), ("technician", "colleague")])
async def test_someone_else_s_report_does_not_exist(
    db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], role: str, whose: str
) -> None:
    acme, rival = companies
    target = rival["own"] if whose == "rival" else acme["colleagues"]

    message = _error(await _call(await _key(db, acme[role]), "reportai_get_report", report_id=str(target.id)))

    assert "not found" in message.lower()
    assert "Rival" not in message and "Sur" not in message


@pytest.mark.parametrize("mode", MODES)
async def test_a_draft_waits_for_a_person(db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], mode: str) -> None:
    acme, _ = companies
    secret = await _key(db, acme["technician"])
    key = await db.scalar(select(ApiKey))
    assert key is not None

    draft = _data(await _call(secret, "reportai_create_report_draft", mode, document_type_id=str(acme["visit"].id), text=" Obra Acme Este: sin deficiencias. "))

    report = await db.scalar(select(Report).where(Report.id == uuid.UUID(draft["id"])))
    assert report is not None
    assert (report.tenant_id, report.requester_user_id, report.requester_channel) == (acme["tenant"].id, acme["technician"].id, "web")
    assert report.channel_meta == {"via": "mcp", "api_key_id": str(key.id)}
    assert draft["status"] == "pending" and draft["url"].endswith(draft["id"])
    jobs = (await db.scalars(select(Job).where(Job.report_id == report.id))).all()
    assert [(job.kind, job.payload["text"], job.payload["document_type_id"]) for job in jobs] == [
        ("run", "Obra Acme Este: sin deficiencias.", str(acme["visit"].id))
    ]


@pytest.mark.parametrize(
    ("role", "type_of", "expected"),
    [
        ("viewer", "acme", "can read reports but not start them"),
        ("approver", "rival", "not found"),
        ("approver", "no_template", "no template"),
    ],
)
async def test_a_draft_is_refused_when_the_panel_would_refuse_it(
    db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], role: str, type_of: str, expected: str
) -> None:
    acme, rival = companies
    document_type = {"acme": acme["visit"], "rival": rival["visit"], "no_template": acme["no_template"]}[type_of]

    message = _error(await _call(await _key(db, acme[role]), "reportai_create_report_draft", document_type_id=str(document_type.id), text="Visita."))

    assert expected in message.lower()
    assert await db.scalar(select(Report).where(Report.source_text == "Visita.")) is None


async def test_an_empty_draft_is_refused_before_it_costs_anything(db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]) -> None:
    acme, _ = companies

    message = _error(await _call(await _key(db, acme["approver"]), "reportai_create_report_draft", document_type_id=str(acme["visit"].id), text="   \n "))

    assert "empty" in message.lower()
    assert await db.scalar(select(Report).where(Report.requester_user_id == acme["approver"].id)) is None


async def test_an_unknown_status_is_refused_with_the_valid_ones(db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]]) -> None:
    acme, _ = companies

    message = _error(await _call(await _key(db, acme["approver"]), "reportai_search_reports", status="approved"))

    assert "awaiting_approval" in message and "delivered" in message


async def test_a_draft_respects_the_company_s_plan(
    db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    acme, _ = companies
    monkeypatch.setattr(settings, "SINGLE_TENANT", False)
    acme["tenant"].plan_status = "canceled"
    await db.commit()

    message = _error(await _call(await _key(db, acme["approver"]), "reportai_create_report_draft", document_type_id=str(acme["visit"].id), text="Visita."))

    assert message and await db.scalar(select(Report).where(Report.source_text == "Visita.")) is None


async def test_drafts_and_requests_have_a_ceiling_per_person(
    db: AsyncSession, companies: tuple[dict[str, Any], dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    acme, _ = companies
    monkeypatch.setattr(rate_limit.mcp_drafts_by_user, "max_attempts", 2)
    secret = await _key(db, acme["approver"])
    args = {"document_type_id": str(acme["visit"].id), "text": "Visita."}

    async with _connect(secret) as client:
        results = [await client.call_tool("reportai_create_report_draft", args) for _ in range(3)]

    assert [r.is_error for r in results] == [False, False, True]
    assert "too many" in _error(results[2]).lower()

    monkeypatch.setattr(rate_limit.mcp_by_key, "max_attempts", 1)
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as http:
        over = await http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"Authorization": f"Bearer {secret}"})
    assert over.status_code == 429 and "Retry-After" in over.headers
