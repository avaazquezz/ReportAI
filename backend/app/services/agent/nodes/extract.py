from typing import Any

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from app.core.config import settings
from app.services.agent.state import AgentState, ToolUsage
from app.services.agent.tools.extraction_schema import build_extraction_model
from app.services.agent.tools.pricing import estimate_cost_usd
from app.services.observability.execution_log import observed_node

TOOL_NAME = "extract_report_fields"

_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=3)


def _build_system_prompt(document_type_name: str, prompt_instructions: str | None) -> str:
    base = (
        f"You extract structured data for a '{document_type_name}' corporate report from a "
        "transcript or message. Use the extract_report_fields tool with your best-effort "
        "extraction. Never invent facts not present in the source text — leave optional "
        "fields empty rather than guessing."
    )
    if prompt_instructions:
        return f"{base}\n\n{prompt_instructions}"
    return base


def _build_user_message(
    incoming_text: str | None, last_validation_error: str | None, correction_text: str | None
) -> str:
    parts = [f"Source text:\n{incoming_text or ''}"]
    if last_validation_error:
        parts.append(
            f"Your previous extraction failed validation with this error — fix it:\n{last_validation_error}"
        )
    if correction_text:
        parts.append(f"The requester sent this correction — apply it:\n{correction_text}")
    return "\n\n".join(parts)


@observed_node("extract")
async def extract_node(state: AgentState) -> AgentState:
    assert state.document_type_name is not None
    assert state.field_schema is not None

    response = await _client.messages.create(
        model=settings.EXTRACTION_MODEL,
        max_tokens=2048,
        system=_build_system_prompt(state.document_type_name, state.prompt_instructions),
        tools=[
            {
                "name": TOOL_NAME,
                "description": "Extract structured report fields from the source text.",
                "input_schema": build_extraction_model(
                    state.document_type_name, state.field_schema
                ).model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": _build_user_message(
                    state.incoming_text, state.last_validation_error, state.correction_text
                ),
            }
        ],
    )
    tool_use = next(block for block in response.content if block.type == "tool_use")
    extracted_fields: dict[str, Any] = tool_use.input  # type: ignore[assignment]

    return state.model_copy(
        update={
            "extracted_fields": extracted_fields,
            "extraction_attempts": state.extraction_attempts + 1,
            "correction_text": None,
            "last_tool_usage": ToolUsage(
                model_used=settings.EXTRACTION_MODEL,
                cost_usd=estimate_cost_usd(
                    settings.EXTRACTION_MODEL,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                ),
            ),
        }
    )


@observed_node("validate")
def validate_node(state: AgentState) -> AgentState:
    assert state.document_type_name is not None
    assert state.field_schema is not None

    model_cls = build_extraction_model(state.document_type_name, state.field_schema)
    try:
        model_cls.model_validate(state.extracted_fields)
        return state.model_copy(update={"last_validation_error": None})
    except ValidationError as exc:
        return state.model_copy(update={"last_validation_error": str(exc)})
