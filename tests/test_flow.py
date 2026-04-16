import unittest

import pandas as pd

from flow_estimator import FlowEstimator


class FlowEstimatorTests(unittest.TestCase):
    def setUp(self):
        self.universe = {
            "ES": {
                "name": "S&P 500 E-mini",
                "sector": "Equity Index",
                "contract_multiplier": 50.0,
                "contract_unit": "index points",
                "quote_currency": "USD",
            },
            "CL": {
                "name": "Crude Oil WTI",
                "sector": "Energy",
                "contract_multiplier": 1000.0,
                "contract_unit": "barrels",
                "quote_currency": "USD",
            },
        }
        self.weight_history = pd.DataFrame(
            {
                "ES": [0.10, 0.11, 0.13, 0.14, 0.15],
                "CL": [-0.10, -0.09, -0.08, -0.07, -0.06],
            },
            index=pd.to_datetime(
                ["2026-04-09", "2026-04-10", "2026-04-13", "2026-04-14", "2026-04-15"]
            ),
        )
        self.current_weights = {"ES": 0.20, "CL": -0.01}
        self.current_prices = {"ES": 5000.0, "CL": 80.0}

    def test_estimate_uses_weight_deltas_for_daily_and_5d_proxy_flow(self):
        flow = FlowEstimator(self.universe).estimate(
            current_weights=self.current_weights,
            historical_weights=self.weight_history,
            current_prices=self.current_prices,
            assumed_cta_aum_usd=1_000_000.0,
        )

        es = flow["markets"]["ES"]
        cl = flow["markets"]["CL"]

        self.assertAlmostEqual(es["delta_weight_1d"], 0.05)
        self.assertAlmostEqual(es["delta_weight_5d"], 0.10)
        self.assertAlmostEqual(es["estimated_notional_change_usd_1d"], 50_000.0)
        self.assertAlmostEqual(es["estimated_notional_change_usd_5d"], 100_000.0)
        self.assertAlmostEqual(es["estimated_contract_equivalent_1d"], 0.20)
        self.assertAlmostEqual(es["estimated_contract_equivalent_5d"], 0.40)

        self.assertAlmostEqual(cl["delta_weight_1d"], 0.05)
        self.assertAlmostEqual(cl["delta_weight_5d"], 0.09)
        self.assertAlmostEqual(cl["estimated_notional_change_usd_1d"], 50_000.0)
        self.assertAlmostEqual(cl["estimated_contract_equivalent_1d"], 0.625)

        self.assertEqual(flow["top_notional_increase_1d"][0]["symbol"], "CL")
        self.assertEqual(flow["top_notional_decrease_1d"], [])

    def test_estimate_keeps_relative_flow_when_aum_assumption_is_missing(self):
        flow = FlowEstimator(self.universe).estimate(
            current_weights=self.current_weights,
            historical_weights=self.weight_history,
            current_prices=self.current_prices,
            assumed_cta_aum_usd=None,
        )

        es = flow["markets"]["ES"]
        self.assertAlmostEqual(es["delta_weight_1d"], 0.05)
        self.assertIsNone(es["estimated_notional_change_usd_1d"])
        self.assertIsNone(es["estimated_notional_change_usd_5d"])
        self.assertIsNone(es["estimated_contract_equivalent_1d"])
        self.assertIsNone(es["estimated_contract_equivalent_5d"])
        self.assertEqual(flow["assumed_cta_aum_usd"], None)

    def test_estimate_aggregates_sector_flows(self):
        flow = FlowEstimator(self.universe).estimate(
            current_weights=self.current_weights,
            historical_weights=self.weight_history,
            current_prices=self.current_prices,
            assumed_cta_aum_usd=1_000_000.0,
        )

        self.assertAlmostEqual(flow["sector_flows_1d"]["Equity Index"]["delta_weight"], 0.05)
        self.assertAlmostEqual(flow["sector_flows_5d"]["Energy"]["delta_weight"], 0.09)
        self.assertAlmostEqual(flow["sector_flows_1d"]["Energy"]["estimated_notional_change_usd"], 50_000.0)

    def test_new_key_names_present_old_keys_absent(self):
        flow = FlowEstimator(self.universe).estimate(
            current_weights=self.current_weights,
            historical_weights=self.weight_history,
            current_prices=self.current_prices,
            assumed_cta_aum_usd=1_000_000.0,
        )

        # New keys exist
        self.assertIn("top_notional_increase_1d", flow)
        self.assertIn("top_notional_decrease_1d", flow)
        self.assertIn("top_notional_increase_5d", flow)
        self.assertIn("top_notional_decrease_5d", flow)

        # Old keys absent
        self.assertNotIn("top_buyers_1d", flow)
        self.assertNotIn("top_sellers_1d", flow)
        self.assertNotIn("top_buyers_5d", flow)
        self.assertNotIn("top_sellers_5d", flow)

        # Per-market new keys
        es = flow["markets"]["ES"]
        self.assertIn("estimated_notional_change_usd_1d", es)
        self.assertNotIn("estimated_flow_usd_1d", es)
        self.assertIn("estimated_contract_equivalent_1d", es)
        self.assertNotIn("estimated_contracts_1d", es)

    def test_estimation_label_describes_model_implied(self):
        flow = FlowEstimator(self.universe).estimate(
            current_weights=self.current_weights,
            historical_weights=self.weight_history,
            current_prices=self.current_prices,
        )
        self.assertIn("Model-implied", flow["estimation_label"])
        self.assertIn("not observed flow", flow["estimation_label"])


if __name__ == "__main__":
    unittest.main()
