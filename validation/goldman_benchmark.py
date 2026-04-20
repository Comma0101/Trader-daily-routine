"""Compare our tactical equity sleeve to public Goldman CTA note snapshots."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from data.goldman_cta_benchmarks import PUBLIC_GOLDMAN_CTA_NOTES
from model.tactical_equity import TacticalEquityFlowModel


@dataclass
class GoldmanBenchmarkValidator:
    benchmarks: list[dict] | None = None
    tactical_model: TacticalEquityFlowModel | None = None

    def __post_init__(self):
        if self.benchmarks is None:
            self.benchmarks = list(PUBLIC_GOLDMAN_CTA_NOTES)
        if self.tactical_model is None:
            self.tactical_model = TacticalEquityFlowModel()

    def validate(self, prices: dict[str, pd.Series], returns: dict[str, pd.Series], assumed_cta_aum_usd=None) -> dict:
        note_results = []

        for note in self.benchmarks:
            as_of = pd.Timestamp(note["published_date"])
            sliced_prices = {
                sym: series[series.index <= as_of]
                for sym, series in prices.items()
                if not series.empty and (series.index <= as_of).any()
            }
            sliced_returns = {
                sym: series[series.index <= as_of]
                for sym, series in returns.items()
                if not series.empty and (series.index <= as_of).any()
            }

            tactical = self.tactical_model.build(
                sliced_prices,
                sliced_returns,
                assumed_cta_aum_usd=assumed_cta_aum_usd,
            )
            note_results.append(_compare_note(note, tactical))

        return _summarize(note_results)


def _compare_note(note, tactical):
    reference_symbol = note.get("reference_symbol")
    tactical_market = (tactical.get("markets") or {}).get(reference_symbol, {})
    scenarios = tactical.get("scenario_reference", {})

    result = {
        "id": note.get("id"),
        "published_date": note.get("published_date"),
        "title": note.get("title"),
        "source_url": note.get("source_url"),
        "reference_symbol": reference_symbol,
        "tactical_available": bool(tactical.get("available")),
        "position_comparison": None,
        "threshold_comparison": None,
        "scenario_comparisons": [],
    }

    position = note.get("position")
    if position and tactical_market:
        goldman_dir = position.get("direction") or _direction_from_usd(position.get("usd"))
        model_dir = _direction_from_signal(tactical_market.get("signal"))
        result["position_comparison"] = {
            "goldman_direction": goldman_dir,
            "model_direction": model_dir,
            "agrees": goldman_dir == model_dir if goldman_dir and model_dir else None,
            "goldman_position_usd": position.get("usd"),
            "model_signal": tactical_market.get("signal"),
            "model_weight": tactical_market.get("target_weight"),
            "scope": position.get("scope"),
        }

    thresholds = note.get("thresholds")
    if thresholds and tactical_market:
        model_mas = tactical_market.get("moving_averages", {})
        mapped = {}
        for label, horizon in (("short_term", "20d"), ("medium_term", "60d"), ("long_term", "125d")):
            goldman_level = thresholds.get(label)
            model_level = model_mas.get(horizon)
            if goldman_level is None or model_level is None:
                continue
            mapped[label] = {
                "goldman_level": float(goldman_level),
                "model_level": float(model_level),
                "model_horizon": horizon,
                "pct_gap": (float(model_level) - float(goldman_level)) / float(goldman_level) * 100.0,
            }
        if mapped:
            result["threshold_comparison"] = mapped

    for target in note.get("scenario_targets", []):
        scenario = scenarios.get(target.get("scenario_key"))
        model_flow = None
        model_direction = None
        comparable = False
        comparison_scope = target.get("scope") or ("market" if target.get("symbol") else "total")

        if scenario is not None:
            if target.get("symbol"):
                market = scenario.get("markets", {}).get(target["symbol"])
                if market is not None:
                    model_flow = market.get("estimated_notional_change_usd")
                    model_direction = _direction_from_usd(model_flow)
                    comparable = True
            else:
                model_flow = scenario.get("total_estimated_notional_change_usd")
                model_direction = _direction_from_usd(model_flow)
                comparable = model_flow is not None

        goldman_flow = target.get("flow_usd")
        result["scenario_comparisons"].append({
            "label": target.get("label"),
            "scenario_key": target.get("scenario_key"),
            "scope": comparison_scope,
            "precision": target.get("precision"),
            "goldman_flow_usd": goldman_flow,
            "model_flow_usd": model_flow,
            "direction_match": (
                _direction_from_usd(goldman_flow) == model_direction
                if comparable and goldman_flow is not None and model_flow is not None
                else None
            ),
            "error_usd": (
                float(model_flow) - float(goldman_flow)
                if comparable and goldman_flow is not None and model_flow is not None
                else None
            ),
            "comparable": comparable and target.get("precision") != "current_levels",
            "note": target.get("note"),
        })

    return result


def _summarize(note_results):
    position_rows = [r["position_comparison"] for r in note_results if r.get("position_comparison")]
    threshold_rows = [r["threshold_comparison"] for r in note_results if r.get("threshold_comparison")]
    scenario_rows = [
        row
        for result in note_results
        for row in result.get("scenario_comparisons", [])
        if row.get("comparable")
    ]

    position_agreement = _mean_boolean([row.get("agrees") for row in position_rows])
    scenario_direction_agreement = _mean_boolean([row.get("direction_match") for row in scenario_rows])
    scenario_abs_errors = [abs(float(row["error_usd"])) for row in scenario_rows if row.get("error_usd") is not None]
    scenario_abs_error_pcts = [
        abs(float(row["error_usd"])) / abs(float(row["goldman_flow_usd"])) * 100.0
        for row in scenario_rows
        if row.get("error_usd") is not None and row.get("goldman_flow_usd") not in (None, 0)
    ]

    threshold_gaps = []
    for group in threshold_rows:
        for item in group.values():
            if item.get("pct_gap") is not None:
                threshold_gaps.append(abs(float(item["pct_gap"])))

    summary = {
        "available": bool(note_results),
        "notes": note_results,
        "notes_evaluated": len(note_results),
        "position_notes": len(position_rows),
        "scenario_points": len(scenario_rows),
        "threshold_points": len(threshold_gaps),
        "position_direction_agreement_rate": position_agreement,
        "scenario_direction_agreement_rate": scenario_direction_agreement,
        "scenario_mean_abs_error_usd": sum(scenario_abs_errors) / len(scenario_abs_errors) if scenario_abs_errors else None,
        "scenario_mean_abs_error_pct": (
            sum(scenario_abs_error_pcts) / len(scenario_abs_error_pcts) if scenario_abs_error_pcts else None
        ),
        "threshold_mean_abs_gap_pct": sum(threshold_gaps) / len(threshold_gaps) if threshold_gaps else None,
    }
    summary["headline"] = _headline(summary)
    return summary


def _headline(summary):
    if not summary.get("available"):
        return "Goldman benchmark unavailable."

    parts = [f"Goldman benchmark coverage: {summary['notes_evaluated']} public notes"]
    if summary.get("position_direction_agreement_rate") is not None:
        parts.append(f"position agreement {summary['position_direction_agreement_rate']:.0%}")
    if summary.get("scenario_direction_agreement_rate") is not None:
        parts.append(f"scenario direction agreement {summary['scenario_direction_agreement_rate']:.0%}")
    if summary.get("threshold_mean_abs_gap_pct") is not None:
        parts.append(f"mean threshold gap {summary['threshold_mean_abs_gap_pct']:.2f}%")
    if summary.get("scenario_mean_abs_error_pct") is not None:
        parts.append(f"mean scenario error {summary['scenario_mean_abs_error_pct']:.0f}%")
    return " | ".join(parts)


def _direction_from_signal(signal):
    if signal is None:
        return None
    value = float(signal)
    if value > 0.1:
        return "LONG"
    if value < -0.1:
        return "SHORT"
    return "FLAT"


def _direction_from_usd(value):
    if value is None:
        return None
    value = float(value)
    if value > 0:
        return "BUY"
    if value < 0:
        return "SELL"
    return "FLAT"


def _mean_boolean(values):
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(1 for value in clean if value) / len(clean)
