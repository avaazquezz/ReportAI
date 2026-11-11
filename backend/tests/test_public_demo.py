"""The landing's live demo: an anonymous visitor's dictation becomes a report in the demo company,
within a few tries per IP and a daily ceiling for everyone. Only the demo's own reports of the last
day are shown, and the worker deletes them after that. Switched off, none of it exists."""

import asyncio
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient, Response
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api import public_demo
from app.core import rate_limit
from app.core.config import Settings, settings
from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models.document_type import DocumentType
from app.models.execution_log import ExecutionLog
from app.models.job import Job
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import data_lifecycle, instance_settings

_HASH = hash_password("x")
_WEBM = ("note.webm", b"\x1aE\xdf\xa3 not really webm", "audio/webm;codecs=opus")
_SCHEMA = {
    "site": {"type": "str", "label": "Site"},
    "visit_date": {"type": "date", "label": "Date"},
    "notes": {"type": "str", "required": False},
}
_DEMO_META = {"public_demo": True, "locale": "es"}
_TRIES_USED = "You have used your demo tries for today."
_DEMO_FULL = "The demo is full for today. Try again tomorrow."
# A visitor at an address, with its own database session per request (see `simultaneous`).
Visitor = Callable[[str], Awaitable[AsyncClient]]


@pytest.fixture(autouse=True)
def _ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def configured(session: object = None) -> dict[str, str]:
        return {"extraction_api_key": "k", "transcription_api_key": "k"}

    monkeypatch.setattr(instance_settings, "load", configured)
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))


