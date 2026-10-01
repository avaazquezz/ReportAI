"""Runs one claimed job: starts or resumes a report's LangGraph run, and decides what a failure
means (try again, or give up and tell the person)."""

import asyncio
import contextlib
import logging
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.langgraph_checkpointer import get_checkpointer
from app.core.logging import describe_exception, log_context
from app.models.channel_connection import ChannelConnection
from app.models.report import Report
from app.models.tenant import Tenant
from app.repositories.report_repository import TERMINAL_STATUSES, ReportRepository
from app.services import transcription
from app.services.agent.graph import get_compiled_graph
from app.services.agent.nodes.deliver import mark_report_failed
from app.services.agent.persistence import save_report
from app.services.agent.state import AgentState
from app.services.channels.base import OutgoingMessage
from app.services.channels.factory import get_channel_adapter
from app.services.delivery.deliveries import DeliveryFailed, send_pending
from app.services.i18n import t
from app.services.jobs.errors import PermanentJobError
from app.services.jobs.queue import (
    DELIVER,
    LEASE_SECONDS,
    RESUME,
    RUN,
    ClaimedJob,
    complete,
    extend_lease,
    fail_or_retry,
)

logger = logging.getLogger(__name__)

# A pause is a normal ainvoke() return carrying '__interrupt__', with the checkpoint already
# persisted — the kind of interrupt says what the report is waiting for.
_INTERRUPT_KIND_TO_STATUS = {
    "select_document_type": "awaiting_doctype_selection",
    "missing_fields": "awaiting_details",
    "confirm_report": "awaiting_approval",
}


async def _mark_paused_if_interrupted(result: dict[str, Any], report_id: uuid.UUID) -> None:
    interrupts = result.get("__interrupt__") or ()
    if not interrupts:
        return
    value = getattr(interrupts[0], "value", None)
    kind = value.get("kind") if isinstance(value, dict) else None
    if kind not in _INTERRUPT_KIND_TO_STATUS:
        return  # unknown interrupt kind: leave the report as-is rather than guess
    await save_report(report_id, status=_INTERRUPT_KIND_TO_STATUS[kind])


async def _forget_finished_thread(report_id: uuid.UUID) -> None:
    """A finished report never resumes, so its checkpoints (about 250 KB each) are dead weight."""
    async with AsyncSessionLocal() as session:
        report = await ReportRepository(session).get_by_id(report_id)
    if report is not None and report.status in TERMINAL_STATUSES:
        await get_checkpointer().adelete_thread(str(report_id))


async def _load(report_id: uuid.UUID) -> tuple[Report, ChannelConnection, Tenant]:
    async with AsyncSessionLocal() as session:
        report = await session.get(Report, report_id)
        if report is None:
            raise PermanentJobError(f"Report {report_id} no longer exists")
        connection = (
            await session.get(ChannelConnection, report.channel_connection_id)
            if report.channel_connection_id
            else None
        )
        tenant = await session.get(Tenant, report.tenant_id)
    if connection is None or tenant is None:
        raise PermanentJobError(f"Report {report_id} has lost its channel connection or tenant")
    return report, connection, tenant


async def _run(job: ClaimedJob, report: Report, connection: ChannelConnection, tenant: Tenant) -> None:
    graph = get_compiled_graph()
    config: RunnableConfig = {"configurable": {"thread_id": str(report.id)}}

    snapshot = await graph.aget_state(config)
    if job.attempts > 1 and snapshot.values:
        # An earlier attempt got somewhere: carry on from its last checkpoint instead of starting
        # over (and paying for the same transcription and extraction twice).
        result = await graph.ainvoke(None, config) if snapshot.next else {}
    else:
        text = job.payload.get("text")
        if text:
            await save_report(report.id, source_text=text)
        state = AgentState(
            thread_id=str(report.id),
            tenant_id=report.tenant_id,
            channel_connection_id=connection.id,
            channel_type=report.requester_channel,
            sender_id=report.requester_identifier,
            report_id=report.id,
            raw_payload={},
            incoming_text=text,
            source_text=text,
            media_reference=job.payload.get("media_reference"),
            language=tenant.language,
            timezone=tenant.timezone,
            received_at=report.received_at,
            sender_label=job.payload.get("sender_label"),
            channel_meta=report.channel_meta or {},
        )
        result = await graph.ainvoke(state, config)
    await _mark_paused_if_interrupted(result, report.id)


