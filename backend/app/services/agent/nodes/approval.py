import logging
from typing import Any

from langgraph.types import interrupt
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.report_attachment import ReportAttachment
from app.services.agent.nodes._shared import send_on_origin_channel
from app.services.agent.persistence import save_report
from app.services.agent.state import AgentState, ToolUsage
from app.services.agent.summary import build_summary, chunk_text
from app.services.agent.tools.extraction_schema import build_extraction_model
from app.services.agent.tools.intent import classify_reply
from app.services.agent.tools.pricing import estimate_cost_usd
from app.services.channels.base import Button
from app.services.i18n import t
from app.services.llm import LLMResult
from app.services.observability.execution_log import observed_node

logger = logging.getLogger(__name__)


async def _photo_count(report_id: object) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            (
                await session.execute(
                    select(func.count()).select_from(ReportAttachment).where(ReportAttachment.report_id == report_id)
                )
            ).scalar_one()
        )


@observed_node("human_approval_prompt")
async def human_approval_prompt_node(state: AgentState) -> AgentState:
    assert state.extracted_fields is not None
    assert state.field_schema is not None

    # Put what the pipeline knows on the report row: the panel reviews from here, not from a checkpoint.
    await save_report(
        state.report_id,
        document_type_id=state.document_type_id,
        source_text=state.source_text,
        extracted_fields=state.extracted_fields,
        evidence=state.evidence,
    )
    summary = build_summary(
        state.language, state.field_schema, state.extracted_fields, photo_count=await _photo_count(state.report_id)
    )
    header = t(state.language, "approval_header", doc_type=state.document_type_name)
    footer = t(state.language, "approval_footer")
    chunks = chunk_text(f"{header}\n\n{summary}")
    buttons = [
        Button(label=t(state.language, "btn_confirm"), action="confirm"),
        Button(label=t(state.language, "btn_correct"), action="correct"),
        Button(label=t(state.language, "btn_cancel"), action="cancel"),
    ]
    try:
        for chunk in chunks[:-1]:
            await send_on_origin_channel(state, chunk)
        await send_on_origin_channel(state, f"{chunks[-1]}\n\n{footer}", buttons=buttons)
    except Exception:
        # Reaching the interrupt matters more than this send: the extraction is already
        # paid for, and a paused report stays approvable from the admin panel.
        logger.warning("Failed to send approval prompt to %s", state.sender_id, exc_info=True)
    return state


@observed_node("await_human_approval")
async def await_human_approval_node(state: AgentState) -> AgentState:
    reply = interrupt({"kind": "confirm_report", "fields": state.extracted_fields})
    return state.model_copy(update={"pending_user_reply": reply})


def _usage(result: LLMResult | None) -> ToolUsage | None:
    if result is None:
        return None
    return ToolUsage(
        model_used=settings.EXTRACTION_MODEL,
        cost_usd=estimate_cost_usd(settings.EXTRACTION_MODEL, result.input_tokens, result.output_tokens),
    )


def _apply_edited_fields(state: AgentState, edited: dict[str, Any]) -> AgentState:
    """Fields a person corrected in the panel replace the extracted ones — validated like any
    extraction, and their evidence dropped: the quote no longer backs what is now there."""
    assert state.field_schema is not None and state.document_type_name is not None
    model = build_extraction_model(state.document_type_name, state.field_schema)
    merged = {**(state.extracted_fields or {}), **edited}
    validated = model.model_validate(merged).model_dump(mode="json")
    evidence = {name: quote for name, quote in state.evidence.items() if name not in edited}
    return state.model_copy(update={"extracted_fields": validated, "evidence": evidence})


@observed_node("classify_approval_reply")
async def classify_approval_reply_node(state: AgentState) -> AgentState:
    reply = state.pending_user_reply
    usage = None

    if isinstance(reply, dict):  # a button, or the panel
        action = reply.get("action", "confirm")
        intent = {"confirm": "confirm", "cancel": "cancel"}.get(str(action), "ask")
        if intent == "confirm" and reply.get("fields"):
            try:
                state = _apply_edited_fields(state, reply["fields"])
            except ValidationError as exc:
                # Edits that do not fit the schema are not approved blindly: back to the person.
                return state.model_copy(update={"intent": "ask", "last_validation_error": str(exc)})
        return state.model_copy(update={"intent": intent, "correction_text": None})

    text = (reply or "").strip()
    intent, result = await classify_reply(text)
    usage = _usage(result)
    update: dict[str, Any] = {"intent": intent, "last_tool_usage": usage}
    if intent == "correct":
        update |= {"correction_text": text, "correction_attempts": state.correction_attempts + 1}
    else:
        update["correction_text"] = None
    return state.model_copy(update=update)


@observed_node("ask_what_to_correct")
async def ask_what_to_correct_node(state: AgentState) -> AgentState:
    """"No" / a pressed Correct button: say what to do, then wait again without re-extracting."""
    try:
        await send_on_origin_channel(state, t(state.language, "ask_correction"))
    except Exception:
        logger.warning("Failed to ask %s what to correct", state.sender_id, exc_info=True)
    return state


@observed_node("correction_limit")
async def correction_limit_node(state: AgentState) -> AgentState:
    """Corrections over chat are capped so a long argument cannot spend unlimited extractions;
    the report stays approvable (and editable) from the panel."""
    try:
        await send_on_origin_channel(state, t(state.language, "correction_limit"))
    except Exception:
        logger.warning("Failed to send the correction-limit notice to %s", state.sender_id, exc_info=True)
    return state
