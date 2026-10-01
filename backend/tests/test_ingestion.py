"""What happens to a message the moment it arrives: one transaction decides whether it is a
repeat, a stranger, noise, a reply or a new report — and records a report and its job together."""

import io
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.channel_connection import ChannelConnection
from app.models.job import Job
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.tenant import Tenant
from app.services.agent import ingestion
from app.services.agent.ingestion import ingest_message, request_resume
from app.services.channels.base import IncomingMessage


async def _connection(db: AsyncSession, *, language: str = "es", allowed: list[str] | None = None) -> ChannelConnection:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True, language=language)
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id,
        channel_type="telegram",
        display_name="Bot",
        credentials={"bot_token": "t"},
        allowed_senders=allowed if allowed is not None else [],
        is_active=True,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    return connection


def _incoming(connection: ChannelConnection, sender: str = "42", **overrides: Any) -> IncomingMessage:
    values: dict[str, Any] = {
        "channel_type": "telegram",
        "channel_connection_id": connection.id,
        "sender_id": sender,
        "text": "Visité la obra de Alicante",
        "raw_payload": {},
    }
    values.update(overrides)
    return IncomingMessage(**values)


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(ingestion, "get_channel_adapter", lambda _connection: mock)
    return mock


async def _reports(db: AsyncSession) -> list[Report]:
    return list((await db.execute(select(Report))).scalars().all())


async def _jobs(db: AsyncSession) -> list[Job]:
    return list((await db.execute(select(Job))).scalars().all())


async def test_a_new_message_creates_a_report_and_its_job_together(db: AsyncSession, adapter: AsyncMock) -> None:
    connection = await _connection(db)

    result = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, sender_label="Ana"))
    await db.commit()

    assert result.outcome == "created"
    [report] = await _reports(db)
    [job] = await _jobs(db)
    assert report.status == "pending" and report.channel_connection_id == connection.id
    assert (job.report_id, job.kind) == (report.id, "run")
    assert job.payload["text"] == "Visité la obra de Alicante" and job.payload["sender_label"] == "Ana"


async def test_a_redelivered_webhook_is_ignored(db: AsyncSession, adapter: AsyncMock) -> None:
    connection = await _connection(db)
    message = _incoming(connection, external_id="update-1")

    first = await ingest_message(db=db, connection=connection, incoming=message)
    await db.commit()
    again = await ingest_message(db=db, connection=connection, incoming=message)
    await db.commit()

    assert (first.outcome, again.outcome) == ("created", "duplicate")
    assert len(await _reports(db)) == 1 and len(await _jobs(db)) == 1
    adapter.send_message.assert_not_awaited()  # a repeat is silent: no second "busy" either


async def test_the_same_id_on_another_connection_is_a_different_message(db: AsyncSession, adapter: AsyncMock) -> None:
    one, two = await _connection(db), await _connection(db)

    a = await ingest_message(db=db, connection=one, incoming=_incoming(one, external_id="7"))
    b = await ingest_message(db=db, connection=two, incoming=_incoming(two, external_id="7"))

    assert (a.outcome, b.outcome) == ("created", "created")


async def test_a_message_while_a_report_is_running_gets_a_busy_notice_not_a_second_report(
    db: AsyncSession, adapter: AsyncMock
) -> None:
    connection = await _connection(db)
    await ingest_message(db=db, connection=connection, incoming=_incoming(connection))
    await db.commit()

    second = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, text="otra cosa"))

    assert second.outcome == "busy"
    assert len(await _reports(db)) == 1
    assert "procesando" in adapter.send_message.await_args.args[0].text  # in the tenant's language


async def test_replies_are_in_the_tenants_language(db: AsyncSession, adapter: AsyncMock) -> None:
    connection = await _connection(db, language="en")

    await ingest_message(db=db, connection=connection, incoming=_incoming(connection, text=None))

    assert "voice note" in adapter.send_message.await_args.args[0].text


async def test_noise_is_answered_politely_and_creates_nothing(db: AsyncSession, adapter: AsyncMock) -> None:
    connection = await _connection(db)

    empty = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, text=None))
    sticker = await ingest_message(
        db=db, connection=connection, incoming=_incoming(connection, text=None, unsupported=True)
    )

    assert (empty.outcome, sticker.outcome) == ("replied", "replied")
    assert await _reports(db) == [] and await _jobs(db) == []
    assert adapter.send_message.await_count == 2