async def _reply(job: ClaimedJob, connection: ChannelConnection) -> str | dict[str, Any]:
    """A pressed button or the panel answers with a structured reply, handed on as it is. A typed
    reply is text, and a voice note is turned into text before the graph sees it."""
    if job.payload.get("action"):
        return job.payload
    text = (job.payload.get("text") or "").strip()
    media_reference = job.payload.get("media_reference")
    if text or not media_reference:
        return text
    audio = await get_channel_adapter(connection).download_media(media_reference)
    return (await transcription.transcribe(audio, f"reply-{job.id}.ogg")).strip()


async def _resume(job: ClaimedJob, report: Report, connection: ChannelConnection) -> None:
    graph = get_compiled_graph()
    config: RunnableConfig = {"configurable": {"thread_id": str(report.id)}}

    snapshot = await graph.aget_state(config)
    if not any(task.interrupts for task in snapshot.tasks):
        return  # an earlier attempt already delivered this answer

    result = await graph.ainvoke(Command(resume=await _reply(job, connection)), config)
    await _mark_paused_if_interrupted(result, report.id)


async def execute(job: ClaimedJob) -> None:
    report, connection, tenant = await _load(job.report_id)
    with log_context(report_id=report.id, tenant_id=report.tenant_id, job=job.kind):
        if job.kind == RUN:
            await _run(job, report, connection, tenant)
        elif job.kind == RESUME:
            await _resume(job, report, connection)
        elif job.kind == DELIVER:
            failures = await send_pending(report.id)
            if failures:
                raise DeliveryFailed("; ".join(failures))
        else:
            raise PermanentJobError(f"Unknown job kind {job.kind!r}")
        await _forget_finished_thread(report.id)


async def notify_failure(report_id: uuid.UUID, reason_key: str = "failure") -> None:
    """Tells the person their report failed — best effort, in their company's language."""
    try:
        report, connection, tenant = await _load(report_id)
        await get_channel_adapter(connection).send_message(
            OutgoingMessage(recipient_id=report.requester_identifier, text=t(tenant.language, reason_key))
        )
    except Exception:
        logger.warning("Couldn't tell the requester that report %s failed", report_id, exc_info=True)


async def give_up(report_id: uuid.UUID, error: str, reason_key: str = "failure") -> None:
    if await mark_report_failed(report_id=report_id, error_detail=error):
        await notify_failure(report_id, reason_key)
    else:
        logger.error("A job for report %s gave up after the report had ended: %s", report_id, error)
    with contextlib.suppress(Exception):
        await get_checkpointer().adelete_thread(str(report_id))


async def _heartbeat(job_id: uuid.UUID, worker_id: str) -> None:
    while True:
        await asyncio.sleep(LEASE_SECONDS / 3)
        if not await extend_lease(job_id, worker_id):
            logger.error("Lost the lease on job %s; another worker may have taken it", job_id)
            return


async def process(job: ClaimedJob, worker_id: str) -> None:
    """Runs a job to completion, retry or surrender — never raises."""
    heartbeat = asyncio.create_task(_heartbeat(job.id, worker_id))
    try:
        async with asyncio.timeout(settings.JOB_TIMEOUT_SECONDS):
            await execute(job)
        await complete(job.id, worker_id)
    except Exception as exc:
        error = describe_exception(exc)
        permanent = isinstance(exc, PermanentJobError)
        logger.exception("Job %s (%s) failed on attempt %s", job.id, job.kind, job.attempts)
        retrying = await fail_or_retry(job, worker_id, error, retryable=not permanent)
        if not retrying:
            await give_up(job.report_id, error)
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
