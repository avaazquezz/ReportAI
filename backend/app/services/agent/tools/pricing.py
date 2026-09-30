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


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    prices = _PRICING_PER_MILLION_TOKENS.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price


def require_priced_model_for_spend_cap(model: str, cap_usd: float) -> None:
    """DAILY_SPEND_CAP_USD sums logged costs; an unpriced model logs none, so the cap would
    silently never trigger. Refuse to start instead."""
    if cap_usd > 0 and estimate_cost_usd(model, 0, 0) is None:
        raise RuntimeError(
            f"DAILY_SPEND_CAP_USD is set but model {model!r} has no price in tools/pricing.py, "
            "so spend can't be counted. Add its price or unset the cap."
        )
