"""Fact builder and renderers for human-readable CTA summaries."""

import logging
from datetime import date, datetime

import pandas as pd

logger = logging.getLogger(__name__)

from llm import GeminiConfigError, GeminiRequestError, generate_gemini_summary, load_gemini_config
from validation.composite_score import compute_composite_score


def build_summary_facts(
    portfolio_result,
    universe,
    flips_by_market,
    flow_estimate=None,
    capital_estimate=None,
    signal_validation=None,
    position_validation=None,
    return_validation=None,
    etf_returns_df=None,
    as_of=None,
    data_context=None,
    historical_crowding_ratios=None,
):
    details = portfolio_result.get("signal_details", {})
    selected_symbols = _selected_symbols(portfolio_result)
    report_date = _report_date(
        as_of=as_of,
        flips_by_market=flips_by_market,
        etf_returns_df=etf_returns_df,
    )

    facts = {
        "report_date": report_date,
        "scope": {
            "selected_market_count": len(selected_symbols),
            "universe_market_count": len(universe),
        },
        "position_counts": _position_counts(portfolio_result, selected_symbols),
        "crowding": _crowding_snapshot(details, universe, historical_crowding_ratios),
        "strongest_convictions": _strongest_convictions(portfolio_result, universe),
        "recent_flips": _recent_flips(flips_by_market, universe),
        "nearest_flip_risks": _nearest_flip_risks(details, universe),
        "sector_exposure": dict(portfolio_result.get("sector_exposure", {})),
        "exposure": {
            "gross_leverage": float(portfolio_result.get("gross_leverage", 0.0) or 0.0),
            "net_exposure": float(portfolio_result.get("net_exposure", 0.0) or 0.0),
        },
        "validation": _validation_snapshot(
            signal_validation=signal_validation,
            position_validation=position_validation,
            return_validation=return_validation,
        ) | {
            "composite": compute_composite_score(
                signal_val=signal_validation,
                position_val=position_validation,
                return_val=return_validation,
            ),
        },
        "data_context": dict(data_context or {}),
        "flow": _flow_snapshot(flow_estimate),
        "capital": _capital_snapshot(capital_estimate),
    }

    benchmark_snapshot = _benchmark_etf_snapshot(etf_returns_df, as_of=as_of)
    if benchmark_snapshot:
        facts["benchmark_etfs"] = benchmark_snapshot

    facts["investment_overview"] = _investment_overview_snapshot(facts)
    facts["data_used"] = _data_used_snapshot(facts)
    facts["calculation_method"] = _calculation_method_snapshot(facts)
    facts["conclusion"] = _conclusion_snapshot(facts)
    facts["suggestions"] = _suggestions_snapshot(facts)
    facts["thesis"] = _thesis_snapshot(facts)
    facts["drivers"] = _drivers_snapshot(facts)
    facts["interpretation"] = _interpretation_snapshot(facts)
    facts["why_now"] = _why_now_snapshot(facts)
    facts["confidence"] = _confidence_snapshot(facts)
    facts["actions"] = list(facts["suggestions"])

    return facts


def render_terminal_summary(facts):
    lines = [
        f"Data: {_data_used_line(facts)}",
        f"Method: {_method_line(facts)}",
        f"Capital: {_capital_line(facts)}",
        f"Conclusion: {_conclusion_line(facts)}",
        f"Suggestion: {_suggestions_line(facts)}",
    ]
    return "\n".join(lines)


def render_markdown_summary(facts):
    selected_count = _selected_market_count(facts)
    lines = [_markdown_headline(facts)]
    lines.append(f"*Proxy model: {selected_count}-market subset, modeled flows, not observed transactions.*")

    overview = facts.get("investment_overview", {})
    if overview.get("aum_usd") is not None:
        lines.append(f"**AUM Basis:** {_format_usd(overview['aum_usd'])} ({overview.get('aum_basis_label', 'N/A')})")
        gross_usd = _format_usd(overview.get("gross_deployed_usd"))
        gross_pct = f"{float(overview.get('gross_deployed_pct') or 0):.2f}x"
        net_usd = _format_usd(overview.get("net_deployed_usd"))
        net_pct = f"{float(overview.get('net_deployed_pct') or 0):.2f}x"
        headroom_usd = _format_usd(overview.get("remaining_headroom_usd"))
        lines.append(f"**Deployed:** {gross_usd} gross ({gross_pct}) | {net_usd} net ({net_pct}) | Headroom: {headroom_usd}")

    top_flows = _top_flows_mini_table(facts)
    if top_flows:
        lines.append("")
        lines.append(top_flows)

    lines.extend([
        f"- Data: {_data_used_line(facts)}",
        f"- Method: {_method_line(facts)}",
        f"- Conclusion: {_conclusion_line(facts)}",
        f"- Suggestions: {_suggestions_line(facts)}",
    ])
    return "\n".join(lines)


