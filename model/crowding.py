"""Crowding percentile — rank current crowding vs trailing history."""

from __future__ import annotations


def compute_crowding_percentile(
    current_crowded_ratio: float,
    historical_ratios: list[float],
) -> dict:
    """Rank current crowding vs trailing history.

    Args:
        current_crowded_ratio: fraction of markets at max signal today
        historical_ratios: trailing daily crowded ratios (e.g. 252 days)

    Returns: {
        "current_ratio": float,
        "percentile": int 0-100,
        "classification": "HIGH" | "MODERATE" | "LOW",
        "context": "87th percentile vs trailing 1Y"
    }
    """
    if not historical_ratios:
        classification = _classify(current_crowded_ratio)
        return {
            "current_ratio": current_crowded_ratio,
            "percentile": None,
            "classification": classification,
            "context": "No historical data for percentile ranking",
        }

    count_below = sum(1 for r in historical_ratios if r < current_crowded_ratio)
    count_equal = sum(1 for r in historical_ratios if r == current_crowded_ratio)
    # Percentile: fraction of observations strictly below + half of ties
    n = len(historical_ratios)
    percentile = int(round((count_below + 0.5 * count_equal) / n * 100))
    percentile = max(0, min(100, percentile))

    classification = _classify(current_crowded_ratio)
    days = len(historical_ratios)
    period = "1Y" if days >= 200 else f"{days}d"

    return {
        "current_ratio": current_crowded_ratio,
        "percentile": percentile,
        "classification": classification,
        "context": f"{_ordinal(percentile)} percentile vs trailing {period}",
    }


def _classify(ratio: float) -> str:
    if ratio > 0.7:
        return "HIGH"
    if ratio > 0.4:
        return "MODERATE"
    return "LOW"


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
