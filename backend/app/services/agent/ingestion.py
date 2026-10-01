"""What happens to a message the moment a channel hands it to us.

Webhooks return fast: this only decides what the message is (a duplicate, a forbidden sender, a
reply to a paused report, a new report...) and records that decision — a report and its job in
ONE transaction. Everything slow (download, transcription, the model, rendering) is the worker's.
"""

import asyncio
import io
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageOps
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.channel_connection import ChannelConnection
from app.models.inbound_message import InboundMessage
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.tenant import Tenant
from app.repositories.execution_log_repository import ExecutionLogRepository
from app.repositories.report_repository import PENDING_STATUSES, ReportRepository
from app.services.channels.base import IncomingMessage, OutgoingMessage
from app.services.channels.factory import get_channel_adapter
from app.services.i18n import t
from app.services.jobs.queue import RESUME, RUN, enqueue

logger = logging.getLogger(__name__)

Outcome = Literal["duplicate", "rejected", "replied", "created", "resumed", "busy"]


@dataclass(frozen=True)
class IngestResult:
    outcome: Outcome
    report_id: uuid.UUID | None = None


async def say(
    connection: ChannelConnection, recipient: str, text: str, *, meta: dict[str, Any] | None = None
) -> None:
    """Best-effort message back to a person. Failing to tell someone "I'm busy" must never
    lose the message they sent."""
    try:
        await get_channel_adapter(connection).send_message(
            OutgoingMessage(recipient_id=recipient, text=text, meta=meta or {})
        )
    except Exception:
        logger.warning("Failed to message %s on connection %s", recipient, connection.id, exc_info=True)


_PHOTO_MAX_SIDE = 1600
_ORPHAN_PHOTO_WINDOW_MINUTES = 60


def _shrink_to_jpeg(raw: bytes) -> bytes:
    """Phone photos are 3-8 MB; a report with six of them would be a 40 MB Word file. Downsizing
    here keeps the documents (and the emails that carry them) a sensible size."""
    with Image.open(io.BytesIO(raw)) as opened:
        upright = ImageOps.exif_transpose(opened).convert("RGB")
    upright.thumbnail((_PHOTO_MAX_SIDE, _PHOTO_MAX_SIDE))
    out = io.BytesIO()
    upright.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


async def _save_photo(
    db: AsyncSession, connection: ChannelConnection, incoming: IncomingMessage, report_id: uuid.UUID | None
) -> None:
    raw = await get_channel_adapter(connection).download_media(incoming.photo_reference or "")
    jpeg = await asyncio.to_thread(_shrink_to_jpeg, raw)
    folder = Path(settings.DOCUMENT_STORAGE_PATH) / "attachments" / str(connection.tenant_id)
    path = folder / f"{uuid.uuid4()}.jpg"

    def _write() -> None:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg)

    await asyncio.to_thread(_write)
    db.add(
        ReportAttachment(
            tenant_id=connection.tenant_id,
            report_id=report_id,
            sender_identifier=incoming.sender_id,
            path=str(path),
            caption=incoming.text,
        )
    )
    await db.flush()


async def _first_delivery(db: AsyncSession, connection_id: uuid.UUID, external_id: str) -> bool:
    inserted = await db.execute(
        pg_insert(InboundMessage)
        .values(connection_id=connection_id, external_id=external_id)
        .on_conflict_do_nothing(constraint="uq_inbound_messages_connection_external")
        .returning(InboundMessage.id)
    )
    return inserted.scalar_one_or_none() is not None


async def request_resume(db: AsyncSession, report: Report, reply: dict[str, Any]) -> bool:
    """Answer a paused report: claim it and queue the resume together, committed by the caller.
    False when someone else answered first (a duplicate reply, or two admins clicking)."""
    if not await ReportRepository(db).claim_for_resume(report.id):
        return False
    await enqueue(db, report_id=report.id, kind=RESUME, payload=reply)
    return True


async def create_report_with_job(
    db: AsyncSession,
    connection: ChannelConnection,
    *,
    sender_id: str,
    channel_type: str,
    text: str | None,
    media_reference: str | None,
    sender_label: str | None = None,
    sent_at: datetime | None = None,
    meta: dict[str, Any] | None = None,
) -> Report | None:
    """A new report and the job that will process it, in the caller's transaction. None when the
    sender already has one in flight (the partial unique index says so, race-safely)."""
    report = Report(
        tenant_id=connection.tenant_id,
        status="pending",
        requester_channel=channel_type,
        requester_identifier=sender_id,
        channel_connection_id=connection.id,
        received_at=sent_at or datetime.now(UTC),
        channel_meta=meta or None,
    )
    try:
        async with db.begin_nested():
            db.add(report)
            await db.flush()
    except IntegrityError:
        return None
    # People often send the pictures before the voice note: attach the ones that were waiting.
    await db.execute(
        sql_text(
            """
            UPDATE report_attachments SET report_id = :report
            WHERE tenant_id = :tenant AND sender_identifier = :sender AND report_id IS NULL
              AND created_at > now() - make_interval(mins => :window)
            """
        ),
        {"report": report.id, "tenant": connection.tenant_id, "sender": sender_id, "window": _ORPHAN_PHOTO_WINDOW_MINUTES},
    )
    await enqueue(
        db,
        report_id=report.id,
        kind=RUN,
        payload={"text": text, "media_reference": media_reference, "sender_label": sender_label},
    )
    return report


