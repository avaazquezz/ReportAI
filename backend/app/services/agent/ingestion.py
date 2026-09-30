"""What happens to a message the moment a channel hands it to us.

Webhooks return fast: this only decides what the message is (a duplicate, a forbidden sender, a
reply to a paused report, a new report...) and records that decision — a report and its job in
ONE transaction. Everything slow (download, transcription, the model, rendering) is the worker's.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.channel_connection import ChannelConnection
from app.models.inbound_message import InboundMessage
from app.models.report import Report
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


async def say(connection: ChannelConnection, recipient: str, text: str) -> None:
    """Best-effort message back to a person. Failing to tell someone "I'm busy" must never
    lose the message they sent."""
    try:
        await get_channel_adapter(connection).send_message(OutgoingMessage(recipient_id=recipient, text=text))
    except Exception:
        logger.warning("Failed to message %s on connection %s", recipient, connection.id, exc_info=True)


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
        await say(connection, incoming.sender_id, t(language, "rejected_sender"))
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

    report = Report(
        tenant_id=connection.tenant_id,
        status="pending",
        requester_channel=incoming.channel_type,
        requester_identifier=incoming.sender_id,
        channel_connection_id=connection.id,
        received_at=incoming.sent_at or datetime.now(UTC),
        channel_meta=incoming.meta or None,
    )
    try:
        async with db.begin_nested():
            db.add(report)
            await db.flush()
    except IntegrityError:
        # Two messages from one sender arrived at the same instant and the other created it.
        await say(connection, incoming.sender_id, t(language, "busy"))
        return IngestResult("busy")

    await enqueue(
        db,
        report_id=report.id,
        kind=RUN,
        payload={
            "text": incoming.text,
            "media_reference": incoming.media_reference,
            "sender_label": incoming.sender_label,
        },
    )
    return IngestResult("created", report.id)
