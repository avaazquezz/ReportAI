"""Required-to-send fields the message did not contain are asked for, not invented (IA-9)."""

import logging

from langgraph.types import interrupt

from app.services.agent.nodes._shared import send_on_origin_channel
from app.services.agent.state import AgentState
from app.services.agent.tools.extraction_schema import field_label, missing_required_fields
from app.services.i18n import t
from app.services.observability.execution_log import observed_node

logger = logging.getLogger(__name__)

# How many times the bot asks before handing the gaps to the approver: a person who does not
# know a value will not produce it on the third try.
MAX_MISSING_ATTEMPTS = 2


@observed_node("check_completeness")
async def check_completeness_node(state: AgentState) -> AgentState:
    assert state.field_schema is not None and state.extracted_fields is not None
    return state.model_copy(
        update={"missing_fields": missing_required_fields(state.field_schema, state.extracted_fields)}
    )


@observed_node("ask_missing_fields")
async def ask_missing_fields_node(state: AgentState) -> AgentState:
    assert state.field_schema is not None
    labels = "\n".join(f"• {field_label(name, state.field_schema[name])}" for name in state.missing_fields)
    try:
        await send_on_origin_channel(state, t(state.language, "missing_fields", fields=labels))
    except Exception:
        logger.warning("Failed to ask %s for the missing fields", state.sender_id, exc_info=True)
    return state.model_copy(update={"missing_attempts": state.missing_attempts + 1})


@observed_node("await_missing_fields")
async def await_missing_fields_node(state: AgentState) -> AgentState:
    reply = interrupt({"kind": "missing_fields", "fields": state.missing_fields})
    text = reply.get("text", "") if isinstance(reply, dict) else (reply or "")
    # The answer is treated like a correction: the extraction runs again with it in hand.
    return state.model_copy(update={"correction_text": str(text).strip() or None})


@observed_node("notify_missing_fields_limit")
async def notify_missing_fields_limit_node(state: AgentState) -> AgentState:
    try:
        await send_on_origin_channel(state, t(state.language, "missing_fields_limit"))
    except Exception:
        logger.warning("Failed to send the missing-fields notice to %s", state.sender_id, exc_info=True)
    return state