def maybe_generate_llm_summary(facts, use_llm=False, output_format="terminal"):
    renderer = render_markdown_summary if output_format == "markdown" else render_terminal_summary
    deterministic_summary = renderer(facts)

    if not use_llm:
        return deterministic_summary

    try:
        config = load_gemini_config()
    except GeminiConfigError as e:
        logger.warning("Gemini config unavailable, using deterministic summary: %s", e)
        return deterministic_summary

    model_overrides = [None]
    fallback_model = config.get("fallback_model")
    if fallback_model and fallback_model != config.get("model"):
        model_overrides.append(fallback_model)

    for model_override in model_overrides:
        model_label = model_override or config.get("model", "default")
        try:
            llm_summary = generate_gemini_summary(
                facts,
                output_format=output_format,
                model_override=model_override,
            )
        except (GeminiConfigError, GeminiRequestError, ValueError) as e:
            logger.warning("Gemini call failed (model=%s): %s", model_label, e)
            continue

        cleaned = llm_summary.strip()
        if not cleaned:
            logger.warning("Gemini returned empty response (model=%s)", model_label)
            continue

        if _llm_summary_matches_requested_format(cleaned, output_format=output_format):
            logger.info("Gemini summary accepted (model=%s, %d chars)", model_label, len(cleaned))
            return cleaned
        else:
            logger.warning("Gemini output rejected by format check (model=%s, %d chars)", model_label, len(cleaned))

    logger.warning("All Gemini attempts failed, using deterministic summary")
    return deterministic_summary


def _top_flows_mini_table(facts):
    flow = facts.get("flow", {})
    increases = flow.get("top_notional_increase_5d", [])[:3]
    decreases = flow.get("top_notional_decrease_5d", [])[:3]
    if not increases and not decreases:
        return None

    lines = ["**Top Modeled Notional Changes (5D):**"]
    for item in increases:
        market = item.get("market", item.get("symbol", "?"))
        usd = item.get("estimated_notional_change_usd_5d")
        if usd is not None:
            lines.append(f"  INCR {market} ({_format_usd(usd)})")
        else:
            lines.append(f"  INCR {market} ({float(item.get('delta_weight_5d', 0)):+.2%})")
    for item in decreases:
        market = item.get("market", item.get("symbol", "?"))
        usd = item.get("estimated_notional_change_usd_5d")
        if usd is not None:
            lines.append(f"  DECR {market} ({_format_usd(usd)})")
        else:
            lines.append(f"  DECR {market} ({float(item.get('delta_weight_5d', 0)):+.2%})")
    return "\n".join(lines)


def _selected_symbols(portfolio_result):
    symbols = set(portfolio_result.get("signal_details", {}))
    symbols.update(portfolio_result.get("signals", {}))
    symbols.update(portfolio_result.get("weights", {}))
    return sorted(symbols)


def _position_counts(portfolio_result, selected_symbols):
    counts = {"long": 0, "short": 0, "flat": 0}
    signals = portfolio_result.get("signals", {})
    details = portfolio_result.get("signal_details", {})

    for symbol in selected_symbols:
        signal_value = signals.get(symbol)
        if signal_value is None:
            signal_value = details.get(symbol, {}).get("signal", 0.0)
        counts[_direction_bucket(signal_value)] += 1

    return counts


def _crowding_snapshot(details, universe, historical_crowding_ratios=None):
    max_long = []
    max_short = []

    for symbol, detail in details.items():
        entry = {
            "symbol": symbol,
            "market": universe.get(symbol, {}).get("name", symbol),
            "sector": universe.get(symbol, {}).get("sector"),
            "days_in_position": detail.get("days_in_position", 0),
        }
        signal_value = float(detail.get("signal", 0.0) or 0.0)
        if signal_value >= 1.0:
            max_long.append(entry)
        elif signal_value <= -1.0:
            max_short.append(entry)

    max_long.sort(key=lambda item: (-item["days_in_position"], item["symbol"]))
    max_short.sort(key=lambda item: (-item["days_in_position"], item["symbol"]))

    total = len(details)
    crowded = len(max_long) + len(max_short)
    ratio = crowded / total if total else 0.0

    if ratio > 0.7:
        classification = "HIGH"
    elif ratio > 0.4:
        classification = "MODERATE"
    else:
        classification = "LOW"

    result = {
        "classification": classification,
        "crowded_market_count": crowded,
        "total_market_count": total,
        "crowded_ratio": ratio,
        "max_long": max_long,
        "max_short": max_short,
        "crowded_longs": max_long,
        "crowded_shorts": max_short,
    }

    if historical_crowding_ratios:
        from model.crowding import compute_crowding_percentile

        pct = compute_crowding_percentile(ratio, historical_crowding_ratios)
        result["percentile"] = pct["percentile"]
        result["percentile_context"] = pct["context"]

    return result


