"""Approximate USD cost estimation for the model under test.

`cost_usd` on EvaluationResult is the estimated cost of the *agent run being
evaluated* (the model-under-test's tokens × that model's price) — not the
judge's cost. For model comparison, the interesting axis is cost-per-quality
of the candidate model; the judge is a fixed evaluation overhead.

The PRICING table is approximate and WILL drift as vendors change prices.
It is keyed by model-id prefix (model ids carry date/version suffixes, e.g.
`claude-sonnet-4-20250514`). Unknown models return `None` — we never
fabricate a number. Prices are USD per 1,000,000 tokens, sourced from public
vendor pricing as of 2026-01; update as needed.
"""

from __future__ import annotations

# (input_per_1m, output_per_1m) in USD. Longest matching prefix wins.
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (1.0, 5.0),
    "claude-3-5-haiku": (0.80, 4.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-opus": (15.0, 75.0),
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.0),
    "o1-mini": (1.10, 4.40),
    "o1": (15.0, 60.0),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
}


def _lookup(model_id: str) -> tuple[float, float] | None:
    """Return the price tuple for the longest PRICING prefix matching model_id."""
    matches = [key for key in PRICING if model_id.startswith(key)]
    if not matches:
        return None
    return PRICING[max(matches, key=len)]


def estimate_cost(
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    """Estimate USD cost for a run, or None if the model is unknown or tokens
    are unavailable.

    Returning None (rather than 0.0) keeps an unknown-model cost out of band,
    consistent with the DimensionScore sentinel policy: absence is null, not a
    misleading zero.
    """
    if input_tokens is None or output_tokens is None:
        return None
    prices = _lookup(model_id)
    if prices is None:
        return None
    input_per_1m, output_per_1m = prices
    cost = (input_tokens * input_per_1m + output_tokens * output_per_1m) / 1_000_000
    return round(cost, 6)
