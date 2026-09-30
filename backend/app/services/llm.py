"""One way to ask the configured model for structured JSON, whichever provider it is.

Extraction and intent classification both go through here, so provider differences (Anthropic
structured outputs vs. an OpenAI-compatible forced function call) and timeouts live in one place.
"""

import asyncio
import json
from functools import cache
from typing import Any, NamedTuple, cast

from anthropic import AsyncAnthropic, transform_schema
from anthropic.types import OutputConfigParam
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings


class LLMResult(NamedTuple):
    data: dict[str, Any]
    input_tokens: int
    output_tokens: int


# Clients are built on first use, not at import: which provider is configured (and which
# keys exist) depends on the installation.
@cache
def _anthropic_client() -> AsyncAnthropic:
    return AsyncAnthropic(
        api_key=settings.ANTHROPIC_API_KEY, max_retries=2, timeout=settings.LLM_TIMEOUT_SECONDS
    )


@cache
def _openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.EXTRACTION_API_KEY,
        base_url=settings.EXTRACTION_BASE_URL,
        max_retries=2,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )


def clear_client_cache() -> None:
    """For tests: pytest-asyncio gives every test its own event loop, and a cached HTTP client
    keeps connections bound to one that is already closed."""
    _anthropic_client.cache_clear()
    _openai_client.cache_clear()


async def _with_anthropic(system: str, user: str, model_cls: type[BaseModel], max_tokens: int) -> LLMResult:
    # Structured outputs, not a forced tool_choice: forced tool use returns a 400 on
    # Claude Sonnet 5.5, Opus 5.5 and Fable 5.1, which is where model updates lead.
    output_config: dict[str, Any] = {
        "format": {"type": "json_schema", "schema": transform_schema(model_cls)}
    }
    if settings.EXTRACTION_EFFORT:
        output_config["effort"] = settings.EXTRACTION_EFFORT
    response = await _anthropic_client().messages.create(
        model=settings.EXTRACTION_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config=cast(OutputConfigParam, output_config),
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise ValueError(f"Model did not complete: stop_reason={response.stop_reason}")
    text = next(block.text for block in response.content if block.type == "text")
    return LLMResult(json.loads(text), response.usage.input_tokens, response.usage.output_tokens)


async def _with_openai_compatible(
    system: str, user: str, model_cls: type[BaseModel], tool_name: str
) -> LLMResult:
    response = await _openai_client().chat.completions.create(
        model=settings.EXTRACTION_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": "Return the structured result.",
                    "parameters": model_cls.model_json_schema(),
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": tool_name}},
    )
    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise ValueError(
            f"Model {settings.EXTRACTION_MODEL!r} did not call the extraction function — it may "
            "not support forced function calling (reasoning/thinking variants often don't)"
        )
    call = tool_calls[0]
    if call.type != "function":
        raise ValueError(f"Unexpected tool call type {call.type!r} from the model")
    usage = response.usage
    return LLMResult(
        json.loads(call.function.arguments),
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )


async def structured_completion(
    *, system: str, user: str, model_cls: type[BaseModel], tool_name: str, max_tokens: int = 4096
) -> LLMResult:
    """Ask the model for JSON matching `model_cls`. Bounded overall: the clients' own timeouts
    apply per attempt, and with retries a stalled provider could otherwise hold a job for minutes."""
    async with asyncio.timeout(settings.LLM_TOTAL_TIMEOUT_SECONDS):
        if settings.EXTRACTION_PROVIDER == "anthropic":
            return await _with_anthropic(system, user, model_cls, max_tokens)
        return await _with_openai_compatible(system, user, model_cls, tool_name)
