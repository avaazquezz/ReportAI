"""The worker process: `python -m app.worker`.

It claims jobs from the queue and runs them — everything slow happens here, not in the API, so an
API restart never drops a report and a worker restart only delays one. On SIGTERM (a deploy) it
stops taking new jobs and finishes the one in hand; anything it cannot finish is picked up by the
next worker once its lease runs out."""

import asyncio
import contextlib
import logging
import os
import signal
import socket
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.langgraph_checkpointer import close_checkpointer, get_checkpointer, init_checkpointer
from app.core.logging import configure_logging
from app.models.report import Report
from app.models.used_refresh_token import UsedRefreshToken
from app.repositories.report_repository import PENDING_STATUSES
from app.services.channels.telegram_updates import (
    polling_enabled,
    register_all_webhooks,
    run_pollers,
)
from app.services.jobs.queue import claim_next, fail_abandoned
from app.services.jobs.runner import give_up, process

logger = logging.getLogger(__name__)

_IDLE_POLL_SECONDS = 2.0
_MAINTENANCE_EVERY = timedelta(minutes=10)


async def cancel_abandoned_reports() -> int:
    """Cancels reports that have waited on a person for PAUSED_REPORT_TTL_DAYS and drops their
    checkpoints, so nothing that will never resume is kept forever."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.PAUSED_REPORT_TTL_DAYS)
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                update(Report)
                .where(Report.status.in_(PENDING_STATUSES), Report.updated_at < cutoff)
                .values(status="cancelled", completed_at=datetime.now(UTC))
                .returning(Report.id)
            )
        ).all()
        await session.commit()
    for (report_id,) in rows:
        await get_checkpointer().adelete_thread(str(report_id))
    return len(rows)


async def drop_finished_checkpoints() -> int:
    """Safety net for the cleanup a job does when it ends a report: rejects, cancellations and
    anything a crash interrupted leave checkpoints behind for reports that will never resume."""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT r.id FROM reports r
                    JOIN checkpoints c ON c.thread_id = r.id::text
                    WHERE r.status IN ('delivered', 'delivery_failed', 'failed', 'cancelled')
                    """
                )
            )
        ).all()
    for (report_id,) in rows:
        await get_checkpointer().adelete_thread(str(report_id))
    return len(rows)


async def drop_expired_refresh_tokens() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(UsedRefreshToken).where(UsedRefreshToken.expires_at < datetime.now(UTC)))
        await session.commit()


async def maintenance() -> None:
    for job_id, report_id in await fail_abandoned():
        logger.error("Job %s was abandoned by a dead worker with no attempts left", job_id)
        await give_up(report_id, "The worker stopped before finishing the report", "interrupted")
    cancelled = await cancel_abandoned_reports()
    if cancelled:
        logger.info("Cancelled %s reports that waited too long for an answer", cancelled)
    await drop_finished_checkpoints()
    await drop_expired_refresh_tokens()


async def main() -> None:
    configure_logging()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    await init_checkpointer()

    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopping.set)

    logger.info("Worker %s started", worker_id)
    if polling_enabled():
        telegram = asyncio.create_task(run_pollers(stopping))
    else:
        telegram = asyncio.create_task(register_all_webhooks())
    last_maintenance = datetime.min.replace(tzinfo=UTC)
    try:
        while not stopping.is_set():
            if datetime.now(UTC) - last_maintenance > _MAINTENANCE_EVERY:
                try:
                    await maintenance()
                except Exception:
                    logger.exception("Maintenance failed")
                last_maintenance = datetime.now(UTC)

            job = await claim_next(worker_id)
            if job is None:
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=_IDLE_POLL_SECONDS)
                except TimeoutError:
                    pass
                continue
            await process(job, worker_id)
    finally:
        stopping.set()
        with contextlib.suppress(Exception):
            await telegram
        await close_checkpointer()
        logger.info("Worker %s stopped", worker_id)


if __name__ == "__main__":
    asyncio.run(main())
