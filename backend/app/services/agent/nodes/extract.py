from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.core.config import settings
from app.services.agent.state import AgentState, ToolUsage
from app.services.agent.tools.extraction_schema import (
    build_extraction_model,
    build_result_model,
    unverified_evidence_keys,
)
from app.services.agent.tools.pricing import estimate_cost_usd
from app.services.i18n import LANGUAGE_NAMES, normalize_language
from app.services.llm import structured_completion
from app.services.observability.execution_log import observed_node

TOOL_NAME = "extract_report_fields"


def _local_moment(state: AgentState) -> datetime:
    moment = state.received_at or datetime.now(UTC)
    try:
        return moment.astimezone(ZoneInfo(state.timezone))
    except Exception:  # noqa: BLE001 — an unknown tz name in a tenant setting must not stop a report
        return moment.astimezone(UTC)


def _build_system_prompt(state: AgentState) -> str:
    assert state.document_type_name is not None
    local = _local_moment(state)
    language = LANGUAGE_NAMES[normalize_language(state.language)]
    sender = f" ('{state.sender_label}')" if state.sender_label else ""
    base = (
        f"You extract structured data for a '{state.document_type_name}' corporate report from a "
        f"message sent by a person{sender}. The message was sent on {local:%A %Y-%m-%d} at "
        f"{local:%H:%M} ({local.tzname()}): resolve relative dates and times ('tomorrow', "
        "'next Thursday', 'el jueves') from that moment and always output absolute dates. "
        "Fill a field only with what the message states. If it does not say, return null for "
        "that field: never guess and never invent — a missing value will be asked of the "
        "person. In 'evidence', for every field you filled, copy the shortest exact quote from "
        "the message that supports it (verbatim, in the message's own language), or null. "
        f"Write free-text values in {language}."
    )
    if state.prompt_instructions:
        return f"{base}\n\n{state.prompt_instructions}"
    return base


def _build_user_message(state: AgentState) -> str:
    parts = [f"Message:\n{state.source_text or ''}"]
    corrections = [*state.corrections, *([state.correction_text] if state.correction_text else [])]
    if corrections:
        listed = "\n".join(f"- {text}" for text in corrections)
        parts.append(
            "The person added or corrected the following, in order (apply all of it; a later "
            f"statement wins over an earlier one):\n{listed}"
        )
    if state.last_validation_error:
        parts.append(
            f"Your previous extraction failed validation with this error — fix it:\n{state.last_validation_error}"
        )
    return "\n\n".join(parts)


@observed_node("extract")
async def extract_node(state: AgentState) -> AgentState:
    assert state.document_type_name is not None
    assert state.field_schema is not None

    result_cls = build_result_model(state.document_type_name, state.field_schema)
    source_text = state.source_text or state.incoming_text or ""
    state = state.model_copy(update={"source_text": source_text})
    completion = await structured_completion(
        system=_build_system_prompt(state),
        user=_build_user_message(state),
        model_cls=result_cls,
        tool_name=TOOL_NAME,
    )

    fields: dict[str, Any] = completion.data.get("fields") or {}
    quotes: dict[str, Any] = completion.data.get("evidence") or {}
    corrections = [*state.corrections, *([state.correction_text] if state.correction_text else [])]
    haystack = "\n".join([source_text, *corrections])
    unverified = unverified_evidence_keys(quotes, haystack)
    evidence = {
        name: {"quote": quote, "verified": name not in unverified}
        for name, quote in quotes.items()
        if quote and fields.get(name) is not None
    }

    return state.model_copy(
        update={
            "extracted_fields": fields,
            "evidence": evidence,
            "corrections": corrections,
            "extraction_attempts": state.extraction_attempts + 1,
            "correction_text": None,
            "last_tool_usage": ToolUsage(
                model_used=settings.EXTRACTION_MODEL,
                cost_usd=estimate_cost_usd(
                    settings.EXTRACTION_MODEL, completion.input_tokens, completion.output_tokens
                ),
            ),
        }
    )


@observed_node("validate")
async def validate_node(state: AgentState) -> AgentState:
    assert state.document_type_name is not None
    assert state.field_schema is not None

    model_cls = build_extraction_model(state.document_type_name, state.field_schema)
    try:
        validated = model_cls.model_validate(state.extracted_fields)
    except ValidationError as exc:
        return state.model_copy(update={"last_validation_error": str(exc)})
    # Normalised (dates as ISO strings, tables as plain dicts) so what is stored and shown is
    # exactly what the template will receive.
    return state.model_copy(
        update={
            "extracted_fields": validated.model_dump(mode="json"),
            "last_validation_error": None,
        }
    )
