"""One way to ask the configured model for structured JSON, whichever provider it is.

Extraction and intent classification both go through here, so provider differences (Anthropic
structured outputs vs. an OpenAI-compatible forced function call) and timeouts live in one place.
"""

import asyncio
import json
from functools import lru_cache
from typing import Any, NamedTuple, cast

import anthropic
import openai
from anthropic import AsyncAnthropic, transform_schema
from anthropic.types import OutputConfigParam
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.services.instance_settings import AIConfig, NotConfiguredError, ProviderRejectedKeyError


class LLMResult(NamedTuple):
    data: dict[str, Any]
    input_tokens: int
    output_tokens: int
    model: str = ""  # who answered: what the cost is counted against
    platform_paid: bool = True  # whose key paid for it (AIConfig.platform_paid)


# One client per key: a key changed in the panel gets a new client on the next call, and the
# old one is dropped from the cache.
@lru_cache(maxsize=4)
def _anthropic_client(api_key: str) -> AsyncAnthropic:
    return AsyncAnthropic(api_key=api_key, max_retries=2, timeout=settings.LLM_TIMEOUT_SECONDS)


@lru_cache(maxsize=4)
def _openai_client(api_key: str, base_url: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=2, timeout=settings.LLM_TIMEOUT_SECONDS)


def clear_client_cache() -> None:
    """For tests: pytest-asyncio gives every test its own event loop, and a cached HTTP client
    keeps connections bound to one that is already closed."""
    _anthropic_client.cache_clear()
    _openai_client.cache_clear()


async def _with_anthropic(
    config: AIConfig, system: str, user: str, model_cls: type[BaseModel], max_tokens: int
) -> LLMResult:
    # Structured outputs, not a forced tool_choice: forced tool use returns a 400 on
    # Claude Sonnet 5.5, Opus 5.5 and Fable 5.1, which is where model updates lead.
    output_config: dict[str, Any] = {
        "format": {"type": "json_schema", "schema": transform_schema(model_cls)}
    }
    if config.effort:
        output_config["effort"] = config.effort
    response = await _anthropic_client(config.api_key).messages.create(
        model=config.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config=cast(OutputConfigParam, output_config),
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise ValueError(f"Model did not complete: stop_reason={response.stop_reason}")
    text = next(block.text for block in response.content if block.type == "text")
    return LLMResult(json.loads(text), response.usage.input_tokens, response.usage.output_tokens, config.model)


async def _with_openai_compatible(
    config: AIConfig, system: str, user: str, model_cls: type[BaseModel], tool_name: str
) -> LLMResult:
    response = await _openai_client(config.api_key, config.base_url).chat.completions.create(
        model=config.model,
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
            f"Model {config.model!r} did not call the extraction function — it may "
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
        config.model,
    )


async def structured_completion(
    *,
    system: str,
    user: str,
    model_cls: type[BaseModel],
    tool_name: str,
    config: AIConfig,
    max_tokens: int = 4096,
) -> LLMResult:
    """Ask the model for JSON matching `model_cls`. `config` has no default on purpose: the caller
    says whose AI it is (company_ai for a company's work, the form's values for a "test" button),
    so no call can fall back to the platform's key by omission.
    Bounded overall: the clients' own timeouts apply per attempt, and with retries a stalled
    provider could otherwise hold a job for minutes."""
    if not config.configured:
        raise NotConfiguredError(
            "No AI model is configured: add the provider and its API key in the panel (Settings → AI)"
        )
    try:
        async with asyncio.timeout(settings.LLM_TOTAL_TIMEOUT_SECONDS):
            if config.provider == "anthropic":
                result = await _with_anthropic(config, system, user, model_cls, max_tokens)
            else:
                result = await _with_openai_compatible(config, system, user, model_cls, tool_name)
    except (
        anthropic.AuthenticationError,
        anthropic.PermissionDeniedError,
        openai.AuthenticationError,
        openai.PermissionDeniedError,
    ) as exc:
        raise ProviderRejectedKeyError(f"The AI provider refused the key ({type(exc).__name__})") from exc
    return result._replace(platform_paid=config.platform_paid)