def _strongest_convictions(portfolio_result, universe):
    convictions = []
    weights = portfolio_result.get("weights", {})
    details = portfolio_result.get("signal_details", {})

    for symbol, weight in weights.items():
        weight_value = float(weight or 0.0)
        if abs(weight_value) < 1e-12:
            continue

        detail = details.get(symbol, {})
        convictions.append({
            "symbol": symbol,
            "market": universe.get(symbol, {}).get("name", symbol),
            "sector": universe.get(symbol, {}).get("sector"),
            "direction": _direction_label(weight_value),
            "weight": weight_value,
            "signal": float(detail.get("signal", 0.0) or 0.0),
            "days_in_position": detail.get("days_in_position", 0),
        })

    convictions.sort(key=lambda item: (-abs(item["weight"]), item["symbol"]))
    return convictions


def _recent_flips(flips_by_market, universe):
    dated_flips = []
    undated_flips = []

    for symbol, market_flips in (flips_by_market or {}).items():
        for flip in market_flips:
            entry = {
                "symbol": symbol,
                "market": universe.get(symbol, {}).get("name", symbol),
                "sector": universe.get(symbol, {}).get("sector"),
                "date": _iso_date(flip.get("date")),
                "from_label": flip.get("from_label"),
                "to_label": flip.get("to_label"),
                "price": flip.get("price"),
            }
            sort_date = _timestamp_or_none(flip.get("date"))
            if sort_date is None:
                undated_flips.append(entry)
            else:
                dated_flips.append((sort_date, entry))

    dated_flips.sort(key=lambda item: (item[0], item[1]["symbol"]), reverse=True)
    undated_flips.sort(key=lambda item: item["symbol"])

    return [entry for _, entry in dated_flips] + undated_flips


def _nearest_flip_risks(details, universe):
    risks = []

    for symbol, detail in details.items():
        price = float(detail.get("price", 0.0) or 0.0)
        reversal_price_short = detail.get("reversal_price_short")
        reversal_price_long = detail.get("reversal_price_long")

        if not price or reversal_price_short is None or reversal_price_long is None:
            continue

        dist_short = (price - float(reversal_price_short)) / price * 100.0
        dist_long = (price - float(reversal_price_long)) / price * 100.0

        if abs(dist_short) <= abs(dist_long):
            nearest_leg = "short"
            nearest_distance = abs(dist_short)
            nearest_price = float(reversal_price_short)
        else:
            nearest_leg = "long"
            nearest_distance = abs(dist_long)
            nearest_price = float(reversal_price_long)

        risks.append({
            "symbol": symbol,
            "market": universe.get(symbol, {}).get("name", symbol),
            "sector": universe.get(symbol, {}).get("sector"),
            "direction": _direction_label(float(detail.get("signal", 0.0) or 0.0)),
            "price": price,
            "reversal_price_short": float(reversal_price_short),
            "reversal_price_long": float(reversal_price_long),
            "distance_pct": nearest_distance,
            "distance_bucket": _bucket_threshold_distance(nearest_distance),
            "nearest_leg": nearest_leg,
            "nearest_price": nearest_price,
            "distance_to_short_pct": abs(dist_short),
            "distance_to_long_pct": abs(dist_long),
        })

    risks.sort(key=lambda item: (item["distance_pct"], item["symbol"]))
    return risks


def _bucket_threshold_distance(distance_pct):
    """Bucket a distance-to-flip percentage into actionable zones."""
    d = abs(float(distance_pct or 0))
    if d < 1.0:
        return "very_near"
    if d < 2.5:
        return "near"
    if d < 5.0:
        return "moderate"
    return "far"


def _validation_snapshot(signal_validation=None, position_validation=None, return_validation=None):
    snapshot = {"caveats": []}

    if signal_validation:
        signal_snapshot = {
            "coverage": signal_validation.get("coverage", 0),
            "agreement_rate": signal_validation.get("agreement_rate"),
        }
        note = signal_validation.get("note")
        if note:
            signal_snapshot["note"] = note
            snapshot["caveats"].append(note)
        snapshot["signal"] = signal_snapshot
    else:
        snapshot["caveats"].append("SG signal validation not provided.")

    if position_validation:
        position_snapshot = {
            "coverage": position_validation.get("coverage", 0),
            "agreement_rate": position_validation.get("agreement_rate"),
            "by_report_type": dict(position_validation.get("by_report_type", {})),
        }
        if position_snapshot["coverage"] == 0 or position_snapshot["agreement_rate"] is None:
            snapshot["caveats"].append("COT directional agreement: No current overlap")
        snapshot["position"] = position_snapshot

    if return_validation:
        return_snapshot = {
            "summary": return_validation.get("summary"),
            "overlap_days": return_validation.get("overlap_days"),
            "correlations": dict(return_validation.get("correlations", {})),
        }
        error = return_validation.get("error")
        if error:
            return_snapshot["error"] = error
            snapshot["caveats"].append(error)
        snapshot["return"] = return_snapshot

    return snapshot


