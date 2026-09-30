"""Ending a report on purpose: the person cancelled it, or started a different one instead."""

import logging
from datetime import UTC, datetime

from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.models.channel_connection import ChannelConnection
from app.models.report import Report
from app.services.agent.ingestion import create_report_with_job
from app.services.agent.nodes._shared import send_on_origin_channel
from app.services.agent.state import AgentState
from app.services.i18n import t
from app.services.observability.execution_log import observed_node

logger = logging.getLogger(__name__)


async def _notify(state: AgentState, key: str) -> None:
    try:
        await send_on_origin_channel(state, t(state.language, key))
    except Exception:
        logger.warning("Failed to send %s to %s", key, state.sender_id, exc_info=True)


@observed_node("cancel_report")
async def cancel_report_node(state: AgentState) -> AgentState:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Report)
            .where(Report.id == state.report_id)
            .values(status="cancelled", completed_at=datetime.now(UTC))
        )
        await session.commit()
    await _notify(state, "cancelled")
    return state


@observed_node("supersede_report")
async def supersede_report_node(state: AgentState) -> AgentState:
    """The reply was not about this report but the start of another one: close this one and begin
    the new one from the same message, in a single transaction (the sender may only have one
    report in flight, so the old one must be out of the way before the new one exists)."""
    reply = state.pending_user_reply
    text = reply.get("text") if isinstance(reply, dict) else reply
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Report)
            .where(Report.id == state.report_id)
            .values(status="cancelled", completed_at=datetime.now(UTC))
        )
        connection = await session.get(ChannelConnection, state.channel_connection_id)
        assert connection is not None
        await create_report_with_job(
            session,
            connection,
            sender_id=state.sender_id,
            channel_type=state.channel_type,
            text=text,
            media_reference=None,
            sender_label=state.sender_label,
            meta=state.channel_meta,
        )
        await session.commit()
    await _notify(state, "superseded")
    return state
