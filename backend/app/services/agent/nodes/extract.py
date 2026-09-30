import json
from functools import cache
from typing import Any, NamedTuple, cast

from anthropic import AsyncAnthropic, transform_schema
from anthropic.types import OutputConfigParam
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.services.agent.state import AgentState, ToolUsage
from app.services.agent.tools.extraction_schema import build_extraction_model
from app.services.agent.tools.pricing import estimate_cost_usd
from app.services.observability.execution_log import observed_node

TOOL_NAME = "extract_report_fields"
_MAX_TOKENS = 4096


class _Extraction(NamedTuple):
    fields: dict[str, Any]
    input_tokens: int
    output_tokens: int


# Clients are built on first use, not at import: which provider is configured (and which
# keys exist) depends on the installation.
@cache
def _anthropic_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=3)


@cache
def _openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.EXTRACTION_API_KEY, base_url=settings.EXTRACTION_BASE_URL, max_retries=3
    )


def _build_system_prompt(document_type_name: str, prompt_instructions: str | None) -> str:
    base = (
        f"You extract structured data for a '{document_type_name}' corporate report from a "
        "transcript or message. Give your best-effort extraction of the requested fields. "
        "Never invent facts not present in the source text — leave optional "
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


async def _extract_with_anthropic(system: str, user: str, model_cls: type[BaseModel]) -> _Extraction:
    # Structured outputs, not a forced tool_choice: forced tool use returns a 400 on
    # Claude Sonnet 5.5, Opus 5.5 and Fable 5.1, which is where model updates lead.
    output_config: dict[str, Any] = {
        "format": {"type": "json_schema", "schema": transform_schema(model_cls)}
    }
    if settings.EXTRACTION_EFFORT:
        output_config["effort"] = settings.EXTRACTION_EFFORT
    response = await _anthropic_client().messages.create(
        model=settings.EXTRACTION_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config=cast(OutputConfigParam, output_config),
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise ValueError(f"Extraction did not complete: stop_reason={response.stop_reason}")
    text = next(block.text for block in response.content if block.type == "text")
    return _Extraction(
        json.loads(text), response.usage.input_tokens, response.usage.output_tokens
    )


async def _extract_with_openai_compatible(
    system: str, user: str, model_cls: type[BaseModel]
) -> _Extraction:
    response = await _openai_client().chat.completions.create(
        model=settings.EXTRACTION_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "description": "Extract structured report fields from the source text.",
                    "parameters": model_cls.model_json_schema(),
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": TOOL_NAME}},
    )
    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise ValueError(
            f"Model {settings.EXTRACTION_MODEL!r} did not call the extraction function — it may "
            "not support forced function calling (reasoning/thinking variants often don't)"
        )
    call = tool_calls[0]
    if call.type != "function":
        raise ValueError(f"Unexpected tool call type {call.type!r} from the extraction model")
    usage = response.usage
    return _Extraction(
        json.loads(call.function.arguments),
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )


@observed_node("extract")
async def extract_node(state: AgentState) -> AgentState:
    assert state.document_type_name is not None
    assert state.field_schema is not None

    model_cls = build_extraction_model(state.document_type_name, state.field_schema)
    system = _build_system_prompt(state.document_type_name, state.prompt_instructions)
    user = _build_user_message(
        state.incoming_text, state.last_validation_error, state.correction_text
    )
    extract = (
        _extract_with_anthropic
        if settings.EXTRACTION_PROVIDER == "anthropic"
        else _extract_with_openai_compatible
    )
    extraction = await extract(system, user, model_cls)

    return state.model_copy(
        update={
            "extracted_fields": extraction.fields,
            "extraction_attempts": state.extraction_attempts + 1,
            "correction_text": None,
            "last_tool_usage": ToolUsage(
                model_used=settings.EXTRACTION_MODEL,
                cost_usd=estimate_cost_usd(
                    settings.EXTRACTION_MODEL, extraction.input_tokens, extraction.output_tokens
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
        model_cls.model_validate(state.extracted_fields)
        return state.model_copy(update={"last_validation_error": None})
    except ValidationError as exc:
        return state.model_copy(update={"last_validation_error": str(exc)})