async def _handle_button(
    db: AsyncSession,
    connection: ChannelConnection,
    incoming: IncomingMessage,
    active: Report | None,
    language: str | None,
) -> IngestResult:
    """A pressed button is a structured reply to the pause it was offered in."""
    if incoming.callback_id:
        try:
            await get_channel_adapter(connection).acknowledge(incoming.callback_id)
        except Exception:
            logger.warning("Couldn't acknowledge button press %s", incoming.callback_id, exc_info=True)
    # A button on an old message, for a report that has moved on: nothing to do.
    if active is None or active.status not in PENDING_STATUSES:
        return IngestResult("replied")
    if incoming.action == "correct":  # says what to do; waits for the correction itself
        await say(connection, incoming.sender_id, t(language, "ask_correction"))
        return IngestResult("replied", active.id)
    if incoming.action in ("confirm", "cancel", "doctype"):
        reply = {"action": incoming.action, "arg": incoming.action_arg}
        if await request_resume(db, active, reply):
            return IngestResult("resumed", active.id)
    return IngestResult("busy", active.id)


async def ingest_message(
    *, db: AsyncSession, connection: ChannelConnection, incoming: IncomingMessage
) -> IngestResult:
    tenant = await db.get(Tenant, connection.tenant_id)
    language = tenant.language if tenant else None

    if incoming.external_id and not await _first_delivery(db, connection.id, incoming.external_id):
        return IngestResult("duplicate")

    allowed = connection.allowed_senders
    if (allowed and incoming.sender_id not in allowed) or (not allowed and not settings.ALLOW_ANY_SENDER):
        # The id is logged so an administrator can copy it into the allow-list.
        logger.warning(
            "Rejected message from sender %s on connection %s (not in allowed_senders)",
            incoming.sender_id,
            connection.id,
        )
        # The id the administrator must add to the allow-list: they cannot read the server logs.
        await say(connection, incoming.sender_id, t(language, "rejected_sender", sender=incoming.sender_id))
        return IngestResult("rejected")

    # Global wallet guard, checked before both paths (a correction reply extracts again).
    if settings.DAILY_SPEND_CAP_USD > 0:
        midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        if await ExecutionLogRepository(db).total_cost_since(midnight) >= settings.DAILY_SPEND_CAP_USD:
            await say(connection, incoming.sender_id, t(language, "spend_capped"))
            return IngestResult("rejected")

    if not (incoming.text or incoming.media_reference or incoming.photo_reference or incoming.action):
        key = "unsupported_message" if incoming.unsupported else "empty_message"
        await say(connection, incoming.sender_id, t(language, key))
        return IngestResult("replied")

    repo = ReportRepository(db)
    active = await repo.find_active_for_sender(
        tenant_id=connection.tenant_id, channel=incoming.channel_type, identifier=incoming.sender_id
    )

    if incoming.action:
        return await _handle_button(db, connection, incoming, active, language)

    if incoming.photo_reference:
        try:
            await _save_photo(db, connection, incoming, active.id if active else None)
        except Exception:
            logger.warning("Couldn't save a photo from %s", incoming.sender_id, exc_info=True)
            await say(connection, incoming.sender_id, t(language, "photo_failed"))
            return IngestResult("replied")
        if not (incoming.text or incoming.media_reference):  # a photo on its own: nothing more to do
            key = "photo_attached" if active else "photo_without_report"
            await say(connection, incoming.sender_id, t(language, key))
            return IngestResult("replied", active.id if active else None)

    if active is not None:
        if active.status not in PENDING_STATUSES:
            await say(connection, incoming.sender_id, t(language, "busy"))
            return IngestResult("busy", active.id)
        reply = {"text": incoming.text, "media_reference": incoming.media_reference}
        if await request_resume(db, active, reply):
            return IngestResult("resumed", active.id)
        await say(connection, incoming.sender_id, t(language, "busy"))
        return IngestResult("busy", active.id)

    # New reports only — a reply to a paused report must never be rate-limited away.
    if settings.SENDER_RATE_LIMIT_PER_HOUR > 0:
        recent = await repo.count_recent_for_sender(
            tenant_id=connection.tenant_id,
            requester_identifier=incoming.sender_id,
            since=datetime.now(UTC) - timedelta(hours=1),
        )
        if recent >= settings.SENDER_RATE_LIMIT_PER_HOUR:
            await say(connection, incoming.sender_id, t(language, "rate_limited"))
            return IngestResult("rejected")

    report = await create_report_with_job(
        db,
        connection,
        sender_id=incoming.sender_id,
        channel_type=incoming.channel_type,
        text=incoming.text,
        media_reference=incoming.media_reference,
        sender_label=incoming.sender_label,
        sent_at=incoming.sent_at,
        meta=incoming.meta,
    )
    if report is None:
        # Two messages from one sender arrived at the same instant and the other created it.
        await say(connection, incoming.sender_id, t(language, "busy"))
        return IngestResult("busy")
    return IngestResult("created", report.id)