def _flow_snapshot(flow_estimate):
    snapshot = {
        "estimation_label": "Model-implied target notional change (not observed flow)",
        "assumed_cta_aum_usd": None,
        "markets": {},
        "top_notional_increase_1d": [],
        "top_notional_decrease_1d": [],
        "top_notional_increase_5d": [],
        "top_notional_decrease_5d": [],
        "sector_flows_1d": {},
        "sector_flows_5d": {},
    }
    if not flow_estimate:
        return snapshot

    merged = dict(snapshot)
    merged.update(dict(flow_estimate))
    return merged


def _capital_snapshot(capital_estimate):
    snapshot = {
        "aum_basis": {
            "source": "unknown",
            "label": "No AUM basis available",
            "aum_usd": None,
        },
        "gross_risk_deployed_pct_of_aum": None,
        "net_risk_deployed_pct_of_aum": None,
        "remaining_gross_headroom_pct_of_aum": None,
        "estimated_gross_risk_deployed_usd": None,
        "estimated_net_risk_deployed_usd": None,
        "estimated_remaining_gross_headroom_usd": None,
        "note": None,
    }
    if not capital_estimate:
        return snapshot

    merged = dict(snapshot)
    merged.update(dict(capital_estimate))
    return merged


def _benchmark_etf_snapshot(etf_returns_df, as_of=None):
    if etf_returns_df is None or etf_returns_df.empty:
        return None

    as_of_timestamp = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(etf_returns_df.index.max())
    rows = []

    for column in etf_returns_df.columns:
        series = etf_returns_df[column].dropna()
        series = series[series.index <= as_of_timestamp]
        if series.empty:
            continue

        ytd_series = series[series.index.year == as_of_timestamp.year]
        rows.append({
            "symbol": column,
            "return_1d": float(series.iloc[-1]),
            "return_5d": _compound_return(series.iloc[-5:]) if len(series) >= 5 else None,
            "return_20d": _compound_return(series.iloc[-20:]) if len(series) >= 20 else None,
            "return_ytd": _compound_return(ytd_series),
        })

    return rows or None


def _investment_overview_snapshot(facts):
    capital = facts.get("capital", {})
    flow = facts.get("flow", {})
    aum_basis = capital.get("aum_basis", {})

    overview = {
        "aum_basis_label": aum_basis.get("label"),
        "aum_usd": aum_basis.get("aum_usd"),
        "gross_deployed_pct": capital.get("gross_risk_deployed_pct_of_aum"),
        "gross_deployed_usd": capital.get("estimated_gross_risk_deployed_usd"),
        "net_deployed_pct": capital.get("net_risk_deployed_pct_of_aum"),
        "net_deployed_usd": capital.get("estimated_net_risk_deployed_usd"),
        "remaining_headroom_pct": capital.get("remaining_gross_headroom_pct_of_aum"),
        "remaining_headroom_usd": capital.get("estimated_remaining_gross_headroom_usd"),
    }

    # Build all_market_flows from flow markets merged with conviction data
    all_market_flows = []
    flow_markets = flow.get("markets", {})
    convictions_by_sym = {
        c["symbol"]: c for c in facts.get("strongest_convictions", [])
    }

    for symbol, fm in sorted(flow_markets.items()):
        conv = convictions_by_sym.get(symbol, {})
        all_market_flows.append({
            "symbol": symbol,
            "market": fm.get("market", symbol),
            "sector": fm.get("sector"),
            "direction": conv.get("direction", "FLAT"),
            "weight": conv.get("weight", 0.0),
            "delta_weight_1d": fm.get("delta_weight_1d"),
            "delta_weight_5d": fm.get("delta_weight_5d"),
            "estimated_notional_change_usd_1d": fm.get("estimated_notional_change_usd_1d"),
            "estimated_notional_change_usd_5d": fm.get("estimated_notional_change_usd_5d"),
            "estimated_contract_equivalent_5d": fm.get("estimated_contract_equivalent_5d"),
        })

    overview["all_market_flows"] = all_market_flows
    overview["sector_flows_5d"] = dict(flow.get("sector_flows_5d", {}))
    return overview


