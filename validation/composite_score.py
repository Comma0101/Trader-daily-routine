"""Composite validation score from individual validators."""

from __future__ import annotations

from config import VALIDATION_WEIGHTS


def compute_composite_score(
    signal_val: dict | None,
    position_val: dict | None,
    return_val: dict | None,
    weights: dict | None = None,
) -> dict:
    """Produce a 0-100 composite validation score with letter grade.

    Each validator contributes a sub-score:
    - signal: agreement_rate * 100 (or unavailable if stub/missing)
    - position: agreement_rate * 100 (or unavailable if coverage == 0)
    - return: map DBMF full_period correlation to 0-100 scale

    Returns: {
        "composite_score": float 0-100,
        "grade": "A" | "B" | "C" | "D" | "F",
        "components": {signal: {score, weight, available}, ...},
        "available_weight": float (sum of weights for available validators),
        "note": str
    }
    """
    w = weights or dict(VALIDATION_WEIGHTS)

    components = {
        "signal": _score_signal(signal_val),
        "position": _score_position(position_val),
        "return": _score_return(return_val),
    }

    available_weight = sum(
        w[k] for k, comp in components.items() if comp["available"]
    )

    if available_weight > 0:
        composite = sum(
            comp["score"] * (w[k] / available_weight)
            for k, comp in components.items()
            if comp["available"]
        )
    else:
        composite = 0.0

    for k, comp in components.items():
        if comp["available"] and available_weight > 0:
            comp["effective_weight"] = round(w[k] / available_weight, 4)
        else:
            comp["effective_weight"] = 0.0

    missing = [k for k, comp in components.items() if not comp["available"]]
    if missing:
        note = f"Validators unavailable: {', '.join(missing)}. Weights redistributed to available validators."
    else:
        note = "All validators available."

    grade = _grade(composite)

    return {
        "composite_score": round(composite, 1),
        "grade": grade,
        "components": components,
        "available_weight": round(available_weight, 4),
        "note": note,
    }


def _score_signal(val: dict | None) -> dict:
    if not val:
        return {"score": 0.0, "available": False, "detail": "not provided"}
    agreement = val.get("agreement_rate")
    if agreement is None:
        return {"score": 0.0, "available": False, "detail": val.get("note", "unavailable")}
    return {"score": float(agreement) * 100.0, "available": True, "detail": f"{agreement:.0%} agreement"}


def _score_position(val: dict | None) -> dict:
    if not val:
        return {"score": 0.0, "available": False, "detail": "not provided"}
    coverage = val.get("coverage", 0)
    agreement = val.get("agreement_rate")
    if coverage == 0 or agreement is None:
        return {"score": 0.0, "available": False, "detail": "no coverage"}
    return {"score": float(agreement) * 100.0, "available": True, "detail": f"{agreement:.0%} agreement ({coverage} markets)"}


def _score_return(val: dict | None) -> dict:
    if not val:
        return {"score": 0.0, "available": False, "detail": "not provided"}
    if val.get("error"):
        return {"score": 0.0, "available": False, "detail": val["error"]}
    corrs = val.get("correlations", {})
    dbmf = corrs.get("DBMF", {})
    full_corr = dbmf.get("full_period")
    if full_corr is None:
        return {"score": 0.0, "available": False, "detail": "DBMF correlation unavailable"}
    # Map correlation [-1, 1] to score [0, 100], clamped
    score = max(0.0, min(100.0, (float(full_corr) + 1.0) * 50.0))
    return {"score": score, "available": True, "detail": f"DBMF corr {full_corr:.2f}"}


def _grade(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "F"
