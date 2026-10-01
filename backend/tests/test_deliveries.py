"""Every copy of a finished report is tracked: what was sent, to whom, and whether it arrived. A
retry sends only what did not arrive, and a copy that keeps failing never fails the report."""

import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.channel_connection import ChannelConnection
from app.models.delivery import Delivery
from app.models.document_type import DocumentType
from app.models.job import Job
from app.models.report import Report
from app.models.tenant import Tenant
from app.services.agent.nodes.deliver import deliver_node
from app.services.agent.state import AgentState
from app.services.delivery import deliveries
from app.services.delivery import email as smtp_delivery
from app.services.delivery.deliveries import attachment_name, plan_deliveries, send_pending
from app.services.jobs import runner
from app.services.jobs.errors import PermanentJobError
from app.services.jobs.queue import DELIVER, claim_next, enqueue


@pytest.fixture
def channel(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    adapter = AsyncMock()
    monkeypatch.setattr(deliveries, "get_channel_adapter", lambda _connection: adapter)
    monkeypatch.setattr(runner, "get_channel_adapter", lambda _connection: adapter)
    return adapter


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    send = AsyncMock()
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "SMTP_FROM_ADDRESS", "informes@acme.test")
    monkeypatch.setattr(smtp_delivery.aiosmtplib, "send", send)
    return send


async def _report(db: AsyncSession, tmp_path: Path, *, channel_type: str = "telegram", sender: str = "42") -> Report:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True, language="es", timezone="Europe/Madrid")
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id, channel_type=channel_type, display_name="Bot",
        credentials={"bot_token": "t"}, allowed_senders=[], is_active=True,
    )
    doc_type = DocumentType(tenant_id=tenant.id, name="Visita de obra", field_schema={})
    db.add_all([connection, doc_type])
    await db.flush()
    pdf = tmp_path / "rendered.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    report = Report(
        tenant_id=tenant.id, status="pending", requester_channel=channel_type, requester_identifier=sender,
        channel_connection_id=connection.id, document_type_id=doc_type.id, file_path=str(pdf),
        # 23:30 UTC is already the next day in Madrid: the file is named after the local date.
        received_at=datetime(2026, 9, 30, 23, 30, tzinfo=UTC),
    )
    db.add(report)
    await db.commit()
    return report


async def _deliveries(db: AsyncSession, report: Report) -> dict[str, Delivery]:
    query = select(Delivery).where(Delivery.report_id == report.id).execution_options(populate_existing=True)
    rows = (await db.scalars(query)).all()
    return {row.destination: row for row in rows}


async def _plan(db: AsyncSession, report: Report, emails: list[str], **kwargs: Any) -> None:
    await plan_deliveries(
        db, report.id, channel_type=report.requester_channel, sender_id=report.requester_identifier,
        emails=emails, **kwargs,
    )
    await db.commit()


def test_the_attachment_is_named_after_the_document_and_safe_as_a_file_name() -> None:
    assert attachment_name("Visita de obra", date(2026, 10, 1)) == "Visita de obra 2026-10-01.pdf"
    assert attachment_name("Obra 3/B: acta", date(2026, 10, 1)) == "Obra 3-B- acta 2026-10-01.pdf"
    assert attachment_name("../", date(2026, 10, 1)) == "report 2026-10-01.pdf"


async def test_planning_twice_does_not_duplicate_copies(db: AsyncSession, tmp_path: Path) -> None:
    report = await _report(db, tmp_path)

    await _plan(db, report, ["jefe@acme.test", "jefe@acme.test"])
    await _plan(db, report, ["jefe@acme.test"])

    planned = await _deliveries(db, report)
    assert {(d.kind, d.destination) for d in planned.values()} == {("channel", "42"), ("email", "jefe@acme.test")}


async def test_someone_who_wrote_by_email_is_not_sent_a_second_copy(db: AsyncSession, tmp_path: Path) -> None:
    report = await _report(db, tmp_path, channel_type="email", sender="ana@acme.test")

    await _plan(db, report, ["Ana@acme.test", "jefe@acme.test"])

    assert set(await _deliveries(db, report)) == {"ana@acme.test", "jefe@acme.test"}
    assert (await _deliveries(db, report))["ana@acme.test"].kind == "channel"