def _data_used_snapshot(facts):
    data_context = facts.get("data_context") or {}
    selected_count = _selected_market_count(facts)
    universe_count = facts.get("scope", {}).get("universe_market_count")
    official_close_date = data_context.get("official_close_date")
    live_as_of = data_context.get("live_as_of")
    mode = data_context.get("mode")

    if mode == "live" and official_close_date and live_as_of:
        price_mode = (
            f"Live nowcast using the latest intraday price over the {official_close_date} "
            f"official close, as of {live_as_of}."
        )
    elif official_close_date:
        price_mode = f"Official daily close data through {official_close_date}."
    else:
        price_mode = "Latest available daily close data."

    validation_inputs = ["COT directional agreement"]
    if facts.get("benchmark_etfs"):
        validation_inputs.append("benchmark ETF return checks")
    signal_validation = facts.get("validation", {}).get("signal")
    if signal_validation:
        validation_inputs.append("SG signal comparison when available")

    if universe_count is not None:
        market_scope = f"{selected_count} selected markets out of {universe_count} in the configured universe."
    else:
        market_scope = f"{selected_count} selected markets."

    return {
        "price_mode": price_mode,
        "market_scope": market_scope,
        "validation_inputs": ", ".join(validation_inputs) + ".",
    }


def _calculation_method_snapshot(facts):
    flow = facts.get("flow", {})
    capital = facts.get("capital", {})
    if flow.get("assumed_cta_aum_usd") is None:
        flow_text = (
            "Modeled notional change uses current target weight minus the prior 1-day "
            "and 5-trading-day model weights. No CTA AUM assumption was supplied, so the "
            "view is relative rather than dollar-denominated."
        )
    else:
        flow_text = (
            "Modeled notional change uses current target weight minus the prior 1-day and "
            "5-trading-day model weights. Dollar and contract estimates use the supplied CTA AUM "
            "assumption, latest price, and contract multiplier."
        )

    return {
        "signals": (
            "Signals use a 20d/120d trend proxy with 3-month EWMA volatility targeting and "
            "equal-risk sector weighting."
        ),
        "flow": flow_text,
        "capital": (
            f"Capital state uses the {capital.get('aum_basis', {}).get('label', 'available')} basis and "
            "frames deployment as risk deployed and remaining risk headroom, not cash spent."
        ),
    }


def _conclusion_snapshot(facts):
    details = []
    for helper in (_convictions_line, _flip_risk_line, _flow_conclusion_line, _caveat_line):
        line = helper(facts)
        if line:
            details.append(line)

    return {
        "headline": _positioning_line(facts),
        "details": details,
    }


def _suggestions_snapshot(facts):
    suggestions = []

    nearest_risks = facts.get("nearest_flip_risks", [])
    if nearest_risks:
        risk = nearest_risks[0]
        market = risk.get("market", risk.get("symbol", "Unknown"))
        distance_pct = _format_distance_pct(risk.get("distance_pct"))
        if risk.get("direction") == "FLAT":
            suggestions.append(f"Watch {market} closely because it is {distance_pct} from a signal change.")
        else:
            suggestions.append(f"Watch {market} closely because it is {distance_pct} from reversal.")

    crowding = facts.get("crowding", {})
    crowded_markets = _crowding_markets(crowding)
    if crowding.get("classification") in {"HIGH", "MODERATE"} and crowded_markets:
        suggestions.append(
            f"Respect {crowding['classification'].lower()} crowding in {_join_items(crowded_markets)} when sizing new risk."
        )

    caveat = _caveat_line(facts)
    if caveat:
        if "SG Trend Indicator" in caveat:
            suggestions.append("Treat SG confirmation as unavailable until the scraper is implemented.")
        else:
            suggestions.append(caveat)

    flow = facts.get("flow", {})
    if flow.get("assumed_cta_aum_usd") is not None:
        suggestions.append("Adjust the CTA AUM assumption if you want a more conservative or more aggressive crowd-level notional estimate.")
    elif flow.get("top_notional_increase_1d") or flow.get("top_notional_decrease_1d") or flow.get("markets"):
        suggestions.append("Add --assumed-cta-aum to convert relative weight changes into estimated dollar and contract notional.")

    if not suggestions:
        suggestions.append("Review the full report for sector concentration and validation context.")

    return suggestions[:3]


def _thesis_snapshot(facts):
    return {
        "headline": _positioning_line(facts),
    }


def _drivers_snapshot(facts):
    return {
        "convictions": facts.get("strongest_convictions", [])[:3],
        "recent_flips": facts.get("recent_flips", [])[:3],
        "nearest_flip_risks": facts.get("nearest_flip_risks", [])[:3],
        "top_notional_increase_5d": facts.get("flow", {}).get("top_notional_increase_5d", [])[:3],
        "top_notional_decrease_5d": facts.get("flow", {}).get("top_notional_decrease_5d", [])[:3],
    }


def _interpretation_snapshot(facts):
    validation = facts.get("validation", {})
    composite = validation.get("composite", {})
    grade = composite.get("grade", "F")

    if grade in ("A", "B"):
        confidence_text = "Validation is supportive, with the model broadly aligned with available positioning checks."
    elif grade == "C":
        confidence_text = "Validation is moderate, with partial alignment between the model and available checks."
    elif grade == "D":
        confidence_text = "Validation is weak. Treat model outputs with caution."
    else:
        confidence_text = "Validation is incomplete or failing. Model outputs are low-confidence estimates."

    capital = facts.get("capital", {})
    capital_text = capital.get("note") or "Capital figures are estimates."
    return {
        "meaning": f"{confidence_text} {capital_text}",
    }


