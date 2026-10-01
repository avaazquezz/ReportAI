"""The panel's review of a report: everything on one page, approve with corrections, reject with a
reason, correct a delivered report and regenerate it, preview, send again, and the history's
search, filters and CSV export."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import reports as reports_api
from app.core.security import hash_password
from app.models.channel_connection import ChannelConnection
from app.models.delivery import Delivery
from app.models.document_type import DocumentType
from app.models.execution_log import ExecutionLog
from app.models.job import Job
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.sender_invite import SenderInvite
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser

SCHEMA = {
    "client": {"type": "str", "label": "Cliente", "required": True},
    "visit_date": {"type": "date", "label": "Fecha de visita", "required": True},
    "notes": {"type": "str", "required": False},
}


class Panel:
    def __init__(self, client: AsyncClient, db: AsyncSession, user: TenantUser, document_type: DocumentType) -> None:
        self.client, self.db, self.user, self.document_type = client, db, user, document_type
        self.headers: dict[str, str] = {}

    async def report(self, **values: Any) -> Report:
        connection = ChannelConnection(
            tenant_id=self.user.tenant_id, channel_type="telegram", display_name="Bot",
            credentials={"bot_token": "t"}, allowed_senders=[], is_active=True,
        )
        self.db.add(connection)
        await self.db.flush()
        report = Report(
            tenant_id=self.user.tenant_id, requester_channel="telegram", channel_connection_id=connection.id,
            **{"requester_identifier": "42", "status": "awaiting_approval", "document_type_id": self.document_type.id, "extracted_fields": {"client": "García", "visit_date": "2026-09-30", "notes": None},
               "evidence": {"client": "para García", "visit_date": "ayer"}, **values},
        )
        self.db.add(report)
        await self.db.commit()
        return report

    async def call(self, method: str, url: str, **kwargs: Any) -> Any:
        return await self.client.request(method, url, headers=self.headers, **kwargs)


@pytest.fixture
async def panel(client: AsyncClient, db: AsyncSession) -> Panel:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True, language="es", timezone="Europe/Madrid")
    db.add(tenant)
    await db.flush()
    user = TenantUser(
        tenant_id=tenant.id, email=f"admin-{tenant.slug}@acme.test", hashed_password=hash_password("correct-password"),
        full_name="Marta Admin", role="tenant_admin", is_active=True,
    )
    document_type = DocumentType(tenant_id=tenant.id, name="Visita de obra", field_schema=SCHEMA)
    db.add_all([user, document_type])
    await db.commit()
    p = Panel(client, db, user, document_type)
    login = await client.post("/auth/login", json={"email": user.email, "password": "correct-password"})
    p.headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return p


@pytest.fixture
def rendered(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    async def _render(*, folder: str, **_: Any) -> str:
        Path(folder).mkdir(parents=True, exist_ok=True)
        pdf = Path(folder) / "rendered.pdf"
        pdf.write_bytes(b"%PDF-1.4 new")
        return str(pdf)

    mock = AsyncMock(side_effect=_render)
    monkeypatch.setattr(reports_api, "render_report_pdf", mock)
    return mock


async def test_the_detail_has_everything_a_reviewer_needs(panel: Panel, tmp_path: Path) -> None:
    report = await panel.report(source_text="Visita para García ayer", audio_path=str(tmp_path / "a.ogg"))
    photo = ReportAttachment(tenant_id=report.tenant_id, report_id=report.id, sender_identifier="42", path="x.jpg")
    panel.db.add_all([
        photo,
        ExecutionLog(tenant_id=report.tenant_id, report_id=report.id, step="extract", status="success", cost_usd=0.002),
        Delivery(report_id=report.id, kind="email", destination="jefe@acme.test", status="failed", last_error="550"),
    ])
    await panel.db.commit()

    body = (await panel.call("GET", f"/reports/{report.id}")).json()

    assert body["source_text"] == "Visita para García ayer"
    assert body["audio_url"] == f"/reports/{report.id}/audio"
    assert body["extracted_fields"]["client"] == "García" and body["evidence"]["client"] == "para García"
    assert body["field_schema"] == SCHEMA and body["document_type_name"] == "Visita de obra"
    assert [p["url"] for p in body["photos"]] == [f"/reports/{report.id}/photos/{photo.id}"]
    assert [(s["step"], s["cost_usd"]) for s in body["steps"]] == [("extract", 0.002)]
    assert [(d["destination"], d["status"], d["last_error"]) for d in body["deliveries"]] == [("jefe@acme.test", "failed", "550")]


async def test_approving_with_corrections_resumes_with_them_and_records_who_changed_what(panel: Panel) -> None:
    report = await panel.report()

    response = await panel.call("POST", f"/reports/{report.id}/approve", json={"fields": {"client": "García Hnos.", "notes": None}})

    assert response.status_code == 202
    job = (await panel.db.scalars(select(Job).where(Job.report_id == report.id))).one()
    assert job.payload == {"action": "confirm", "fields": {"client": "García Hnos."}}  # notes did not change
    [revision] = response.json()["revisions"]
    assert revision["action"] == "approve" and revision["user_name"] == "Marta Admin"
    assert revision["changes"] == {"client": {"from": "García", "to": "García Hnos."}}


async def test_a_correction_that_does_not_fit_is_refused_with_the_fields_label(panel: Panel) -> None:
    report = await panel.report()

    response = await panel.call("POST", f"/reports/{report.id}/approve", json={"fields": {"visit_date": "el martes"}})

    assert response.status_code == 400 and "Fecha de visita" in response.json()["detail"]
    assert (await panel.db.scalars(select(Job))).all() == []


async def test_a_report_with_required_fields_missing_cannot_be_approved(panel: Panel) -> None:
    report = await panel.report(extracted_fields={"client": "García", "visit_date": None})

    missing = await panel.call("POST", f"/reports/{report.id}/approve")
    filled = await panel.call("POST", f"/reports/{report.id}/approve", json={"fields": {"visit_date": "2026-09-30"}})

    assert missing.status_code == 400 and "Fecha de visita" in missing.json()["detail"]
    assert filled.status_code == 202


async def test_rejecting_records_the_reason_and_tells_the_requester(panel: Panel, monkeypatch: pytest.MonkeyPatch) -> None:
    report = await panel.report()
    say = AsyncMock()
    monkeypatch.setattr(reports_api, "say", say)

    response = await panel.call("POST", f"/reports/{report.id}/reject", json={"reason": "El cliente no es este"})

    body = response.json()
    assert (body["status"], body["reject_reason"]) == ("failed", "El cliente no es este")
    assert body["revisions"][0]["action"] == "reject"
    assert say.await_args.args[1:] == ("42", "Tu informe ha sido rechazado en la revisión. Motivo: El cliente no es este")


async def test_correcting_a_delivered_report_regenerates_its_pdf_without_sending_it(
    panel: Panel, rendered: AsyncMock, tmp_path: Path
) -> None:
    report = await panel.report(status="delivered", file_path=str(tmp_path / "r" / "rendered.pdf"))

    response = await panel.call("PATCH", f"/reports/{report.id}/fields", json={"fields": {"client": "García Hnos."}})

    assert response.status_code == 200
    body = response.json()
    assert body["extracted_fields"]["client"] == "García Hnos."
    assert "client" not in body["evidence"] and body["evidence"]["visit_date"] == "ayer"
    assert rendered.await_args.kwargs["fields"]["client"] == "García Hnos."
    assert rendered.await_args.kwargs["folder"] == str(tmp_path / "r")
    assert body["revisions"][0]["action"] == "edit"
    assert (await panel.db.scalars(select(Job))).all() == []  # resending is a separate decision


async def test_saving_without_changes_only_regenerates(panel: Panel, rendered: AsyncMock, tmp_path: Path) -> None:
    report = await panel.report(status="delivered", file_path=str(tmp_path / "rendered.pdf"))

    body = (await panel.call("PATCH", f"/reports/{report.id}/fields", json={"fields": {}})).json()

    assert body["revisions"][0]["action"] == "rerender" and body["revisions"][0]["changes"] is None


async def test_a_paused_report_is_corrected_by_approving_it_not_by_editing(panel: Panel, rendered: AsyncMock) -> None:
    report = await panel.report()

    response = await panel.call("PATCH", f"/reports/{report.id}/fields", json={"fields": {"client": "X"}})

    assert response.status_code == 409
    rendered.assert_not_awaited()


async def test_the_preview_renders_the_edits_without_saving_them(panel: Panel, rendered: AsyncMock) -> None:
    report = await panel.report()

    response = await panel.call("POST", f"/reports/{report.id}/preview", json={"fields": {"client": "Otro"}})

    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 new"
    assert rendered.await_args.kwargs["fields"]["client"] == "Otro"
    await panel.db.refresh(report)
    assert report.extracted_fields is not None and report.extracted_fields["client"] == "García"


async def test_resending_puts_the_failed_copies_back_and_can_add_an_address(panel: Panel, tmp_path: Path) -> None:
    report = await panel.report(status="delivered", file_path=str(tmp_path / "rendered.pdf"))
    panel.db.add_all([
        Delivery(report_id=report.id, kind="channel", destination="42", status="sent"),
        Delivery(report_id=report.id, kind="email", destination="jefe@acme.test", status="failed"),
    ])
    await panel.db.commit()

    failed = await panel.call("POST", f"/reports/{report.id}/resend")
    extra = await panel.call("POST", f"/reports/{report.id}/resend", json={"email": "cliente@garcia.test"})

    assert failed.status_code == extra.status_code == 202
    statuses = {d["destination"]: d["status"] for d in extra.json()["deliveries"]}
    assert statuses == {"42": "sent", "jefe@acme.test": "pending", "cliente@garcia.test": "pending"}
    assert sorted(r["note"] for r in extra.json()["revisions"]) == ["cliente@garcia.test", "jefe@acme.test"]
    jobs = (await panel.db.scalars(select(Job).where(Job.report_id == report.id))).all()
    assert [job.kind for job in jobs] == ["deliver", "deliver"]


async def test_nothing_to_resend_is_a_conflict(panel: Panel, tmp_path: Path) -> None:
    report = await panel.report(status="delivered", file_path=str(tmp_path / "rendered.pdf"))

    assert (await panel.call("POST", f"/reports/{report.id}/resend")).status_code == 409


async def test_the_history_searches_names_in_the_fields_and_filters_by_type_and_date(panel: Panel) -> None:
    now = datetime.now(UTC)
    garcia = await panel.report(status="delivered")
    await panel.report(status="delivered", extracted_fields={"client": "Pérez"}, document_type_id=None)
    old = await panel.report(status="delivered", extracted_fields={"client": "García viejo"})
    old.created_at = now - timedelta(days=40)
    await panel.db.commit()

    found = (await panel.call("GET", "/reports", params={"q": "garcía"})).json()
    recent = (await panel.call("GET", "/reports", params={
        "q": "garcía", "document_type_id": str(panel.document_type.id), "created_from": (now - timedelta(days=7)).isoformat(),
    })).json()
    wildcard = (await panel.call("GET", "/reports", params={"q": "%"})).json()

    assert found["total"] == 2
    assert [item["id"] for item in recent["items"]] == [str(garcia.id)]
    assert wildcard["total"] == 0  # a % typed in the box is a character, not "everything"


async def test_the_csv_has_a_column_per_field_and_cannot_smuggle_formulas(panel: Panel) -> None:
    await panel.report(status="delivered", extracted_fields={"client": "=HYPERLINK(\"http://x\")", "visit_date": "2026-09-30"})

    response = await panel.call("GET", "/reports/export.csv", params={"document_type_id": str(panel.document_type.id)})

    assert response.status_code == 200 and response.text.startswith("﻿")
    lines = response.text.lstrip("﻿").splitlines()
    assert lines[0].endswith("Cliente,Fecha de visita,Notes")
    assert "'=HYPERLINK" in lines[1] and "30/09/2026" in lines[1]


async def test_photos_and_audio_are_only_served_for_their_own_report(panel: Panel, tmp_path: Path) -> None:
    picture = tmp_path / "p.jpg"
    picture.write_bytes(b"jpeg")
    report = await panel.report(audio_path=str(tmp_path / "missing.ogg"))
    other = await panel.report(status="delivered")
    photo = ReportAttachment(tenant_id=report.tenant_id, report_id=report.id, sender_identifier="42", path=str(picture))
    panel.db.add(photo)
    await panel.db.commit()

    assert (await panel.call("GET", f"/reports/{report.id}/photos/{photo.id}")).content == b"jpeg"
    assert (await panel.call("GET", f"/reports/{other.id}/photos/{photo.id}")).status_code == 404
    assert (await panel.call("GET", f"/reports/{other.id}/audio")).status_code == 404



async def test_a_report_shows_the_name_its_sender_joined_with(panel: Panel) -> None:
    named = await panel.report(status="delivered")
    unnamed = await panel.report(status="failed", requester_identifier="99")
    panel.db.add(SenderInvite(
        tenant_id=named.tenant_id, connection_id=named.channel_connection_id, label="Ana Ruiz", code_hash=uuid.uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(days=1), used_at=datetime.now(UTC), sender_id="42",
    ))
    await panel.db.commit()

    listed = {r["id"]: r["requester_name"] for r in (await panel.call("GET", "/reports")).json()["items"]}
    detail = (await panel.call("GET", f"/reports/{named.id}")).json()

    assert listed == {str(named.id): "Ana Ruiz", str(unnamed.id): None}
    assert detail["requester_name"] == "Ana Ruiz"


async def test_a_failed_report_runs_again_from_the_message_that_started_it(panel: Panel) -> None:
    report = await panel.report(status="failed", error_detail="Transcription timed out", completed_at=datetime.now(UTC))
    panel.db.add(Job(report_id=report.id, kind="run", payload={"media_reference": "file-1", "sender_label": "Ana"}, status="failed"))
    await panel.db.commit()

    response = await panel.call("POST", f"/reports/{report.id}/retry")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending" and body["error_detail"] is None
    assert body["revisions"][-1]["action"] == "retry" and body["revisions"][-1]["user_name"] == "Marta Admin"
    queued = (await panel.db.scalars(select(Job).where(Job.report_id == report.id, Job.status == "queued"))).one()
    assert (queued.kind, queued.payload) == ("run", {"media_reference": "file-1", "sender_label": "Ana"})


async def test_a_rejected_report_or_a_busy_sender_cannot_be_retried(panel: Panel) -> None:
    rejected = await panel.report(status="failed", error_detail="Rejected by admin")
    failed = await panel.report(status="failed", error_detail="boom")
    for report in (rejected, failed):
        panel.db.add(Job(report_id=report.id, kind="run", payload={"text": "hola"}, status="failed"))
    await panel.report(status="awaiting_details")  # the same sender is already busy with another one
    await panel.db.commit()

    assert (await panel.call("POST", f"/reports/{rejected.id}/retry")).status_code == 409
    busy = await panel.call("POST", f"/reports/{failed.id}/retry")
    assert busy.status_code == 409 and "another report" in busy.json()["detail"]
    assert (await panel.db.get(Report, failed.id)).status == "failed"  # type: ignore[union-attr]