async def test_every_copy_is_sent_in_the_tenants_language_and_recorded(
    db: AsyncSession, own_sessions: None, tmp_path: Path, channel: AsyncMock, smtp: AsyncMock
) -> None:
    report = await _report(db, tmp_path)
    await _plan(db, report, ["jefe@acme.test"])

    assert await send_pending(report.id) == []

    message = channel.send_message.await_args.args[0]
    assert (message.recipient_id, message.text) == ("42", "Tu Visita de obra está listo.")
    assert message.attachment_name == "Visita de obra 2026-10-01.pdf"
    email = smtp.await_args.args[0]
    assert (email["To"], email["Subject"]) == ("jefe@acme.test", "Visita de obra — 01/10/2026")
    sent = await _deliveries(db, report)
    assert all(d.status == "sent" and d.attempts == 1 and d.sent_at for d in sent.values())


async def test_a_retry_sends_only_the_copies_that_failed(
    db: AsyncSession, own_sessions: None, tmp_path: Path, channel: AsyncMock, smtp: AsyncMock
) -> None:
    report = await _report(db, tmp_path)
    await _plan(db, report, ["jefe@acme.test"])
    smtp.side_effect = [ConnectionRefusedError("smtp down"), None]

    failures = await send_pending(report.id)

    assert len(failures) == 1 and "jefe@acme.test" in failures[0] and "smtp down" in failures[0]
    stored = await _deliveries(db, report)
    assert (stored["42"].status, stored["jefe@acme.test"].status) == ("sent", "failed")
    assert "smtp down" in (stored["jefe@acme.test"].last_error or "")

    assert await send_pending(report.id) == []

    assert channel.send_message.await_count == 1  # the person already had theirs
    stored = await _deliveries(db, report)
    assert (stored["jefe@acme.test"].status, stored["jefe@acme.test"].attempts) == ("sent", 2)
    assert stored["jefe@acme.test"].last_error is None


async def test_without_a_pdf_there_is_nothing_to_retry(db: AsyncSession, own_sessions: None, tmp_path: Path) -> None:
    report = await _report(db, tmp_path)
    report.file_path = None
    await db.commit()

    with pytest.raises(PermanentJobError):
        await send_pending(report.id)


async def test_the_deliver_step_records_the_pdf_and_queues_a_retry_for_what_failed(
    db: AsyncSession, own_sessions: None, tmp_path: Path, channel: AsyncMock, smtp: AsyncMock
) -> None:
    report = await _report(db, tmp_path)
    pdf, doc_type_id = report.file_path, report.document_type_id
    report.file_path, report.document_type_id = None, None
    await db.commit()
    channel.send_message.side_effect = RuntimeError("telegram is down")
    state = AgentState(
        thread_id=str(report.id), tenant_id=report.tenant_id, channel_connection_id=report.channel_connection_id,
        channel_type="telegram", sender_id="42", report_id=report.id, raw_payload={},
        document_type_id=doc_type_id, rendered_pdf_path=pdf, notification_emails=["jefe@acme.test"],
        extracted_fields={"client": "García Hnos."}, evidence={"visit_date": "ayer"},
    )

    await deliver_node(state)

    await db.refresh(report)
    # IA-1: without these the panel can't offer the download or show/count the type.
    assert (report.file_path, report.document_type_id) == (pdf, doc_type_id)
    # The fields in the PDF, including any correction made when approving from the panel.
    assert (report.extracted_fields, report.evidence) == ({"client": "García Hnos."}, {"visit_date": "ayer"})
    stored = await _deliveries(db, report)
    assert (stored["42"].status, stored["jefe@acme.test"].status) == ("failed", "sent")
    job = (await db.scalars(select(Job).where(Job.report_id == report.id))).one()
    assert job.kind == DELIVER and job.run_after > datetime.now(UTC)


async def test_a_delivery_job_that_runs_out_of_attempts_leaves_the_report_delivered(
    db: AsyncSession, own_sessions: None, tmp_path: Path, channel: AsyncMock, smtp: AsyncMock
) -> None:
    report = await _report(db, tmp_path)
    report.status = "delivered"
    await _plan(db, report, ["jefe@acme.test"])
    smtp.side_effect = ConnectionRefusedError("smtp down")
    await enqueue(db, report_id=report.id, kind=DELIVER, max_attempts=1)
    await db.commit()
    job = await claim_next("test-worker")
    assert job is not None

    await runner.process(job, "test-worker")

    await db.refresh(report)
    assert report.status == "delivered"
    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert stored.status == "failed" and "smtp down" in (stored.last_error or "")
    # The person got their PDF: no "we couldn't generate your report", and no second copy.
    assert channel.send_message.await_count == 1
