import logging
from datetime import UTC, datetime

from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.models.report import Report
from app.repositories.report_repository import TERMINAL_STATUSES
from app.services.agent.nodes._shared import send_on_origin_channel
from app.services.agent.state import AgentState
from app.services.delivery.deliveries import (
    RETRY_DELAY_SECONDS,
    outcome_status,
    plan_deliveries,
    send_pending,
)
from app.services.i18n import t
from app.services.jobs.queue import DELIVER, enqueue
from app.services.observability.execution_log import observed_node

logger = logging.getLogger(__name__)


@observed_node("deliver")
async def deliver_node(state: AgentState) -> AgentState:
    """Records the PDF and every copy it must reach, then sends them. A copy that fails does not
    fail the report — the document exists — it gets a job of its own that retries just that copy."""
    assert state.rendered_pdf_path is not None
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Report)
            .where(Report.id == state.report_id)
            # Without these the panel can't offer the download or show/count the type, and the
            # fields must be the ones in the PDF (an approval from the panel may have edited them).
            .values(
                file_path=state.rendered_pdf_path,
                document_type_id=state.document_type_id,
                extracted_fields=state.extracted_fields,
                evidence=state.evidence,
            )
        )
        await plan_deliveries(
            session,
            state.report_id,
            channel_type=state.channel_type,
            sender_id=state.sender_id,
            emails=state.notification_emails,
        )
        await session.commit()

    if await send_pending(state.report_id):
        async with AsyncSessionLocal() as session:
            await enqueue(session, report_id=state.report_id, kind=DELIVER, delay_seconds=RETRY_DELAY_SECONDS)
            await session.commit()
    return state


@observed_node("finalize_report")
async def finalize_report_node(state: AgentState) -> AgentState:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Report)
            .where(Report.id == state.report_id)
            .values(status=await outcome_status(session, state.report_id), completed_at=datetime.now(UTC))
        )
        await session.commit()
    return state


async def mark_report_failed(*, report_id: object, error_detail: str) -> bool:
    """False when the report had already ended: a copy that could not be sent, or a job that gave
    up after the person cancelled, must not turn a finished report into a failed one."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Report)
            .where(Report.id == report_id, Report.status.not_in(TERMINAL_STATUSES))
            .values(status="failed", error_detail=error_detail[:2000])
            .returning(Report.id)
        )
        await session.commit()
        return result.first() is not None


@observed_node("fail")
async def fail_node(state: AgentState) -> AgentState:
    error_detail = state.error_detail or state.last_validation_error or "Pipeline failed after exhausting retries"
    await mark_report_failed(report_id=state.report_id, error_detail=error_detail)
    try:
        await send_on_origin_channel(state, t(state.language, "failure"))
    except Exception:
        logger.warning("Failed to notify sender %s of pipeline failure", state.sender_id, exc_info=True)
    return state
