"""Runs one claimed job: starts or resumes a report's LangGraph run, and decides what a failure
means (try again, or give up and tell the person)."""

import asyncio
import contextlib
import logging
import time
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
from app.services import company_ai, transcription
from app.services.agent.graph import get_compiled_graph
from app.services.agent.nodes.deliver import mark_report_failed
from app.services.agent.persistence import save_report
from app.services.agent.state import AgentState
from app.services.agent.tools.pricing import transcription_usage
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
    another_job_queued,
    complete,
    extend_lease,
    fail_or_retry,
    note_in_payload,
)
from app.services.observability.execution_log import write_execution_log

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

    if job.attempts > 1 and report.status in TERMINAL_STATUSES:
        # An earlier attempt finished the report (and forgot its checkpoints) but couldn't record
        # it: starting over would transcribe, extract and deliver it again.
        return
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
            # A report may carry its own language (the landing's live demo, in the visitor's):
            # it is transcribed, read and rendered in it rather than in the company's.
            language=(report.channel_meta or {}).get("locale") or tenant.language,
            timezone=tenant.timezone,
            received_at=report.received_at,
            sender_label=job.payload.get("sender_label"),
            channel_meta=report.channel_meta or {},
            document_type_id=job.payload.get("document_type_id"),  # chosen in the app before recording
        )
        result = await graph.ainvoke(state, config)
    await _mark_paused_if_interrupted(result, report.id)


# Where a resume took up its paused graph, noted in the job's payload: a retry compares it with
# where the graph stands now to tell whether the answer was delivered. The checkpoint moves on
# once the answered node completes, and stays put if that node itself fails.
_RESUMED_FROM = "resumed_from_checkpoint"


async def _reply(job: ClaimedJob, connection: ChannelConnection, tenant: Tenant) -> str | dict[str, Any]:
    """A pressed button or the panel answers with a structured reply, handed on as it is. A typed
    reply is text, and a voice note is turned into text before the graph sees it."""
    if job.payload.get("action"):
        return {key: value for key, value in job.payload.items() if key != _RESUMED_FROM}
    text = (job.payload.get("text") or "").strip()
    media_reference = job.payload.get("media_reference")
    if not media_reference:
        return text
    audio = await get_channel_adapter(connection).download_media(media_reference)
    filename = f"reply-{job.id}{transcription.audio_suffix(media_reference)}"
    start = time.monotonic()
    transcript = await transcription.transcribe(
        audio, filename, tenant.language, config=await company_ai.transcription_for(tenant.id)
    )
    # Outside the graph, so no node logs it: metered here.
    await write_execution_log(
        tenant_id=tenant.id,
        report_id=job.report_id,
        step="transcribe_reply",
        status="success",
        usage=transcription_usage(transcript),
        latency_ms=int((time.monotonic() - start) * 1000),
    )
    # Said and typed together (a correction in the app): both reach the graph.
    return "\n\n".join(part for part in (transcript.text.strip(), text) if part)


async def _resume(
    job: ClaimedJob, worker_id: str, report: Report, connection: ChannelConnection, tenant: Tenant
) -> None:
    graph = get_compiled_graph()
    config: RunnableConfig = {"configurable": {"thread_id": str(report.id)}}

    snapshot = await graph.aget_state(config)
    here = snapshot.config["configurable"].get("checkpoint_id")
    resumed_from = job.payload.get(_RESUMED_FROM)
    if resumed_from is not None and resumed_from != here:
        # An earlier attempt delivered the answer and the graph moved on: finish what it left.
        if snapshot.interrupts:
            # Paused again: never hand it this answer. Nor record the pause over a later answer
            # to it already queued (the report was claimed for that one): its job records its own.
            if await another_job_queued(report.id, job.id, RESUME):
                return
            result: dict[str, Any] = {"__interrupt__": snapshot.interrupts}
        elif snapshot.next:
            result = await graph.ainvoke(None, config)  # failed on the way: carry on
        else:
            return
    elif not any(task.interrupts for task in snapshot.tasks):
        return  # nothing awaits this answer (the report is no longer paused)
    else:
        if resumed_from is None and not await note_in_payload(job.id, worker_id, {_RESUMED_FROM: here}):
            return  # another worker took the job over and answers in its stead (process() logs it)
        result = await graph.ainvoke(Command(resume=await _reply(job, connection, tenant)), config)
    await _mark_paused_if_interrupted(result, report.id)