def _why_now_snapshot(facts):
    nearest = facts.get("nearest_flip_risks", [])
    crowding = facts.get("crowding", {})
    if nearest:
        market = nearest[0].get("market", nearest[0].get("symbol", "Unknown"))
        distance = _format_distance_pct(nearest[0].get("distance_pct"))
        return {
            "text": (
                f"This matters now because {market} is {distance} from a regime change while "
                f"crowding is {crowding.get('classification', 'UNKNOWN').lower()}."
            )
        }
    return {
        "text": f"This matters now because crowding is {crowding.get('classification', 'UNKNOWN').lower()}."
    }


def _confidence_snapshot(facts):
    validation = facts.get("validation", {})
    composite = validation.get("composite", {})
    grade = composite.get("grade", "F")

    if grade in ("A", "B"):
        level = "High"
    elif grade == "C":
        level = "Medium"
    else:
        level = "Low"

    return {
        "level": level,
        "validation_grade": grade,
        "validation_score": composite.get("composite_score"),
        "reason": _interpretation_snapshot(facts)["meaning"],
    }


def _compound_return(series):
    clean = series.dropna()
    if clean.empty:
        return None
    return float((1.0 + clean).prod() - 1.0)


def _report_date(as_of, flips_by_market=None, etf_returns_df=None):
    if as_of is not None:
        return _iso_date(as_of)

    inferred_date = _inferred_report_date(
        flips_by_market=flips_by_market,
        etf_returns_df=etf_returns_df,
    )
    return _iso_date(inferred_date) if inferred_date is not None else None


def _inferred_report_date(flips_by_market=None, etf_returns_df=None):
    candidate_dates = []

    if etf_returns_df is not None and not etf_returns_df.empty:
        candidate_dates.append(pd.Timestamp(etf_returns_df.index.max()))

    for market_flips in (flips_by_market or {}).values():
        for flip in market_flips:
            flip_date = _timestamp_or_none(flip.get("date"))
            if flip_date is not None:
                candidate_dates.append(flip_date)

    if not candidate_dates:
        return None

    return max(candidate_dates)


def _iso_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _timestamp_or_none(value):
    if value is None:
        return None
    return pd.Timestamp(value)


def _direction_bucket(signal_value):
    value = float(signal_value or 0.0)
    if value > 0:
        return "long"
    if value < 0:
        return "short"
    return "flat"


def _direction_label(signal_value):
    bucket = _direction_bucket(signal_value)
    if bucket == "long":
        return "LONG"
    if bucket == "short":
        return "SHORT"
    return "FLAT"


def _markdown_headline(facts):
    selected_count = _selected_market_count(facts)
    report_date = facts.get("report_date")
    headline = f"## CTA Summary ({selected_count} markets)"
    if report_date:
        headline += f" — {report_date}"
    return headline


def _terminal_scope_line(facts):
    selected_count = _selected_market_count(facts)
    universe_count = facts.get("scope", {}).get("universe_market_count")
    report_date = facts.get("report_date")

    if report_date and universe_count is not None:
        return (
            f"CTA summary for {report_date} covers {selected_count} selected markets "
            f"out of {universe_count} in the universe."
        )
    if report_date:
        return f"CTA summary for {report_date} covers {selected_count} selected markets."
    if universe_count is not None:
        return (
            f"CTA summary covers {selected_count} selected markets out of "
            f"{universe_count} in the universe."
        )
    return f"CTA summary covers {selected_count} selected markets."


def _positioning_line(facts):
    counts = facts.get("position_counts", {})
    crowding = facts.get("crowding", {})
    line = (
        "Positioning is "
        f"{int(counts.get('long', 0))} long, "
        f"{int(counts.get('short', 0))} short, and "
        f"{int(counts.get('flat', 0))} flat, with "
        f"{crowding.get('classification', 'UNKNOWN')} crowding."
    )

    crowded_markets = _crowding_markets(crowding)
    if crowded_markets:
        line += f" Concentration is highest in {_join_items(crowded_markets)}."

    return line


def _data_context_line(facts):
    data_context = facts.get("data_context") or {}
    mode = data_context.get("mode")
    official_close_date = data_context.get("official_close_date")
    live_as_of = data_context.get("live_as_of")

    if mode == "live" and official_close_date and live_as_of:
        return (
            f"Live nowcast as of {live_as_of}, using official daily closes through "
            f"{official_close_date}."
        )

    if official_close_date:
        return f"Official daily data through {official_close_date}."

    return None