async def _tenant(db: AsyncSession, name: str) -> Tenant:
    tenant = Tenant(name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    return tenant


@pytest.fixture
async def demo(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    tenant = await _tenant(db, "ReportAI Demo")
    account = TenantUser(
        tenant_id=tenant.id, email="demo@reportai.test", hashed_password=_HASH, full_name="Demo technician",
        role="tenant_admin", is_active=False,  # as scripts/seed_live_demo.py makes it: nobody signs into it
    )
    spanish = DocumentType(
        tenant_id=tenant.id, name="Visita de seguridad", field_schema=_SCHEMA, notification_emails=["boss@demo.test"]
    )
    english = DocumentType(tenant_id=tenant.id, name="Safety visit", field_schema=_SCHEMA)
    db.add_all([account, spanish, english])
    await db.commit()
    monkeypatch.setattr(settings, "PUBLIC_DEMO_ENABLED", True)
    monkeypatch.setattr(settings, "PUBLIC_DEMO_USER_EMAIL", account.email)
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", "")
    monkeypatch.setattr(settings, "PUBLIC_DEMO_DOCUMENT_TYPE_ES", str(spanish.id))
    monkeypatch.setattr(settings, "PUBLIC_DEMO_DOCUMENT_TYPE_EN", str(english.id))
    # The limiters are built from the environment at import: pin them to the defaults here.
    monkeypatch.setattr(rate_limit.demo_capture_by_ip, "max_attempts", 3)
    monkeypatch.setattr(rate_limit.demo_capture_total, "max_attempts", 50)
    monkeypatch.setattr(rate_limit.demo_pdf_by_ip, "max_attempts", 10)
    return {"tenant": tenant, "account": account, "es": spanish, "en": english}


async def _try(
    client: AsyncClient, *, text: str | None = "Visita a la nave 3 de Acme esta mañana",
    audio: tuple[str, bytes, str] | None = None, locale: str | None = None,
) -> Response:
    data = {key: value for key, value in {"text": text, "locale": locale}.items() if value is not None}
    return await client.post("/demo/capture", data=data, files=[("audio", audio)] if audio else None)


async def _from(ip: str) -> Response:
    """A try from another visitor's address (the `client` fixture must be active: it points the
    app at the test database)."""
    async with AsyncClient(transport=ASGITransport(app=app, client=(ip, 4000)), base_url="http://test") as visitor:
        return await _try(visitor)


async def _report(
    db: AsyncSession, tenant_id: uuid.UUID, *, channel: str = "web", meta: dict[str, Any] | None = _DEMO_META,
    age: timedelta | None = None, status: str = "awaiting_approval", **values: Any,
) -> Report:
    report = Report(
        tenant_id=tenant_id, status=status, requester_channel=channel, requester_identifier="42",
        channel_meta=meta, **values,
    )
    db.add(report)
    await db.flush()
    if age is not None:
        await db.execute(update(Report).where(Report.id == report.id).values(created_at=datetime.now(UTC) - age))
    await db.commit()
    return report


async def _reports(db: AsyncSession) -> int:
    return int(await db.scalar(select(func.count()).select_from(Report)) or 0)


@pytest.mark.parametrize("switched_off", ["PUBLIC_DEMO_ENABLED", "PUBLIC_DEMO_USER_EMAIL", "PUBLIC_DEMO_DOCUMENT_TYPE_ES"])
async def test_the_demo_is_a_route_that_does_not_exist_unless_fully_switched_on(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch, switched_off: str
) -> None:
    report = await _report(db, demo["tenant"].id, document_type_id=demo["es"].id, extracted_fields={"site": "Nave 3"})
    monkeypatch.setattr(settings, switched_off, False if switched_off == "PUBLIC_DEMO_ENABLED" else "")
    no_such_route = await client.get("/demo/nowhere")

    answers = [
        await _try(client),
        await client.get(f"/demo/reports/{report.id}"),
        await client.get(f"/demo/reports/{report.id}/pdf"),
    ]

    assert [(a.status_code, a.json()) for a in answers] == [(404, no_such_route.json())] * 3
    assert await _reports(db) == 1


async def test_a_typed_visit_becomes_a_report_of_the_demo_company(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any]
) -> None:
    response = await _try(client)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "pending" and set(body) == {"id", "status"}
    report = await db.get(Report, uuid.UUID(body["id"]))
    assert report is not None
    assert (report.tenant_id, report.requester_channel, report.requester_user_id) == (
        demo["tenant"].id, "web", demo["account"].id
    )
    assert report.channel_meta == {"public_demo": True, "locale": "es"} and report.document_type_id == demo["es"].id
    job = await db.scalar(select(Job).where(Job.report_id == report.id))
    assert job is not None and job.kind == "run"
    assert job.payload["document_type_id"] == str(demo["es"].id)
    assert job.payload["text"] == "Visita a la nave 3 de Acme esta mañana" and job.payload["media_reference"] is None


async def test_each_language_gets_its_type_and_english_falls_back_to_spanish(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    english = await _try(client, locale="en")
    monkeypatch.setattr(settings, "PUBLIC_DEMO_DOCUMENT_TYPE_EN", "")
    fallback = await _try(client, locale="en")
    spanish = await _try(client)

    made = [await db.get(Report, uuid.UUID(answer.json()["id"])) for answer in (english, fallback, spanish)]
    assert [(r.document_type_id, (r.channel_meta or {})["locale"]) for r in made if r] == [
        (demo["en"].id, "en"), (demo["es"].id, "en"), (demo["es"].id, "es"),
    ]


async def test_a_recording_reaches_the_pipeline_whole(client: AsyncClient, db: AsyncSession, demo: dict[str, Any]) -> None:
    response = await _try(client, text=None, audio=_WEBM)

    assert response.status_code == 202, response.text
    job = await db.scalar(select(Job).where(Job.report_id == uuid.UUID(response.json()["id"])))
    assert job is not None and Path(job.payload["media_reference"]).read_bytes() == _WEBM[1]


async def test_an_empty_or_oversized_try_is_refused_and_not_counted(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit.demo_capture_by_ip, "max_attempts", 1)
    limit = public_demo.MAX_AUDIO_BYTES

    refused = [
        await _try(client, text=None),
        await _try(client, text="   "),
        await _try(client, text=None, audio=("note.webm", b"\0" * (limit + 1), "audio/webm")),
        await _try(client, text="x" * (public_demo.MAX_TEXT_CHARS + 1)),
        await _try(client, locale="fr"),
    ]
    unsupported = await _try(client, text=None, audio=("note.xyz", b"x", "audio/x-foo"))

    assert [r.status_code for r in refused] == [422] * 5, [r.text for r in refused]
    assert unsupported.status_code == 400
    assert await _reports(db) == 0
    # None of them used the visitor's only try, and a recording right at the limit is fine.
    assert (await _try(client, text=None, audio=("note.webm", b"\0" * limit, "audio/webm"))).status_code == 202


async def test_a_visitor_has_a_few_tries_a_day(client: AsyncClient, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rate_limit.demo_capture_by_ip, "max_attempts", 2)

    answers = [await _try(client) for _ in range(3)]

    assert [a.status_code for a in answers] == [202, 202, 429]
    assert answers[2].json()["detail"] == _TRIES_USED
    assert 0 < int(answers[2].headers["Retry-After"]) <= 24 * 60 * 60


async def test_the_demo_has_a_daily_ceiling_for_everyone(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit.demo_capture_by_ip, "max_attempts", 1)
    monkeypatch.setattr(rate_limit.demo_capture_total, "max_attempts", 2)

    answers = [await _from(ip) for ip in ("198.51.100.1", "198.51.100.2", "198.51.100.3")]
    again = await _from("198.51.100.1")

    assert [a.status_code for a in answers] == [202, 202, 429]
    assert answers[2].json()["detail"] == _DEMO_FULL and "Retry-After" in answers[2].headers
    assert again.status_code == 429 and again.json()["detail"] == _TRIES_USED  # their own tries, said first
    assert await _reports(db) == 2


@pytest.fixture
async def simultaneous(_test_engine: AsyncEngine, db: AsyncSession) -> AsyncGenerator[Visitor, None]:
    """Visitors whose requests run at the same time, each with its own database session as in
    production (the `client` fixture shares one session, which serializes everything)."""
    factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

    async def own_session() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = own_session
    async with AsyncExitStack() as stack:
        yield lambda ip: stack.enter_async_context(
            AsyncClient(transport=ASGITransport(app=app, client=(ip, 4000)), base_url="http://test")
        )
    app.dependency_overrides.clear()


async def test_a_burst_of_simultaneous_tries_from_one_visitor_gets_their_tries_and_no_more(
    simultaneous: Visitor, db: AsyncSession, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit.demo_capture_by_ip, "max_attempts", 3)
    visitor = await simultaneous("203.0.113.7")

    answers = await asyncio.gather(*[_try(visitor, text=f"Visita {n} a la nave 3") for n in range(20)])

    assert sorted(a.status_code for a in answers) == [202] * 3 + [429] * 17
    assert await _reports(db) == 3


async def test_a_burst_of_simultaneous_tries_from_everyone_stops_at_the_daily_ceiling(
    simultaneous: Visitor, db: AsyncSession, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit.demo_capture_total, "max_attempts", 5)
    visitors = [await simultaneous(f"198.51.100.{n}") for n in range(1, 21)]

    answers = await asyncio.gather(*[_try(visitor) for visitor in visitors])

    assert sorted(a.status_code for a in answers) == [202] * 5 + [429] * 15
    assert {a.json()["detail"] for a in answers if a.status_code == 429} == {_DEMO_FULL}
    assert await _reports(db) == 5


async def test_one_ipv6_network_is_one_visitor(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A /64 is what one home or one server gets: changing the last bits must not buy more tries.
    monkeypatch.setattr(rate_limit.demo_capture_by_ip, "max_attempts", 1)

    first, sibling, elsewhere = [await _from(ip) for ip in ("2001:db8:1:2::1", "2001:db8:1:2:ffff::9", "2001:db8:1:3::1")]

    assert [first.status_code, sibling.status_code, elsewhere.status_code] == [202, 429, 202]


async def test_the_demo_stops_for_the_day_once_it_has_spent_its_own_budget(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Long recordings cost more than the average try: the ceiling on tries alone doesn't bound it.
    monkeypatch.setattr(settings, "PUBLIC_DEMO_DAILY_SPEND_USD", 1.0)
    monkeypatch.setattr(settings, "DAILY_SPEND_CAP_USD", 0)  # the platform's breaker is another test's
    db.add(ExecutionLog(tenant_id=demo["tenant"].id, step="extract", status="success", cost_usd=0.6))
    db.add(ExecutionLog(tenant_id=(await _tenant(db, "Acme")).id, step="extract", status="success", cost_usd=5.0))
    await db.commit()
    under = await _try(client)

    db.add(ExecutionLog(tenant_id=demo["tenant"].id, step="extract", status="success", cost_usd=0.4))
    await db.commit()
    over = await _try(client)

    assert under.status_code == 202  # another company's spend is not the demo's
    assert over.status_code == 429 and over.json()["detail"] == _DEMO_FULL
    assert await _reports(db) == 1


async def test_a_type_outside_the_demo_company_fails_loud_and_makes_nothing(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    foreign = DocumentType(tenant_id=(await _tenant(db, "Acme")).id, name="Acme visit", field_schema={})
    db.add(foreign)
    await db.commit()
    monkeypatch.setattr(settings, "PUBLIC_DEMO_DOCUMENT_TYPE_ES", str(foreign.id))

    with pytest.raises(RuntimeError, match="not an active type of the demo company"):
        await _try(client)

    assert await _reports(db) == 0


async def test_the_one_click_demo_s_company_is_refused_so_visitors_never_see_each_other(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A second account in the live demo's company, set as the one-click demo anyone can sign into.
    db.add(TenantUser(
        tenant_id=demo["tenant"].id, email="open-demo@reportai.test", hashed_password=_HASH,
        full_name="Open demo", role="viewer", is_active=True,
    ))
    await db.commit()
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", "open-demo@reportai.test")

    with pytest.raises(RuntimeError, match="one-click demo"):
        await _try(client)

    assert await _reports(db) == 0


async def test_only_the_demo_s_own_reports_of_the_last_day_are_shown(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any]
) -> None:
    other = await _tenant(db, "Acme")
    fields = {"extracted_fields": {"site": "Nave 3"}}
    hidden = {
        "another company's, even with the meta": await _report(db, other.id, **fields),
        "the demo company's own, without it": await _report(db, demo["tenant"].id, meta=None, **fields),
        "a chat message can't pass for one": await _report(db, demo["tenant"].id, channel="telegram", **fields),
        "more than a day old": await _report(db, demo["tenant"].id, age=timedelta(hours=25), **fields),
    }
    shown = await _report(db, demo["tenant"].id, age=timedelta(hours=23), document_type_id=demo["es"].id, **fields)

    for why, report in hidden.items():
        for path in (f"/demo/reports/{report.id}", f"/demo/reports/{report.id}/pdf"):
            assert (await client.get(path)).status_code == 404, f"{why}: {path}"
    assert (await client.get(f"/demo/reports/{uuid.uuid4()}")).status_code == 404
    assert (await client.get(f"/demo/reports/{shown.id}")).status_code == 200


@pytest.mark.parametrize(
    ("status", "shown"),
    [
        ("pending", "processing"),
        ("awaiting_approval", "ready"),
        ("delivered", "ready"),
        ("failed", "failed"),
        ("cancelled", "failed"),
    ],
)
async def test_the_page_is_told_how_far_the_report_got(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], status: str, shown: str
) -> None:
    report = await _report(db, demo["tenant"].id, status=status, document_type_id=demo["es"].id)

    body = (await client.get(f"/demo/reports/{report.id}")).json()

    assert body["status"] == shown
    assert body["fields"] is None and body["missing"] == [] and body["field_schema"] == _SCHEMA


async def test_a_ready_report_shows_what_was_understood_and_what_is_missing(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any]
) -> None:
    report = await _report(
        db, demo["tenant"].id, document_type_id=demo["es"].id, source_text="Visita a la nave 3",
        extracted_fields={"site": "Nave 3", "visit_date": None, "notes": None}, evidence={"site": "la nave 3"},
    )

    response = await client.get(f"/demo/reports/{report.id}")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "document_type": "Visita de seguridad",
        "transcript": "Visita a la nave 3",
        "fields": {"site": "Nave 3", "visit_date": None, "notes": None},
        "evidence": {"site": "la nave 3"},
        "field_schema": _SCHEMA,
        "missing": ["visit_date"],  # notes is optional
    }
    for private in (demo["tenant"].id, demo["tenant"].name, demo["account"].email, demo["es"].id, "boss@demo.test"):
        assert str(private) not in response.text


@pytest.fixture
def rendered(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    async def _render(*, folder: str, **_: Any) -> str:
        pdf = Path(folder) / "rendered.pdf"
        pdf.write_bytes(b"%PDF-1.4 demo")
        return str(pdf)

    mock = AsyncMock(side_effect=_render)
    monkeypatch.setattr(public_demo, "render_report_pdf", mock)
    return mock


async def test_the_preview_is_the_report_s_pdf_rendered_once_and_kept_with_the_report(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], rendered: AsyncMock, tmp_path: Path
) -> None:
    report = await _report(
        db, demo["tenant"].id, meta={"public_demo": True, "locale": "en"}, document_type_id=demo["en"].id,
        extracted_fields={"site": "Bay 3"},
    )

    answers = [await client.get(f"/demo/reports/{report.id}/pdf") for _ in range(3)]

    assert all(a.status_code == 200 and a.headers["content-type"] == "application/pdf" for a in answers)
    assert {a.content for a in answers} == {b"%PDF-1.4 demo"}
    assert rendered.await_count == 1  # Gotenberg once, however often the visitor opens it
    call = rendered.await_args.kwargs
    assert (call["document_type_id"], call["fields"], call["language"]) == (demo["en"].id, {"site": "Bay 3"}, "en")
    assert not Path(call["folder"]).exists()
    # In the report's folder, which the purge deletes with the report (see the purge test).
    assert [p.name for p in (tmp_path / str(report.id)).iterdir()] == ["demo-preview.pdf"]


async def test_no_preview_before_extraction_and_only_a_few_renders_an_hour(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], rendered: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit.demo_pdf_by_ip, "max_attempts", 1)
    waiting = await _report(db, demo["tenant"].id, status="pending", document_type_id=demo["es"].id)
    first, second = [
        await _report(db, demo["tenant"].id, document_type_id=demo["es"].id, extracted_fields={"site": f"Nave {n}"})
        for n in (3, 4)
    ]

    asked = [first.id, second.id, first.id]  # read now: a refusal rolls back the shared session

    assert (await client.get(f"/demo/reports/{waiting.id}/pdf")).status_code == 409  # not counted
    statuses = [(await client.get(f"/demo/reports/{report_id}/pdf")).status_code for report_id in asked]

    assert statuses == [200, 429, 200] and rendered.await_count == 1  # the kept one costs no render


async def test_the_purge_deletes_the_demo_s_day_old_reports_and_nothing_else(
    db: AsyncSession, demo: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forgotten: list[str] = []

    async def forget(thread_id: str) -> None:
        still_there = await db.scalar(select(func.count()).select_from(Report).where(Report.id == uuid.UUID(thread_id)))
        assert still_there, "checkpoints must go before the rows that lead to them"
        forgotten.append(thread_id)

    monkeypatch.setattr(data_lifecycle, "get_checkpointer", lambda: SimpleNamespace(adelete_thread=forget))

    def put(relative: str) -> Path:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")
        return path

    tenant_id = demo["tenant"].id
    expired = await _report(db, tenant_id, age=timedelta(hours=25))
    gone = {
        "audio": put(f"{expired.id}/audio.webm"),
        "pdf": put(f"{expired.id}/rendered.pdf"),
        "preview": put(f"{expired.id}/demo-preview.pdf"),
        "upload": put("inbound_tmp/expired.webm"),
        "photo": put(f"attachments/{tenant_id}/expired.jpg"),
    }
    await db.execute(update(Report).where(Report.id == expired.id).values(audio_path=str(gone["audio"])))
    fresh = await _report(db, tenant_id, age=timedelta(hours=23))
    own = await _report(db, tenant_id, meta=None, age=timedelta(days=3))
    chat = await _report(db, tenant_id, channel="telegram", age=timedelta(days=3))
    kept = [put(f"{report.id}/audio.webm") for report in (fresh, own, chat)] + [put("inbound_tmp/fresh.webm")]
    db.add_all([
        Job(report_id=expired.id, kind="run", payload={"text": None, "media_reference": str(gone["upload"])}),
        Job(report_id=fresh.id, kind="run", payload={"text": None, "media_reference": str(kept[-1])}),
        ReportAttachment(tenant_id=tenant_id, report_id=expired.id, sender_identifier="42", path=str(gone["photo"])),
    ])
    await db.commit()

    assert await data_lifecycle.purge_expired_public_demo_reports(db) == 1
    await db.commit()

    assert forgotten == [str(expired.id)]
    assert set(await db.scalars(select(Report.id))) == {fresh.id, own.id, chat.id}
    assert list(await db.scalars(select(Job.report_id))) == [fresh.id]
    assert await db.scalar(select(func.count()).select_from(ReportAttachment)) == 0
    assert not any(path.exists() for path in gone.values()) and not (tmp_path / str(expired.id)).exists()
    assert all(path.exists() for path in kept)
    assert await data_lifecycle.purge_expired_public_demo_reports(db) == 0  # safe to run again


def test_the_demo_is_off_by_default_and_will_not_start_half_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PUBLIC_DEMO_ENABLED", "PUBLIC_DEMO_USER_EMAIL", "DEMO_USER_EMAIL", "PUBLIC_DEMO_DOCUMENT_TYPE_ES",
        "PUBLIC_DEMO_DOCUMENT_TYPE_EN", "PUBLIC_DEMO_DAILY_SPEND_USD", "DAILY_SPEND_CAP_USD", "SINGLE_TENANT",
    ):
        monkeypatch.delenv(name, raising=False)
    required: dict[str, Any] = {"POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p", "POSTGRES_DB": "d", "SECRET_KEY": "k"}
    complete = required | {
        "PUBLIC_DEMO_ENABLED": True, "PUBLIC_DEMO_USER_EMAIL": "live-demo@reportai.test", "DEMO_USER_EMAIL": "demo@reportai.test",
        "PUBLIC_DEMO_DOCUMENT_TYPE_ES": str(uuid.uuid4()),
    }

    assert Settings(_env_file=None, **required).PUBLIC_DEMO_ENABLED is False  # type: ignore[call-arg]
    assert Settings(_env_file=None, **complete).PUBLIC_DEMO_ENABLED is True  # type: ignore[call-arg]
    assert Settings(_env_file=None, **(complete | {"DAILY_SPEND_CAP_USD": 10.0})).DAILY_SPEND_CAP_USD == 10.0  # type: ignore[call-arg]
    for broken in (
        # A company's own server has no landing: the demo would spend its AI on strangers.
        {"SINGLE_TENANT": True},
        # The demo alone would trip the platform's breaker and stop every company for the day.
        {"DAILY_SPEND_CAP_USD": 2.0},
        {"PUBLIC_DEMO_USER_EMAIL": ""},
        # The one-click demo's account: anyone could sign in and read visitors' recordings.
        {"PUBLIC_DEMO_USER_EMAIL": "Demo@ReportAI.test"},
        {"PUBLIC_DEMO_DOCUMENT_TYPE_ES": ""},
        {"PUBLIC_DEMO_DOCUMENT_TYPE_ES": "visita-de-seguridad"},
        {"PUBLIC_DEMO_DOCUMENT_TYPE_EN": "safety-visit"},
    ):
        with pytest.raises(ValidationError, match="PUBLIC_DEMO"):
            Settings(_env_file=None, **(complete | broken))  # type: ignore[call-arg]
