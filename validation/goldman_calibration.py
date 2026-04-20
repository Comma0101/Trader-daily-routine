"""Coarse calibration search for the tactical equity sleeve.

This module answers a narrow question: which parameter set best matches the
public Goldman CTA note snapshots we have curated? It is intentionally simple
and reproducible, using a small grid search rather than an opaque optimizer.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import product

import pandas as pd

from config import GOLDMAN_CALIBRATION_GRID, TACTICAL_EQUITY_PARAMS
from model.tactical_equity import TacticalEquityFlowModel
from validation.goldman_benchmark import GoldmanBenchmarkValidator


@dataclass
class GoldmanCalibrationSearch:
    benchmarks: list[dict] | None = None
    base_params: dict | None = None
    grid: dict | None = None
    evaluator: callable | None = None

    def __post_init__(self):
        if self.base_params is None:
            self.base_params = deepcopy(TACTICAL_EQUITY_PARAMS)
        if self.grid is None:
            self.grid = deepcopy(GOLDMAN_CALIBRATION_GRID)

    def fit(self, prices: dict[str, pd.Series], returns: dict[str, pd.Series], assumed_cta_aum_usd=None) -> dict:
        baseline_candidate = self._evaluate_candidate(
            label="baseline",
            params=deepcopy(self.base_params),
            assumed_cta_aum_usd=assumed_cta_aum_usd,
            prices=prices,
            returns=returns,
        )

        candidates = []
        for profile_name, horizon_weights in dict(self.grid.get("horizon_profiles", {})).items():
            for es_allocation, gross_leverage, span_scale in product(
                self.grid.get("es_allocations", (0.7,)),
                self.grid.get("max_gross_leverage", (2.0,)),
                self.grid.get("signal_span_scales", (1.0,)),
            ):
                params = deepcopy(self.base_params)
                params["horizon_weights"] = {int(k): float(v) for k, v in dict(horizon_weights).items()}
                params["market_allocations"] = {
                    "ES": float(es_allocation),
                    "NQ": float(1.0 - float(es_allocation)),
                }
                params["max_gross_leverage"] = float(gross_leverage)
                params["signal_mode"] = "distance_scaled"
                params["signal_spans"] = _scaled_spans(
                    params.get("signal_spans", {}),
                    float(span_scale),
                )

                candidates.append(
                    self._evaluate_candidate(
                        label=profile_name,
                        params=params,
                        assumed_cta_aum_usd=assumed_cta_aum_usd,
                        prices=prices,
                        returns=returns,
                    )
                )

        candidates.sort(key=lambda item: (item["objective_score"], item["scenario_mean_abs_error_pct"] or 9999.0))
        top_k = int(self.grid.get("top_k", 5) or 5)
        best = candidates[0] if candidates else baseline_candidate
        improvement = None
        if baseline_candidate.get("objective_score") not in (None, 0):
            improvement = (
                float(baseline_candidate["objective_score"]) - float(best["objective_score"])
            ) / float(baseline_candidate["objective_score"]) * 100.0

        result = {
            "available": True,
            "baseline": baseline_candidate,
            "best": best,
            "top_candidates": candidates[:top_k],
            "search_space": {
                "profiles": sorted(dict(self.grid.get("horizon_profiles", {})).keys()),
                "es_allocations": list(self.grid.get("es_allocations", [])),
                "max_gross_leverage": list(self.grid.get("max_gross_leverage", [])),
                "signal_span_scales": list(self.grid.get("signal_span_scales", [])),
                "candidate_count": len(candidates),
            },
            "objective_improvement_pct": improvement,
        }
        result["headline"] = _headline(result)
        result["recommendation"] = _recommendation(result)
        return result

    def _evaluate_candidate(self, label, params, assumed_cta_aum_usd, prices, returns):
        summary = self._evaluate_params(
            params=params,
            prices=prices,
            returns=returns,
            assumed_cta_aum_usd=assumed_cta_aum_usd,
        )
        return {
            "label": label,
            "objective_score": _objective_score(summary),
            "position_direction_agreement_rate": summary.get("position_direction_agreement_rate"),
            "scenario_direction_agreement_rate": summary.get("scenario_direction_agreement_rate"),
            "scenario_mean_abs_error_usd": summary.get("scenario_mean_abs_error_usd"),
            "scenario_mean_abs_error_pct": summary.get("scenario_mean_abs_error_pct"),
            "threshold_mean_abs_gap_pct": summary.get("threshold_mean_abs_gap_pct"),
            "notes_evaluated": summary.get("notes_evaluated"),
            "scenario_points": summary.get("scenario_points"),
            "headline": summary.get("headline"),
            "params": {
                "signal_mode": params.get("signal_mode"),
                "horizon_weights": dict(params.get("horizon_weights", {})),
                "market_allocations": dict(params.get("market_allocations", {})),
                "signal_spans": dict(params.get("signal_spans", {})),
                "max_gross_leverage": params.get("max_gross_leverage"),
            },
        }

    def _evaluate_params(self, params, prices, returns, assumed_cta_aum_usd):
        if self.evaluator is not None:
            return self.evaluator(params, prices, returns, assumed_cta_aum_usd)

        tactical_model = TacticalEquityFlowModel(params=params)
        validator = GoldmanBenchmarkValidator(
            benchmarks=self.benchmarks,
            tactical_model=tactical_model,
        )
        return validator.validate(
            prices=prices,
            returns=returns,
            assumed_cta_aum_usd=assumed_cta_aum_usd,
        )


def _scaled_spans(base_spans, scale):
    base = {int(k): float(v) for k, v in dict(base_spans).items()}
    return {horizon: float(span) * float(scale) for horizon, span in base.items()}


def _objective_score(summary):
    position = summary.get("position_direction_agreement_rate")
    scenario_direction = summary.get("scenario_direction_agreement_rate")
    scenario_error_pct = summary.get("scenario_mean_abs_error_pct")
    threshold_gap_pct = summary.get("threshold_mean_abs_gap_pct")

    score = 0.0
    score += (1.0 - float(position if position is not None else 0.0)) * 120.0
    score += (1.0 - float(scenario_direction if scenario_direction is not None else 0.0)) * 160.0
    score += min(float(scenario_error_pct if scenario_error_pct is not None else 300.0), 300.0)
    score += min(float(threshold_gap_pct if threshold_gap_pct is not None else 10.0), 25.0) * 4.0
    return score


def _headline(result):
    best = result.get("best") or {}
    baseline = result.get("baseline") or {}
    if not best:
        return "Goldman calibration unavailable."

    improvement = result.get("objective_improvement_pct")
    parts = [
        f"Goldman calibration best fit: {best.get('label')}",
        f"score {best.get('objective_score'):.1f}",
    ]
    if improvement is not None:
        parts.append(f"{improvement:+.0f}% vs baseline")
    if best.get("scenario_mean_abs_error_pct") is not None:
        parts.append(f"scenario error {best['scenario_mean_abs_error_pct']:.0f}%")
    if best.get("threshold_mean_abs_gap_pct") is not None:
        parts.append(f"threshold gap {best['threshold_mean_abs_gap_pct']:.2f}%")
    if baseline.get("objective_score") is not None:
        parts.append(f"baseline {baseline['objective_score']:.1f}")
    return " | ".join(parts)


def _recommendation(result):
    best = result.get("best") or {}
    improvement = result.get("objective_improvement_pct")
    scenario_error = best.get("scenario_mean_abs_error_pct")
    threshold_gap = best.get("threshold_mean_abs_gap_pct")
    scenario_direction = best.get("scenario_direction_agreement_rate")

    if scenario_error is None:
        return "Calibration coverage is too thin to judge whether the tactical sleeve is Goldman-close."
    if scenario_error <= 50 and (threshold_gap or 99.0) <= 2.5 and (scenario_direction or 0.0) >= 0.75:
        return "The tactical sleeve is directionally credible against public Goldman notes, but still needs magnitude refinement."
    if improvement is not None and improvement >= 10:
        return "Calibration materially improved fit, but magnitude error is still too wide for dealer-desk quality."
    return "Calibration did not materially close the Goldman gap; data and model structure still dominate the error."