def _convictions_line(facts):
    convictions = facts.get("strongest_convictions", [])[:2]
    if not convictions:
        return None

    formatted = [
        f"{item.get('direction', 'FLAT')} {item.get('market', item.get('symbol', 'Unknown'))} "
        f"({_format_weight_pct(item.get('weight'))})"
        for item in convictions
    ]
    return f"Strongest convictions: {_join_items(formatted)}."


def _flip_risk_line(facts):
    segments = []

    recent_flip_line = _recent_flips_segment(facts)
    if recent_flip_line:
        segments.append(recent_flip_line)

    flip_risk_line = _nearest_flip_risk_segment(facts)
    if flip_risk_line:
        segments.append(flip_risk_line)

    if not segments:
        return None

    return " ".join(segments)


def _recent_flips_segment(facts):
    recent_flips = facts.get("recent_flips", [])
    if not recent_flips:
        return None

    flip = recent_flips[0]
    market = flip.get("market", flip.get("symbol", "Unknown"))
    from_label = flip.get("from_label", "UNKNOWN")
    to_label = flip.get("to_label", "UNKNOWN")
    flip_date = flip.get("date")

    segment = f"Recent flip: {market} moved {from_label} to {to_label}"
    if flip_date:
        segment += f" on {flip_date}"
    return segment + "."


def _nearest_flip_risk_segment(facts):
    nearest_risks = facts.get("nearest_flip_risks", [])
    if not nearest_risks:
        return None

    risk = nearest_risks[0]
    market = risk.get("market", risk.get("symbol", "Unknown"))
    distance_pct = float(risk.get("distance_pct", 0.0) or 0.0)
    direction = risk.get("direction")

    if direction == "FLAT":
        return (
            f"Nearest signal change: {market} is {_format_distance_pct(distance_pct)} "
            "from leaving flat."
        )

    return f"Nearest flip risk: {market} is {_format_distance_pct(distance_pct)} from reversal."


def _caveat_line(facts):
    caveats = facts.get("validation", {}).get("caveats", [])
    if not caveats:
        return None
    return f"Caveat: {caveats[0]}"


def _data_used_line(facts):
    data_used = facts.get("data_used", {})
    return (
        f"{data_used.get('market_scope', _terminal_scope_line(facts))} "
        f"{data_used.get('price_mode', '')} "
        f"Validation inputs: {data_used.get('validation_inputs', 'None noted.')}"
    ).strip()


def _method_line(facts):
    method = facts.get("calculation_method", {})
    flow = facts.get("flow", {})
    line = (
        f"{method.get('signals', '').strip()} "
        f"{method.get('flow', '').strip()} "
        f"{method.get('capital', '').strip()}"
    ).strip()
    if flow.get("assumed_cta_aum_usd") is not None:
        line += f" CTA AUM assumption: {_format_usd(flow.get('assumed_cta_aum_usd'))}."
    return line


def _capital_line(facts):
    overview = facts.get("investment_overview", {})
    if overview.get("gross_deployed_usd") is None:
        return "No capital data available."

    gross_usd = _format_usd(overview.get("gross_deployed_usd"))
    gross_pct = f"{float(overview.get('gross_deployed_pct') or 0):.2f}x"
    headroom_usd = _format_usd(overview.get("remaining_headroom_usd"))

    flow = facts.get("flow", {})
    increases = flow.get("top_notional_increase_5d", []) or flow.get("top_notional_increase_1d", [])
    decreases = flow.get("top_notional_decrease_5d", []) or flow.get("top_notional_decrease_1d", [])

    parts = [f"{gross_usd} gross deployed ({gross_pct})", f"{headroom_usd} headroom"]

    if increases:
        b = increases[0]
        market = b.get("market", b.get("symbol", "?"))
        usd = b.get("estimated_notional_change_usd_5d") or b.get("estimated_notional_change_usd_1d")
        if usd is not None:
            parts.append(f"Top increase: {market} ({_format_usd(usd)})")

    if decreases:
        s = decreases[0]
        market = s.get("market", s.get("symbol", "?"))
        usd = s.get("estimated_notional_change_usd_5d") or s.get("estimated_notional_change_usd_1d")
        if usd is not None:
            parts.append(f"Top decrease: {market} ({_format_usd(usd)})")

    return " | ".join(parts)


def _conclusion_line(facts):
    conclusion = _conclusion_snapshot(facts)
    grade = facts.get("validation", {}).get("composite", {}).get("grade", "F")
    prefix = ""
    if grade in ("D", "F"):
        prefix = "Low-confidence estimate: "
    elif grade == "C":
        prefix = "Moderate-confidence: "

    segments = [conclusion.get("headline")]
    segments.extend(conclusion.get("details", []))
    body = " ".join(segment for segment in segments if segment)
    return f"{prefix}{body}"


