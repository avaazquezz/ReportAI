from typing import Any

from langgraph.types import interrupt

from app.services.agent.nodes._shared import send_on_origin_channel
from app.services.agent.state import AgentState
from app.services.observability.execution_log import observed_node

_CONFIRM_WORDS = {"confirm", "confirmar", "si", "sí", "yes", "ok", "vale"}


def _format_summary(extracted_fields: dict[str, Any]) -> str:
    lines = [f"- {key}: {value}" for key, value in extracted_fields.items()]
    return "\n".join(lines)


@observed_node("human_approval_prompt")
async def human_approval_prompt_node(state: AgentState) -> AgentState:
    assert state.extracted_fields is not None
    summary = _format_summary(state.extracted_fields)
    await send_on_origin_channel(
        state,
        f"Here's what I extracted for your {state.document_type_name}:\n\n{summary}\n\n"
        "Reply CONFIRM to generate the document, or send a correction as free text.",
    )
    return state


@observed_node("await_human_approval")
async def await_human_approval_node(state: AgentState) -> AgentState:
    reply = interrupt({"kind": "confirm_report", "fields": state.extracted_fields})
    return state.model_copy(update={"pending_user_reply": reply})


@observed_node("classify_approval_reply")
async def classify_approval_reply_node(state: AgentState) -> AgentState:
    reply = (state.pending_user_reply or "").strip()
    if reply.lower() in _CONFIRM_WORDS:
        return state.model_copy(update={"correction_text": None})

    return state.model_copy(
        update={
            "correction_text": reply,
            "correction_attempts": state.correction_attempts + 1,
        }
    )
