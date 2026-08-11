import logging
import uuid

from fastapi import BackgroundTasks
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.channel_connection import ChannelConnection
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
        background_tasks.add_task(_resume_graph, str(pending.id), incoming.text or "")
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
        await get_compiled_graph().ainvoke(
            initial_state,
            config={"configurable": {"thread_id": initial_state.thread_id}},
        )
        # If the run paused on an interrupt, ainvoke() returns normally with the
        # checkpoint already persisted — no exception, nothing more to do here.
    except Exception as exc:  # noqa: BLE001 — deliberate top-level catch: any unexpected
        # node failure must mark the report failed, not crash the background task silently
        await mark_report_failed(report_id=initial_state.report_id, error_detail=str(exc))
        await _notify_failure_best_effort(initial_state)


async def _resume_graph(thread_id: str, reply_text: str) -> None:
    try:
        await get_compiled_graph().ainvoke(
            Command(resume=reply_text),
            config={"configurable": {"thread_id": thread_id}},
        )
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
