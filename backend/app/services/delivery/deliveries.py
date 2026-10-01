"""Every copy of a finished report is a row in `deliveries`: the PDF back on the channel the
request came in on, and one email per notification address. Sending works from those rows and
the report alone, never from the graph's state, so the run that made the PDF, the worker's later
retries and a resend from the panel all skip the copies that already arrived — nobody gets the
same report twice, and a copy that keeps failing shows in the panel instead of failing the report."""

import logging
import re
import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import describe_exception
from app.models.channel_connection import ChannelConnection
from app.models.delivery import Delivery
from app.models.document_type import DocumentType
from app.models.report import Report
from app.models.tenant import Tenant
from app.repositories.report_repository import FINISHED_STATUSES
from app.services.branding import Branding
from app.services.channels.base import OutgoingMessage
from app.services.channels.factory import get_channel_adapter
from app.services.delivery.email import send_report_email
from app.services.i18n import format_date, t
from app.services.jobs.errors import PermanentJobError
from app.services.jobs.queue import DELIVER, enqueue

logger = logging.getLogger(__name__)

CHANNEL = "channel"
EMAIL = "email"
# The first retry of a copy that failed; the queue's backoff spaces out the ones after it.
RETRY_DELAY_SECONDS = 60


class DeliveryFailed(Exception):
    """Some copies did not arrive; the job is retried and sends only those."""


def local_day(report: Report, timezone: str) -> date:
    """The day the report is about, on the company's clock (23:30 UTC is tomorrow in Madrid)."""
    return (report.received_at or report.created_at).astimezone(ZoneInfo(timezone)).date()


def attachment_name(document_type_name: str, day: date) -> str:
    """'Visit report 2026-10-01.pdf' instead of 'rendered.pdf', safe as a file name anywhere."""
    safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", document_type_name).strip(" .-") or "report"
    return f"{safe} {day.isoformat()}.pdf"


async def outcome_status(session: AsyncSession, report_id: uuid.UUID) -> str:
    """What a finished report reads as: 'delivered' once any copy arrived, 'delivery_failed' while
    every copy that was tried failed — so a report nobody received doesn't look done."""
    copies = Delivery.report_id == report_id
    any_sent = await session.scalar(select(exists().where(copies, Delivery.status == "sent")))
    any_failed = await session.scalar(select(exists().where(copies, Delivery.status == "failed")))
    return "delivery_failed" if any_failed and not any_sent else "delivered"


async def plan_deliveries(
    session: AsyncSession, report_id: uuid.UUID, *, channel_type: str, sender_id: str, emails: list[str]
) -> None:
    """Adds a row for each copy the report must reach; copies already planned are left as they are."""
    copies = [(CHANNEL, sender_id)] + [
        (EMAIL, email)
        for email in dict.fromkeys(emails)
        # Someone who wrote to the bot by email already gets the PDF in their own thread.
        if not (channel_type == "email" and email.lower() == sender_id.lower())
    ]
    await session.execute(
        pg_insert(Delivery)
        .values([{"report_id": report_id, "kind": kind, "destination": to} for kind, to in copies])
        .on_conflict_do_nothing(constraint="uq_deliveries_report_kind_destination")
    )


async def request_resend(
    session: AsyncSession, report_id: uuid.UUID, *, delivery_id: uuid.UUID | None = None, email: str | None = None
) -> list[str]:
    """Puts copies back on the to-send list — one copy, a new address, or every copy that failed —
    and queues the job that sends them, in the caller's transaction. Returns their destinations."""
    query = update(Delivery).where(Delivery.report_id == report_id)
    if email:
        await session.execute(
            pg_insert(Delivery)
            .values(report_id=report_id, kind=EMAIL, destination=email)
            .on_conflict_do_nothing(constraint="uq_deliveries_report_kind_destination")
        )
        query = query.where(Delivery.kind == EMAIL, Delivery.destination == email)
    elif delivery_id:
        query = query.where(Delivery.id == delivery_id)
    else:
        query = query.where(Delivery.status == "failed")
    destinations = list((await session.scalars(query.values(status="pending").returning(Delivery.destination))).all())
    if destinations:
        await enqueue(session, report_id=report_id, kind=DELIVER)
    return destinations


async def send_pending(report_id: uuid.UUID) -> list[str]:
    """Sends every copy of the report that has not arrived yet, and returns one line per copy that
    failed. Each outcome is committed as it happens, so a crash halfway forgets nothing."""
    async with AsyncSessionLocal() as session:
        report = await session.get(Report, report_id)
        if report is None or not report.file_path:
            raise PermanentJobError(f"Report {report_id} has no PDF to deliver")
        tenant = await session.get(Tenant, report.tenant_id)
        assert tenant is not None
        document_type = (
            await session.get(DocumentType, report.document_type_id) if report.document_type_id else None
        )
        connection = (
            await session.get(ChannelConnection, report.channel_connection_id)
            if report.channel_connection_id
            else None
        )
        pending = (
            await session.scalars(
                select(Delivery)
                .where(Delivery.report_id == report_id, Delivery.status != "sent")
                .order_by(Delivery.created_at, Delivery.kind)
            )
        ).all()

        language = tenant.language
        name = document_type.name if document_type else t(language, "report")
        day = local_day(report, tenant.timezone)
        filename = attachment_name(name, day)

        failures = []
        for delivery in pending:
            try:
                if delivery.kind == CHANNEL:
                    if connection is None:
                        raise RuntimeError("The channel this report came in on no longer exists")
                    await get_channel_adapter(connection).send_message(
                        OutgoingMessage(
                            recipient_id=delivery.destination,
                            text=t(language, "delivered", doc_type=name),
                            attachments=[report.file_path],
                            attachment_name=filename,
                            meta=report.channel_meta or {},
                        )
                    )
                else:
                    await send_report_email(
                        to=[delivery.destination],
                        subject=t(language, "email_subject", doc_type=name, date=format_date(language, day)),
                        body=t(language, "email_body", doc_type=name),
                        attachment_path=report.file_path,
                        attachment_name=filename,
                        branding=Branding.of(tenant),
                    )
            except Exception as exc:
                logger.warning("Couldn't deliver report %s to %s", report_id, delivery.destination, exc_info=True)
                delivery.status, delivery.last_error = "failed", describe_exception(exc)[:2000]
                failures.append(f"{delivery.kind} {delivery.destination}: {delivery.last_error}")
            else:
                delivery.status, delivery.last_error, delivery.sent_at = "sent", None, datetime.now(UTC)
            delivery.attempts += 1
            await session.commit()

        # Only once the graph has finished the report: its own last step sets the first outcome.
        await session.execute(
            update(Report)
            .where(Report.id == report_id, Report.status.in_(FINISHED_STATUSES))
            .values(status=await outcome_status(session, report_id))
        )
        await session.commit()
    return failures
