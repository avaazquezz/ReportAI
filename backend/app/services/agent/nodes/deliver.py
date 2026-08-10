import logging
from datetime import UTC, datetime

from app.core.database import AsyncSessionLocal
from app.models.channel_connection import ChannelConnection
from app.models.report import Report
from app.repositories.base import BaseRepository
from app.services.agent.nodes._shared import send_on_origin_channel
from app.services.agent.state import AgentState
from app.services.channels.base import OutgoingMessage
from app.services.channels.factory import get_channel_adapter
from app.services.delivery.email import send_report_email
from app.services.observability.execution_log import observed_node

logger = logging.getLogger(__name__)


@observed_node("deliver_email")
async def deliver_email_node(state: AgentState) -> AgentState:
    if not state.notification_emails:
        return state  # empty recipient list is a deliberate skip, not a failure

    assert state.rendered_pdf_path is not None
    await send_report_email(
        to=state.notification_emails,
        subject=f"{state.document_type_name} — generated report",
        body="Your report is attached.",
        attachment_path=state.rendered_pdf_path,
    )
    return state


@observed_node("deliver_channel_reply")
async def deliver_channel_reply_node(state: AgentState) -> AgentState:
    assert state.rendered_pdf_path is not None
    async with AsyncSessionLocal() as session:
        repo = BaseRepository(ChannelConnection, session)
        connection = await repo.get_by_id(state.channel_connection_id)
        if connection is None:
            raise ValueError(f"ChannelConnection {state.channel_connection_id} not found")
    adapter = get_channel_adapter(connection)
    await adapter.send_message(
        OutgoingMessage(
            recipient_id=state.sender_id,
            text=f"Your {state.document_type_name} is ready.",
            attachments=[state.rendered_pdf_path],
        )
    )
    return state


@observed_node("finalize_report")
async def finalize_report_node(state: AgentState) -> AgentState:
    async with AsyncSessionLocal() as session:
        repo = BaseRepository(Report, session)
        report = await repo.get_by_id(state.report_id)
        if report is not None:
            await repo.update(report, status="delivered", completed_at=datetime.now(UTC))
            await session.commit()
    return state


async def mark_report_failed(*, report_id: object, error_detail: str) -> None:
    async with AsyncSessionLocal() as session:
        repo = BaseRepository(Report, session)
        report = await repo.get_by_id(report_id)  # type: ignore[arg-type]
        if report is not None:
            await repo.update(report, status="failed", error_detail=error_detail[:2000])
            await session.commit()


@observed_node("fail")
async def fail_node(state: AgentState) -> AgentState:
    error_detail = state.error_detail or state.last_validation_error or "Pipeline failed after exhausting retries"
    await mark_report_failed(report_id=state.report_id, error_detail=error_detail)
    try:
        await send_on_origin_channel(
            state, "Sorry, we couldn't generate your report. Please try again or contact support."
        )
    except Exception:
        logger.warning("Failed to notify sender %s of pipeline failure", state.sender_id, exc_info=True)
    return state