async def execute(job: ClaimedJob, worker_id: str) -> None:
    report, connection, tenant = await _load(job.report_id)
    with log_context(report_id=report.id, tenant_id=report.tenant_id, job=job.kind):
        if job.kind == RUN:
            await _run(job, report, connection, tenant)
        elif job.kind == RESUME:
            await _resume(job, worker_id, report, connection, tenant)
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


async def _pause_reached(job: ClaimedJob) -> tuple[Any, ...]:
    """The interrupts the report now waits on, if the job's work took it there: a run that got to
    its first pause, or a resume whose answer got in and led to the next one. Empty otherwise."""
    if job.kind not in (RUN, RESUME):
        return ()
    async with AsyncSessionLocal() as session:
        report = await ReportRepository(session).get_by_id(job.report_id)
    if report is None or report.status in TERMINAL_STATUSES:
        return ()  # nothing to keep: give_up leaves an ended report as it is
    config: RunnableConfig = {"configurable": {"thread_id": str(job.report_id)}}
    snapshot = await get_compiled_graph().aget_state(config)
    if not snapshot.interrupts:
        return ()
    if job.kind == RESUME:
        resumed_from = job.payload.get(_RESUMED_FROM)
        if resumed_from is None or resumed_from == snapshot.config["configurable"].get("checkpoint_id"):
            return ()  # the answer never got in: the pause is the one this job was to answer
    return tuple(snapshot.interrupts)


async def settle_abandoned(job: ClaimedJob, worker_id: str) -> None:
    """A job whose worker died on its last attempt (claimed by `claim_abandoned`). If the work got
    to its pause and only recording it failed, the report waits on the person, as it should: the
    pause is recorded and the job done. Otherwise the report fails and the person is told."""
    with log_context(report_id=job.report_id, job=job.kind):
        interrupts = await _pause_reached(job)
        if interrupts:
            logger.warning("Job %s was abandoned on its last attempt after its work was done", job.id)
            # As in _resume: a later answer already queued records its own pause.
            if not await another_job_queued(job.report_id, job.id, RESUME):
                await _mark_paused_if_interrupted({"__interrupt__": interrupts}, job.report_id)
            if not await complete(job.id, worker_id):
                logger.error("Job %s was taken by another worker while being settled", job.id)
            return
        logger.error("Job %s was abandoned by a dead worker with no attempts left", job.id)
        error = "The worker stopped before finishing and no attempts were left"
        if await fail_or_retry(job, worker_id, error, retryable=False) == "failed":
            await give_up(job.report_id, "The worker stopped before finishing the report", "interrupted")
        else:
            logger.error("Job %s was taken by another worker while being settled", job.id)


