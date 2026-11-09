"""The landing's live demo: an anonymous visitor's dictation becomes a report in the demo company,
within a few tries per IP and a daily ceiling for everyone. Only the demo's own reports of the last
day are shown, and the worker deletes them after that. Switched off, none of it exists."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient, Response
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import public_demo
from app.core import rate_limit
from app.core.config import Settings, settings
from app.core.security import hash_password
from app.main import app
from app.models.document_type import DocumentType
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
        role="tenant_admin", is_active=True,
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


async def test_the_preview_is_the_report_s_pdf_and_nothing_is_kept(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], rendered: AsyncMock
) -> None:
    report = await _report(
        db, demo["tenant"].id, meta={"public_demo": True, "locale": "en"}, document_type_id=demo["en"].id,
        extracted_fields={"site": "Bay 3"},
    )

    response = await client.get(f"/demo/reports/{report.id}/pdf")

    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 demo"
    call = rendered.await_args.kwargs
    assert (call["document_type_id"], call["fields"], call["language"]) == (demo["en"].id, {"site": "Bay 3"}, "en")
    assert not Path(call["folder"]).exists()


async def test_no_preview_before_extraction_and_only_a_few_an_hour(
    client: AsyncClient, db: AsyncSession, demo: dict[str, Any], rendered: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit.demo_pdf_by_ip, "max_attempts", 1)
    waiting = await _report(db, demo["tenant"].id, status="pending", document_type_id=demo["es"].id)
    ready = await _report(db, demo["tenant"].id, document_type_id=demo["es"].id, extracted_fields={"site": "Nave 3"})

    assert (await client.get(f"/demo/reports/{waiting.id}/pdf")).status_code == 409  # not counted
    statuses = [(await client.get(f"/demo/reports/{ready.id}/pdf")).status_code for _ in range(2)]

    assert statuses == [200, 429] and rendered.await_count == 1


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
    for name in ("PUBLIC_DEMO_ENABLED", "PUBLIC_DEMO_USER_EMAIL", "DEMO_USER_EMAIL", "PUBLIC_DEMO_DOCUMENT_TYPE_ES", "PUBLIC_DEMO_DOCUMENT_TYPE_EN"):
        monkeypatch.delenv(name, raising=False)
    required: dict[str, Any] = {"POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p", "POSTGRES_DB": "d", "SECRET_KEY": "k"}
    complete = required | {
        "PUBLIC_DEMO_ENABLED": True, "PUBLIC_DEMO_USER_EMAIL": "live-demo@reportai.test", "DEMO_USER_EMAIL": "demo@reportai.test",
        "PUBLIC_DEMO_DOCUMENT_TYPE_ES": str(uuid.uuid4()),
    }

    assert Settings(_env_file=None, **required).PUBLIC_DEMO_ENABLED is False  # type: ignore[call-arg]
    assert Settings(_env_file=None, **complete).PUBLIC_DEMO_ENABLED is True  # type: ignore[call-arg]
    for broken in (
        {"PUBLIC_DEMO_USER_EMAIL": ""},
        # The one-click demo's account: anyone could sign in and read visitors' recordings.
        {"PUBLIC_DEMO_USER_EMAIL": "Demo@ReportAI.test"},
        {"PUBLIC_DEMO_DOCUMENT_TYPE_ES": ""},
        {"PUBLIC_DEMO_DOCUMENT_TYPE_ES": "visita-de-seguridad"},
        {"PUBLIC_DEMO_DOCUMENT_TYPE_EN": "safety-visit"},
    ):
        with pytest.raises(ValidationError, match="PUBLIC_DEMO"):
            Settings(_env_file=None, **(complete | broken))  # type: ignore[call-arg]
