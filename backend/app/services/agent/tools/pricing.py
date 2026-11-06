from app.services.agent.state import ToolUsage
from app.services.llm import LLMResult
from app.services.transcription import Transcript

# USD per million tokens, (input, output). Static snapshot of Anthropic's list prices
# (2026-09-25) — providers reprice, so revisit rather than treat this as exact.
# Models missing from the table (any non-Anthropic provider, new model ids) are simply
# not priced: tokens are still logged, and DAILY_SPEND_CAP_USD refuses to start without
# a price for the configured model, since it could not count anything.
_PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


# USD per hour of audio, and the shortest length one request is billed for. Static snapshot
# (2026-11-06) of Groq's (console.groq.com/docs/models, /docs/speech-to-text) and OpenAI's
# (developers.openai.com/api/docs/pricing) list prices — revisit rather than treat as exact.
# gpt-4o(-mini)-transcribe are billed by the token, not by the second: left unpriced.
_TRANSCRIPTION_PRICING_PER_HOUR: dict[str, tuple[float, float]] = {
    "whisper-large-v3-turbo": (0.04, 10.0),  # Groq bills at least 10 s per request
    "whisper-large-v3": (0.111, 10.0),
    "whisper-1": (0.36, 0.0),  # OpenAI, $0.006 / minute
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    prices = _PRICING_PER_MILLION_TOKENS.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price


def estimate_transcription_cost_usd(model: str, seconds: float | None) -> float | None:
    prices = _TRANSCRIPTION_PRICING_PER_HOUR.get(model)
    if prices is None or seconds is None:
        return None
    per_hour, minimum_seconds = prices
    return max(seconds, minimum_seconds) / 3600 * per_hour


def usage_of(result: LLMResult) -> ToolUsage:
    return ToolUsage(
        model_used=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=estimate_cost_usd(result.model, result.input_tokens, result.output_tokens),
    )


def transcription_usage(transcript: Transcript) -> ToolUsage:
    return ToolUsage(
        model_used=transcript.model,
        audio_seconds=transcript.seconds,
        cost_usd=estimate_transcription_cost_usd(transcript.model, transcript.seconds),
    )


def require_priced_model_for_spend_cap(model: str, cap_usd: float) -> None:
    """DAILY_SPEND_CAP_USD sums logged costs; an unpriced model logs none, so the cap would
    silently never trigger. Refuse to start instead."""
    if cap_usd > 0 and estimate_cost_usd(model, 0, 0) is None:
        raise RuntimeError(
            f"DAILY_SPEND_CAP_USD is set but model {model!r} has no price in tools/pricing.py, "
            "so spend can't be counted. Add its price or unset the cap."
        )
