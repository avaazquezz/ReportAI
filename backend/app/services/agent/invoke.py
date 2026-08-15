import logging
import uuid
from typing import Any

from fastapi import BackgroundTasks
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.channel_connection import ChannelConnection
from app.models.report import Report
from app.repositories.report_repository import ReportRepository
from app.services.agent.graph import get_compiled_graph
from app.services.agent.nodes._shared import send_on_origin_channel
from app.services.agent.nodes.deliver import mark_report_failed
from app.services.agent.state import AgentState
from app.services.channels.base import IncomingMessage, OutgoingMessage
from app.services.channels.factory import get_channel_adapter

logger = logging.getLogger(__name__)

_FAILURE_MESSAGE = "Sorry, we couldn't generate your report. Please try again or contact support."
_REJECTED_SENDER_MESSAGE = "Sorry, you're not authorized to use this channel. Contact your administrator."

_INTERRUPT_KIND_TO_STATUS = {
    "select_document_type": "awaiting_doctype_selection",
    "confirm_report": "awaiting_approval",
}


async def _mark_paused_if_interrupted(result: dict[str, Any], report_id: uuid.UUID) -> None:
    """A pause is a normal ainvoke() return carrying '__interrupt__', with the checkpoint
    already persisted — record it on the report so the resume dispatch can find it."""
    interrupts = result.get("__interrupt__") or ()
    if not interrupts:
        return
    value = getattr(interrupts[0], "value", None)
    kind = value.get("kind") if isinstance(value, dict) else None
    if kind is None or kind not in _INTERRUPT_KIND_TO_STATUS:
        return  # unknown interrupt kind: leave the report as-is rather than guess
    async with AsyncSessionLocal() as session:
        repo = ReportRepository(session)
        report = await repo.get_by_id(report_id)
        if report is not None:
            await repo.update(report, status=_INTERRUPT_KIND_TO_STATUS[kind])
            await session.commit()


async def resume_pipeline(
    *,
    db: AsyncSession,
    report: Report,
    reply_text: str,
    background_tasks: BackgroundTasks,
) -> bool:
    """Atomically claim a paused report and schedule the graph resume in the background.
    Returns False if another caller (duplicate reply, concurrent approve) already won the
    claim — the caller must not schedule a second resume of the same thread."""
    if not await ReportRepository(db).claim_for_resume(report.id):
        return False
    background_tasks.add_task(_resume_graph, str(report.id), reply_text)
    return True


async def _notify_failure_best_effort(state: AgentState) -> None:
    try:
        await send_on_origin_channel(state, _FAILURE_MESSAGE)
    except Exception:
        logger.warning("Failed to notify sender %s of pipeline failure", state.sender_id, exc_info=True)


async def _reject_sender_best_effort(connection: ChannelConnection, incoming: IncomingMessage) -> None:
    try:
        adapter = get_channel_adapter(connection)
        await adapter.send_message(
            OutgoingMessage(recipient_id=incoming.sender_id, text=_REJECTED_SENDER_MESSAGE)
        )
    except Exception:
        logger.warning(
            "Failed to notify unauthorized sender %s on connection %s",
            incoming.sender_id,
            connection.id,
            exc_info=True,
        )


async def start_or_resume_pipeline(
    *,
    db: AsyncSession,
    connection: ChannelConnection,
    incoming: IncomingMessage,
    background_tasks: BackgroundTasks,
) -> uuid.UUID | None:
    """Single entry point every webhook route calls. A new message from a sender with an
    already-paused report is treated as the reply to that pause; otherwise a new run starts.
    Returns None (no report created, no LLM invoked) if the sender isn't on this
    connection's allow-list — checked here so both the new-report and resume paths are
    covered by one guard, not one per webhook route."""
    if connection.allowed_senders and incoming.sender_id not in connection.allowed_senders:
        await _reject_sender_best_effort(connection, incoming)
        return None

    report_repo = ReportRepository(db)
    pending = await report_repo.find_pending_for_sender(
        tenant_id=connection.tenant_id, requester_identifier=incoming.sender_id
    )
    if pending is not None:
        # If the claim is lost (near-simultaneous duplicate reply), drop this message
        # rather than starting a new report from what was meant as a reply.
        await resume_pipeline(
            db=db, report=pending, reply_text=incoming.text or "", background_tasks=background_tasks
        )
        return pending.id

    report = await report_repo.create(
        tenant_id=connection.tenant_id,
        status="pending",
        requester_channel=incoming.channel_type,
        requester_identifier=incoming.sender_id,
    )
    await db.commit()

    initial_state = AgentState(
        thread_id=str(report.id),
        tenant_id=connection.tenant_id,
        channel_connection_id=connection.id,
        channel_type=incoming.channel_type,
        sender_id=incoming.sender_id,
        report_id=report.id,
        raw_payload=incoming.raw_payload,
        incoming_text=incoming.text,
        media_reference=incoming.media_reference,
    )
    background_tasks.add_task(_run_graph, initial_state)
    return report.id


async def _run_graph(initial_state: AgentState) -> None:
    try:
        result = await get_compiled_graph().ainvoke(
            initial_state,
            config={"configurable": {"thread_id": initial_state.thread_id}},
        )
        await _mark_paused_if_interrupted(result, initial_state.report_id)
    except Exception as exc:  # noqa: BLE001 — deliberate top-level catch: any unexpected
        # node failure must mark the report failed, not crash the background task silently
        await mark_report_failed(report_id=initial_state.report_id, error_detail=str(exc))
        await _notify_failure_best_effort(initial_state)


async def _resume_graph(thread_id: str, reply_text: str) -> None:
    try:
        result = await get_compiled_graph().ainvoke(
            Command(resume=reply_text),
            config={"configurable": {"thread_id": thread_id}},
        )
        # A correction reply re-extracts and pauses again — re-mark the pause status
        # (the claim set it back to 'pending' while the resume was in flight).
        await _mark_paused_if_interrupted(result, uuid.UUID(thread_id))
    except Exception as exc:  # noqa: BLE001 — same deliberate top-level catch as _run_graph
        async with AsyncSessionLocal() as session:
            report_repo = ReportRepository(session)
            report = await report_repo.get_by_id(uuid.UUID(thread_id))
            if report is not None:
                await mark_report_failed(report_id=report.id, error_detail=str(exc))

        # Reconstruct enough state from the last checkpoint to notify the requester —
        # _resume_graph only receives thread_id + reply text, not the full AgentState.
        snapshot = await get_compiled_graph().aget_state({"configurable": {"thread_id": thread_id}})
        if snapshot.values:
            await _notify_failure_best_effort(AgentState.model_validate(snapshot.values))