def _suggestions_line(facts):
    suggestions = facts.get("suggestions", [])
    return " ".join(suggestions)


def _flow_conclusion_line(facts):
    flow = facts.get("flow", {})
    increases = flow.get("top_notional_increase_1d", []) or flow.get("top_notional_increase_5d", [])
    decreases = flow.get("top_notional_decrease_1d", []) or flow.get("top_notional_decrease_5d", [])
    period_label = "1D" if flow.get("top_notional_increase_1d") or flow.get("top_notional_decrease_1d") else "5D"

    fragments = []
    if increases:
        item = increases[0]
        market = item.get("market", item.get("symbol", "Unknown"))
        usd = item.get("estimated_notional_change_usd_1d")
        delta_key = "delta_weight_1d"
        if period_label == "5D":
            usd = item.get("estimated_notional_change_usd_5d")
            delta_key = "delta_weight_5d"
        if usd is not None:
            fragments.append(f"Largest modeled {period_label} notional increase: {market} ({_format_usd(usd)}).")
        else:
            fragments.append(
                f"Largest relative {period_label} notional increase: {market} ({float(item.get(delta_key, 0.0)):+.2%} weight)."
            )
    if decreases:
        item = decreases[0]
        market = item.get("market", item.get("symbol", "Unknown"))
        usd = item.get("estimated_notional_change_usd_1d")
        delta_key = "delta_weight_1d"
        if period_label == "5D":
            usd = item.get("estimated_notional_change_usd_5d")
            delta_key = "delta_weight_5d"
        if usd is not None:
            fragments.append(f"Largest modeled {period_label} notional decrease: {market} ({_format_usd(usd)}).")
        else:
            fragments.append(
                f"Largest relative {period_label} notional decrease: {market} ({float(item.get(delta_key, 0.0)):+.2%} weight)."
            )

    if not fragments:
        return None
    return " ".join(fragments)


def _selected_market_count(facts):
    selected_count = facts.get("scope", {}).get("selected_market_count")
    if selected_count is not None:
        return int(selected_count)

    counts = facts.get("position_counts", {})
    return int(sum(int(counts.get(bucket, 0) or 0) for bucket in ("long", "short", "flat")))


def _format_weight_pct(weight):
    return f"{abs(float(weight or 0.0)):.0%}"


def _format_distance_pct(distance_pct):
    return f"{float(distance_pct or 0.0):.2f}%"


def _format_usd(value):
    amount = float(value or 0.0)
    abs_amount = abs(amount)
    prefix = "-" if amount < 0 else ""
    if abs_amount >= 1_000_000_000:
        return f"{prefix}${abs_amount / 1_000_000_000:.2f}B"
    if abs_amount >= 1_000_000:
        return f"{prefix}${abs_amount / 1_000_000:.2f}M"
    if abs_amount >= 1_000:
        return f"{prefix}${abs_amount / 1_000:.2f}K"
    return f"{prefix}${abs_amount:,.0f}"


def _join_items(items):
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _crowding_markets(crowding):
    crowded_markets = []
    for key in ("crowded_longs", "crowded_shorts", "max_long", "max_short"):
        for item in crowding.get(key, []):
            market = item.get("market") or item.get("symbol")
            if market and market not in crowded_markets:
                crowded_markets.append(market)

    return crowded_markets[:3]


def _llm_summary_matches_requested_format(text, output_format="terminal"):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        logger.debug("LLM format check: empty response")
        return False

    if output_format == "markdown":
        has_headline = lines[0].startswith("##") or lines[0].startswith("**")
        subsection_headers = (
            "Investment Overview", "Positioning", "Flow Activity",
            "Key Risks", "Assumptions",
        )
        found_subsections = sum(
            1 for line in lines
            if line.startswith("###") and any(h in line for h in subsection_headers)
        )
        paragraph_lines = [
            line for line in lines[1:]
            if not _is_markdown_bullet(line) and not line.startswith("#")
        ]

        passes = has_headline and found_subsections >= 3 and len(paragraph_lines) >= 1
        if not passes:
            logger.warning(
                "LLM markdown format rejected: headline=%s, subsections=%d (need>=3), "
                "paragraphs=%d (need>=1)",
                has_headline, found_subsections, len(paragraph_lines),
            )
        return passes

    required_labels = ("Data:", "Method:", "Capital:", "Conclusion:", "Suggestion:")
    missing = [label for label in required_labels if not any(line.startswith(label) for line in lines)]
    if missing:
        logger.warning("LLM terminal format rejected: missing labels=%s", missing)
        return False
    return True


def _is_markdown_bullet(line):
    return line.startswith("- ") or line.startswith("* ")


def _normalize_markdown_bullet(line):
    normalized = line.strip()
    if _is_markdown_bullet(normalized):
        normalized = normalized[2:].strip()
    return normalized.replace("**", "")
