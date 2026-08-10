# USD per million tokens. Static snapshot — drifts as providers reprice;
# revisit periodically rather than treating this as exact.
_PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (3.0, 15.0),  # (input, output)
    "whisper-large-v3-turbo": (0.0, 0.0),  # priced per audio-minute, not tokens — not estimated here
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    prices = _PRICING_PER_MILLION_TOKENS.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
