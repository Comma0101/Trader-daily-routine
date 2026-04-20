import unittest

import pandas as pd

from validation.goldman_calibration import GoldmanCalibrationSearch


def _stub_evaluator(params, prices, returns, assumed_cta_aum_usd):
    es_alloc = float(params["market_allocations"]["ES"])
    leverage = float(params["max_gross_leverage"])
    fast_weight = float(params["horizon_weights"][20])
    span_20 = float(params["signal_spans"][20])

    scenario_error = abs(es_alloc - 0.8) * 100.0 + abs(leverage - 2.0) * 20.0 + abs(span_20 - 0.05) * 500.0
    threshold_gap = abs(fast_weight - 0.35) * 10.0
    position_rate = 1.0 if fast_weight >= 0.30 else 0.5

    return {
        "position_direction_agreement_rate": position_rate,
        "scenario_direction_agreement_rate": 1.0,
        "scenario_mean_abs_error_pct": scenario_error,
        "threshold_mean_abs_gap_pct": threshold_gap,
        "scenario_mean_abs_error_usd": scenario_error * 1_000_000.0,
        "notes_evaluated": 3,
        "scenario_points": 4,
        "headline": "stub",
    }


class GoldmanCalibrationSearchTests(unittest.TestCase):
    def test_fit_picks_lowest_objective_candidate(self):
        search = GoldmanCalibrationSearch(
            base_params={
                "markets": ("ES", "NQ"),
                "horizons": (20, 60),
                "horizon_weights": {20: 0.2, 60: 0.8},
                "market_allocations": {"ES": 0.7, "NQ": 0.3},
                "signal_mode": "distance_scaled",
                "signal_spans": {20: 0.04, 60: 0.08},
                "scenario_moves": (0.0,),
                "max_gross_leverage": 1.5,
            },
            grid={
                "horizon_profiles": {
                    "fast": {20: 0.35, 60: 0.65},
                    "slow": {20: 0.1, 60: 0.9},
                },
                "es_allocations": (0.7, 0.8),
                "max_gross_leverage": (1.5, 2.0),
                "signal_span_scales": (1.0, 1.25),
                "top_k": 3,
            },
            evaluator=_stub_evaluator,
        )
        dates = pd.date_range("2026-01-01", periods=3, freq="D")
        prices = {"ES": pd.Series([1, 2, 3], index=dates)}
        returns = {"ES": prices["ES"].pct_change().dropna()}

        result = search.fit(prices=prices, returns=returns, assumed_cta_aum_usd=100_000_000.0)

        self.assertTrue(result["available"])
        self.assertEqual(result["best"]["label"], "fast")
        self.assertAlmostEqual(result["best"]["params"]["market_allocations"]["ES"], 0.8)
        self.assertAlmostEqual(result["best"]["params"]["max_gross_leverage"], 2.0)
        self.assertGreater(result["objective_improvement_pct"], 0.0)
        self.assertIn("Goldman calibration best fit", result["headline"])


if __name__ == "__main__":
    unittest.main()
