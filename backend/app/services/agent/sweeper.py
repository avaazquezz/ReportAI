"""Stuck-report sweep (OPS-3, stopgap until the durable job queue of a later phase).

The pipeline runs in a FastAPI BackgroundTask inside the API process, so a deploy or a
crash kills in-flight reports and leaves them 'pending' forever — the sender never hears
back. This marks them failed and tells the sender, which at least turns silence into an
answer."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import log_context
from app.models.channel_connection import ChannelConnection
from app.models.execution_log import ExecutionLog
from app.models.report import Report
from app.services.channels.base import OutgoingMessage
from app.services.channels.factory import get_channel_adapter

logger = logging.getLogger(__name__)

_SWEEP_INTERVAL_SECONDS = 60
_STUCK_MESSAGE = (
    "Sorry, your report didn't finish (the service was interrupted). Please send it again."
)


async def fail_stuck_reports(*, older_than: timedelta) -> int:
    """Mark 'pending' reports with no activity for `older_than` as failed and notify their
    senders. Returns how many were swept.

    Only 'pending' — the paused statuses wait on a human, which is not being stuck. Activity
    is the later of the report's last update and its latest pipeline step, so a slow run
    that keeps finishing steps is left alone. One UPDATE ... RETURNING claims each report
    for exactly one sweeper even with several workers sweeping at once."""
    cutoff = func.now() - older_than
    last_step = (
        select(func.max(ExecutionLog.created_at)).where(ExecutionLog.report_id == Report.id).scalar_subquery()
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Report)
            .where(
                Report.status == "pending",
                func.greatest(Report.updated_at, func.coalesce(last_step, Report.updated_at)) < cutoff,
            )
            .values(
                status="failed",
                error_detail=f"Interrupted: no progress for {int(older_than.total_seconds() // 60)} minutes",
                completed_at=func.now(),
            )
            .returning(Report.id, Report.tenant_id, Report.requester_channel, Report.requester_identifier)
        )
        swept = result.all()
        await session.commit()

    for report_id, tenant_id, channel, recipient in swept:
        with log_context(report_id=report_id, tenant_id=tenant_id):
            logger.warning("Marked stuck report as failed")
        await _notify_best_effort(tenant_id=tenant_id, channel=channel, recipient=recipient)
    return len(swept)


async def _notify_best_effort(*, tenant_id: object, channel: str, recipient: str) -> None:
    try:
        async with AsyncSessionLocal() as session:
            connection = (
                await session.execute(
                    select(ChannelConnection)
                    .where(
                        ChannelConnection.tenant_id == tenant_id,
                        ChannelConnection.channel_type == channel,
                        ChannelConnection.is_active.is_(True),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
        if connection is None:
            return
        await get_channel_adapter(connection).send_message(
            OutgoingMessage(recipient_id=recipient, text=_STUCK_MESSAGE)
        )
    except Exception:
        logger.warning("Couldn't tell %s their report was interrupted", recipient, exc_info=True)


async def sweep_forever() -> None:
    older_than = timedelta(minutes=settings.STUCK_REPORT_MINUTES)
    while True:
        try:
            await fail_stuck_reports(older_than=older_than)
        except Exception:
            logger.exception("Stuck-report sweep failed")
        await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