async def test_a_reply_to_a_paused_report_resumes_it_instead_of_starting_another(
    db: AsyncSession, adapter: AsyncMock
) -> None:
    connection = await _connection(db)
    paused = Report(
        tenant_id=connection.tenant_id, status="awaiting_approval", requester_channel="telegram",
        requester_identifier="42", channel_connection_id=connection.id,
    )
    db.add(paused)
    await db.commit()

    result = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, text="la fecha era el martes"))
    await db.commit()

    assert (result.outcome, result.report_id) == ("resumed", paused.id)
    assert len(await _reports(db)) == 1
    await db.refresh(paused)
    assert paused.status == "pending"  # claimed while the resume is queued
    [job] = await _jobs(db)
    assert (job.kind, job.payload["text"]) == ("resume", "la fecha era el martes")


async def test_two_answers_to_one_pause_resume_it_once(db: AsyncSession, adapter: AsyncMock) -> None:
    connection = await _connection(db)
    paused = Report(
        tenant_id=connection.tenant_id, status="awaiting_approval", requester_channel="telegram",
        requester_identifier="42", channel_connection_id=connection.id,
    )
    db.add(paused)
    await db.commit()

    first = await request_resume(db, paused, {"text": "CONFIRM"})
    second = await request_resume(db, paused, {"text": "CONFIRM"})
    await db.commit()

    assert (first, second) == (True, False)
    assert len(await _jobs(db)) == 1


async def test_reports_of_different_senders_do_not_block_each_other(db: AsyncSession, adapter: AsyncMock) -> None:
    connection = await _connection(db)

    a = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, sender="1"))
    b = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, sender="2"))

    assert (a.outcome, b.outcome) == ("created", "created")


async def test_a_sender_outside_the_allow_list_is_turned_away(db: AsyncSession, adapter: AsyncMock) -> None:
    connection = await _connection(db, allowed=["7"])

    result = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, sender="99"))

    assert result.outcome == "rejected"
    assert await _reports(db) == []
    assert "enlace de invitación" in adapter.send_message.await_args.args[0].text