async def _heartbeat(job_id: uuid.UUID, worker_id: str, work: asyncio.Task[None], lost: asyncio.Event) -> None:
    """Renews the lease while `work` runs, and cancels `work` once this worker can't count on
    holding it: two runs of one report would race each other. Lost (another worker holds the job):
    sets `lost` and returns. Unknown (renewals kept failing): raises, for process() to stop the
    worker with. A renewal that fails or hangs while the last good one still holds (a database
    blip) is retried sooner than the next beat, until two thirds of the lease are gone: no attempt
    runs past that, so the work has the last third to wind down before another worker may claim
    the job."""
    loop = asyncio.get_running_loop()
    retry_every = LEASE_SECONDS / 12
    renewed_at = loop.time()  # the claim took the lease moments ago
    delay = LEASE_SECONDS / 3
    while True:
        await asyncio.sleep(delay)
        attempted_at = loop.time()  # before the call, as extend_lease stamps the new lease
        give_up_at = renewed_at + LEASE_SECONDS * 2 / 3
        try:
            async with asyncio.timeout_at(give_up_at):
                held = await extend_lease(job_id, worker_id)
        except Exception:
            if give_up_at - loop.time() <= retry_every:
                work.cancel()
                raise
            logger.warning("Couldn't renew the lease on job %s; trying again", job_id, exc_info=True)
            delay = retry_every
            continue
        if not held:
            if work.done():
                return  # process() has recorded the outcome; what it records checks the owner
            logger.error("Lost the lease on job %s; another worker may have taken it", job_id)
            lost.set()
            work.cancel()
            return
        # The next beat keeps its place a third of the lease after this renewal began, however
        # long it took, so a slow one doesn't eat into the retries of a failure after it.
        renewed_at = attempted_at
        delay = max(0.0, renewed_at + LEASE_SECONDS / 3 - loop.time())


def _renewal_error(heartbeat: asyncio.Task[None]) -> BaseException | None:
    return heartbeat.exception() if heartbeat.done() and not heartbeat.cancelled() else None


def _shutting_down() -> bool:
    """This task itself is being cancelled (the worker stopping), not just the work it awaits."""
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


async def process(job: ClaimedJob, worker_id: str) -> None:
    """Runs a job to completion, retry or surrender. It raises only to stop the worker: on its own
    cancellation, or when the lease can't be renewed, so that it runs out and another worker
    claims the job, or when recording success fails (the job is claimed again, as one whose worker
    died). Once the lease is lost it records nothing: the job and its report are the new owner's
    to finish or fail."""
    lease_lost = asyncio.Event()
    work = asyncio.create_task(execute(job, worker_id))
    heartbeat = asyncio.create_task(_heartbeat(job.id, worker_id, work, lease_lost))
    try:
        async with asyncio.timeout(settings.JOB_TIMEOUT_SECONDS):
            await work
    except asyncio.CancelledError:
        if _shutting_down():
            raise
        if (renewal_error := _renewal_error(heartbeat)) is not None:
            raise renewal_error from None
        if not lease_lost.is_set():
            raise
    except Exception as exc:
        if _shutting_down():
            raise asyncio.CancelledError from exc  # the work turned the worker's own cancellation into an error
        if (renewal_error := _renewal_error(heartbeat)) is not None:
            raise renewal_error from exc
        if lease_lost.is_set():
            return  # e.g. a library that turned our cancellation into an error of its own
        error = describe_exception(exc)
        permanent = isinstance(exc, PermanentJobError)
        logger.exception("Job %s (%s) failed on attempt %s", job.id, job.kind, job.attempts)
        outcome = await fail_or_retry(job, worker_id, error, retryable=not permanent)
        if outcome == "not_ours":
            # The lease ran out before the heartbeat noticed: the report is the new owner's.
            logger.error("Job %s was taken by another worker before this one could record its failure", job.id)
        elif outcome == "failed":
            await give_up(job.report_id, error, exc.reason_key if isinstance(exc, PermanentJobError) else "failure")
    else:
        # Outside the handlers above: a failure to record success is not a failure of the job.
        if not lease_lost.is_set() and not await complete(job.id, worker_id):
            # The lease ran out before the heartbeat noticed: another worker runs the job too.
            logger.error("Job %s was taken by another worker before this one could record its success", job.id)
    finally:
        heartbeat.cancel()
        # Unlike awaiting the heartbeat, this lets the worker's own cancellation through.
        await asyncio.wait([heartbeat])
        # Re-raises a renewal error, also one that came after the job had already ended.
        if (renewal_error := _renewal_error(heartbeat)) is not None:
            raise renewal_error
