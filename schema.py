"""Structured report builder — machine-readable schema from raw summary facts."""

from __future__ import annotations

from datetime import datetime, timezone


def build_structured_report(facts: dict) -> dict:
    """Build a machine-readable report with explicit provenance.

    Transforms the raw summary facts dict into a documented, structured
    schema suitable for JSON output and downstream consumers.
    """
    scope = facts.get("scope", {})
    exposure = facts.get("exposure", {})
    overview = facts.get("investment_overview", {})
    crowding = facts.get("crowding", {})
    validation = facts.get("validation", {})
    flow = facts.get("flow", {})

    market_table = _build_market_table(facts)
    sector_rotation = _build_sector_rotation(overview)
    risk_flags = _build_risk_flags(facts)

    conclusion = facts.get("conclusion", {})
    headline = conclusion.get("headline", "")
    details = conclusion.get("details", [])
    narrative = f"{headline} {' '.join(details)}".strip()

    return {
        "meta": {
            "report_date": facts.get("report_date"),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "schema_version": "2.0",
            "model_description": "20/120-day MA crossover with 3-month EWMA vol targeting and equal-risk sector weighting",
            "universe_scope": {
                "selected": scope.get("selected_market_count"),
                "total": scope.get("universe_market_count"),
                "note": "Proxy subset of ~100+ liquid futures markets",
            },
        },
        "exposure_summary": {
            "position_counts": facts.get("position_counts"),
            "gross_leverage": exposure.get("gross_leverage"),
            "net_exposure": exposure.get("net_exposure"),
            "aum_basis": overview.get("aum_basis_label"),
            "aum_usd": overview.get("aum_usd"),
            "deployed_notional": overview.get("gross_deployed_usd"),
            "headroom": overview.get("remaining_headroom_usd"),
            "headroom_formula": facts.get("capital", {}).get("formula"),
        },
        "market_table": market_table,
        "sector_rotation": sector_rotation,
        "crowding": {
            "ratio": crowding.get("crowded_ratio"),
            "classification": crowding.get("classification"),
            "percentile": crowding.get("percentile"),
            "percentile_context": crowding.get("percentile_context"),
            "max_positions": (
                crowding.get("max_long", []) + crowding.get("max_short", [])
            ),
        },
        "validation": {
            "composite_score": validation.get("composite", {}).get("composite_score"),
            "grade": validation.get("composite", {}).get("grade"),
            "components": validation.get("composite", {}).get("components"),
            "note": validation.get("composite", {}).get("note"),
        },
        "risk_flags": risk_flags,
        "narrative_summary": narrative,
        "raw_facts": facts,
    }


def _build_market_table(facts):
    overview = facts.get("investment_overview", {})
    all_flows = overview.get("all_market_flows", [])
    flip_risks_by_sym = {
        r["symbol"]: r for r in facts.get("nearest_flip_risks", [])
    }
    convictions_by_sym = {
        c["symbol"]: c for c in facts.get("strongest_convictions", [])
    }

    rows = []
    for mf in all_flows:
        sym = mf.get("symbol")
        risk = flip_risks_by_sym.get(sym, {})
        conv = convictions_by_sym.get(sym, {})
        rows.append({
            "symbol": sym,
            "market": mf.get("market"),
            "sector": mf.get("sector"),
            "signal": conv.get("signal"),
            "direction": mf.get("direction"),
            "weight": mf.get("weight"),
            "distance_to_flip_pct": risk.get("distance_pct"),
            "distance_bucket": risk.get("distance_bucket"),
            "notional_change_5d_usd": mf.get("estimated_notional_change_usd_5d"),
            "contract_equivalent_5d": mf.get("estimated_contract_equivalent_5d"),
            "days_in_position": conv.get("days_in_position"),
        })

    return rows


def _build_sector_rotation(overview):
    sector_flows = overview.get("sector_flows_5d", {})
    result = {}
    for sector, vals in sector_flows.items():
        result[sector] = {
            "net_weight": vals.get("delta_weight"),
            "notional_change_5d": vals.get("estimated_notional_change_usd"),
        }
    return result


def _build_risk_flags(facts):
    flags = []

    for risk in facts.get("nearest_flip_risks", [])[:5]:
        bucket = risk.get("distance_bucket", "far")
        if bucket in ("very_near", "near"):
            flags.append({
                "type": "reversal_proximity",
                "market": risk.get("market"),
                "distance_pct": risk.get("distance_pct"),
                "bucket": bucket,
            })

    crowding = facts.get("crowding", {})
    if crowding.get("classification") in ("HIGH", "MODERATE"):
        flags.append({
            "type": "crowding",
            "level": crowding.get("classification"),
            "percentile": crowding.get("percentile"),
        })

    validation = facts.get("validation", {})
    composite = validation.get("composite", {})
    for k, comp in (composite.get("components") or {}).items():
        if not comp.get("available"):
            flags.append({
                "type": "validation_gap",
                "missing_validator": k,
                "detail": comp.get("detail"),
            })

    return flags
