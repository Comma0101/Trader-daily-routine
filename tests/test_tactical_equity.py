import unittest

import pandas as pd

from model.tactical_equity import TacticalEquityFlowModel


class _FakeVolatilityEstimator:
    def current_scalar(self, returns: pd.Series) -> float:
        return 1.0


class TacticalEquityFlowModelTests(unittest.TestCase):
    def test_build_generates_multi_horizon_current_state_and_tape_scenarios(self):
        dates = pd.date_range("2026-01-01", periods=4, freq="D")
        prices = {
            "ES": pd.Series([100.0, 101.0, 102.0, 103.0], index=dates),
            "NQ": pd.Series([100.0, 99.0, 98.0, 97.0], index=dates),
        }
        returns = {
            "ES": prices["ES"].pct_change().dropna(),
            "NQ": prices["NQ"].pct_change().dropna(),
        }

        model = TacticalEquityFlowModel(
            params={
                "markets": ("ES", "NQ"),
                "horizons": (2, 3),
                "horizon_weights": {2: 0.5, 3: 0.5},
                "market_allocations": {"ES": 0.7, "NQ": 0.3},
                "scenario_moves": (-0.05, 0.0, 0.05),
                "max_gross_leverage": 2.0,
                "signal_mode": "binary",
            },
            volatility_estimator=_FakeVolatilityEstimator(),
        )

        result = model.build(prices, returns, assumed_cta_aum_usd=100_000_000.0)

        self.assertTrue(result["available"])
        self.assertEqual(result["markets"]["ES"]["signal_label"], "LONG")
        self.assertEqual(result["markets"]["NQ"]["signal_label"], "SHORT")
        self.assertAlmostEqual(result["markets"]["ES"]["target_weight"], 0.7)
        self.assertAlmostEqual(result["markets"]["NQ"]["target_weight"], -0.3)

        flat = result["scenario_reference"]["flat"]
        up = result["scenario_reference"]["up_5pct"]
        down = result["scenario_reference"]["down_5pct"]

        self.assertAlmostEqual(flat["total_delta_weight"], 0.0)
        self.assertAlmostEqual(flat["total_estimated_notional_change_usd"], 0.0)

        self.assertAlmostEqual(up["markets"]["NQ"]["delta_weight"], 0.6)
        self.assertEqual(up["markets"]["NQ"]["flow_type"], "short_cover_to_long")
        self.assertAlmostEqual(up["total_delta_weight"], 0.6)
        self.assertAlmostEqual(up["total_estimated_notional_change_usd"], 60_000_000.0)

        self.assertAlmostEqual(down["markets"]["ES"]["delta_weight"], -1.4)
        self.assertEqual(down["markets"]["ES"]["flow_type"], "long_exit_to_short")
        self.assertAlmostEqual(down["total_delta_weight"], -1.4)
        self.assertAlmostEqual(down["total_estimated_notional_change_usd"], -140_000_000.0)


if __name__ == "__main__":
    unittest.main()