async def test_an_empty_allow_list_rejects_everyone_unless_explicitly_opened(
    db: AsyncSession, adapter: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SEC-5: an unconfigured channel used to accept anyone who found the bot."""
    connection = await _connection(db)
    monkeypatch.setattr(settings, "ALLOW_ANY_SENDER", False)

    closed = await ingest_message(db=db, connection=connection, incoming=_incoming(connection))
    monkeypatch.setattr(settings, "ALLOW_ANY_SENDER", True)
    opened = await ingest_message(db=db, connection=connection, incoming=_incoming(connection))

    assert (closed.outcome, opened.outcome) == ("rejected", "created")


async def test_the_allow_list_also_guards_replies(db: AsyncSession, adapter: AsyncMock) -> None:
    connection = await _connection(db, allowed=["7"])
    paused = Report(
        tenant_id=connection.tenant_id, status="awaiting_approval", requester_channel="telegram",
        requester_identifier="99", channel_connection_id=connection.id,
    )
    db.add(paused)
    await db.commit()

    result = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, sender="99"))

    assert result.outcome == "rejected"
    assert await _jobs(db) == []


def _jpeg(size: tuple[int, int] = (3000, 2000)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(out, "JPEG")
    return out.getvalue()


async def _paused(db: AsyncSession, connection: ChannelConnection, status: str = "awaiting_approval") -> Report:
    report = Report(
        tenant_id=connection.tenant_id, status=status, requester_channel="telegram",
        requester_identifier="42", channel_connection_id=connection.id,
    )
    db.add(report)
    await db.commit()
    return report


async def test_a_pressed_confirm_button_resumes_the_report_with_a_structured_reply(
    db: AsyncSession, adapter: AsyncMock
) -> None:
    connection = await _connection(db)
    paused = await _paused(db, connection)

    result = await ingest_message(
        db=db, connection=connection, incoming=_incoming(connection, text=None, action="confirm", callback_id="cb-1")
    )
    await db.commit()

    assert (result.outcome, result.report_id) == ("resumed", paused.id)
    [job] = await _jobs(db)
    assert job.payload == {"action": "confirm", "arg": None}
    adapter.acknowledge.assert_awaited_once_with("cb-1")


async def test_the_correct_button_asks_what_to_change_and_waits(db: AsyncSession, adapter: AsyncMock) -> None:
    connection = await _connection(db)
    paused = await _paused(db, connection)

    result = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, text=None, action="correct"))

    assert (result.outcome, result.report_id) == ("replied", paused.id)
    assert await _jobs(db) == []
    assert "cambiar" in adapter.send_message.await_args.args[0].text
    await db.refresh(paused)
    assert paused.status == "awaiting_approval"  # still waiting for the correction itself


async def test_a_button_on_an_old_message_changes_nothing(db: AsyncSession, adapter: AsyncMock) -> None:
    connection = await _connection(db)

    result = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, text=None, action="confirm"))

    assert result.outcome == "replied" and await _jobs(db) == [] and await _reports(db) == []
    adapter.send_message.assert_not_awaited()


async def test_a_photo_sent_first_waits_and_joins_the_report_that_follows(
    db: AsyncSession, adapter: AsyncMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))
    connection = await _connection(db)
    adapter.download_media.return_value = _jpeg()

    photo = await ingest_message(
        db=db, connection=connection, incoming=_incoming(connection, text=None, photo_reference="p1")
    )
    await db.commit()
    assert photo.outcome == "replied" and await _reports(db) == []
    waiting = (await db.execute(select(ReportAttachment))).scalars().one()
    assert waiting.report_id is None and "guardado la foto" in adapter.send_message.await_args.args[0].text

    created = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, text="Visité la obra"))
    await db.commit()

    await db.refresh(waiting)
    assert created.outcome == "created" and waiting.report_id == created.report_id


async def test_a_photo_during_a_report_is_attached_to_it(
    db: AsyncSession, adapter: AsyncMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))
    connection = await _connection(db)
    paused = await _paused(db, connection)
    adapter.download_media.return_value = _jpeg()

    result = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, text=None, photo_reference="p1"))
    await db.commit()

    attachment = (await db.execute(select(ReportAttachment))).scalars().one()
    assert (result.outcome, attachment.report_id) == ("replied", paused.id)
    assert "📎" in adapter.send_message.await_args.args[0].text and await _jobs(db) == []


async def test_saved_photos_are_shrunk_upright_jpegs(
    db: AsyncSession, adapter: AsyncMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))
    connection = await _connection(db)
    adapter.download_media.return_value = _jpeg((4000, 3000))

    await ingest_message(db=db, connection=connection, incoming=_incoming(connection, text=None, photo_reference="p1"))

    saved = (await db.execute(select(ReportAttachment))).scalars().one()
    with Image.open(saved.path) as image:
        assert image.format == "JPEG" and max(image.size) == 1600


async def test_a_photo_that_cannot_be_downloaded_is_reported_not_lost_silently(
    db: AsyncSession, adapter: AsyncMock
) -> None:
    connection = await _connection(db)
    adapter.download_media.side_effect = RuntimeError("telegram is down")

    result = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, text=None, photo_reference="p1"))

    assert result.outcome == "replied" and "descargar la foto" in adapter.send_message.await_args.args[0].text


async def test_a_sender_outside_the_allow_list_is_told_the_id_to_give_their_administrator(
    db: AsyncSession, adapter: AsyncMock
) -> None:
    connection = await _connection(db, allowed=["7"])

    result = await ingest_message(db=db, connection=connection, incoming=_incoming(connection, sender="981234"))

    assert result.outcome == "rejected"
    assert "981234" in adapter.send_message.await_args.args[0].text
    assert await _reports(db) == []


async def test_without_an_ai_model_the_sender_is_told_instead_of_getting_a_failed_report(
    db: AsyncSession, adapter: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "EXTRACTION_PROVIDER", "anthropic")
    connection = await _connection(db)

    result = await ingest_message(db=db, connection=connection, incoming=_incoming(connection))

    assert result.outcome == "rejected" and await _reports(db) == []
    assert "no está configurado" in adapter.send_message.await_args.args[0].text


async def test_a_voice_note_without_transcription_asks_for_text(
    db: AsyncSession, adapter: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "TRANSCRIPTION_API_KEY", "")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    connection = await _connection(db)

    result = await ingest_message(
        db=db, connection=connection, incoming=_incoming(connection, text=None, media_reference="voice-1")
    )

    assert result.outcome == "rejected" and await _reports(db) == []
    assert "por escrito" in adapter.send_message.await_args.args[0].text
