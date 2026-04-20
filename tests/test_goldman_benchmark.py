import unittest

import pandas as pd

from validation.goldman_benchmark import GoldmanBenchmarkValidator


class _StubTacticalModel:
    def build(self, prices, returns, assumed_cta_aum_usd=None):
        return {
            "available": True,
            "markets": {
                "ES": {
                    "signal": 1.0,
                    "target_weight": 0.5,
                    "moving_averages": {
                        "20d": 5050.0,
                        "60d": 4950.0,
                        "125d": 4850.0,
                    },
                }
            },
            "scenario_reference": {
                "flat": {
                    "markets": {
                        "ES": {"estimated_notional_change_usd": -400_000_000.0}
                    },
                    "total_estimated_notional_change_usd": -400_000_000.0,
                },
                "down_2pct": {
                    "markets": {
                        "ES": {"estimated_notional_change_usd": -1_800_000_000.0}
                    },
                    "total_estimated_notional_change_usd": -1_800_000_000.0,
                },
            },
        }


class GoldmanBenchmarkValidatorTests(unittest.TestCase):
    def test_validate_compares_position_thresholds_and_scenarios(self):
        validator = GoldmanBenchmarkValidator(
            benchmarks=[
                {
                    "id": "sample",
                    "published_date": "2026-01-05",
                    "title": "Sample note",
                    "source_url": "https://example.com",
                    "reference_symbol": "ES",
                    "position": {"direction": "LONG", "usd": 1_000_000_000.0},
                    "thresholds": {
                        "short_term": 5000.0,
                        "medium_term": 4900.0,
                        "long_term": 4800.0,
                    },
                    "scenario_targets": [
                        {
                            "label": "flat",
                            "scenario_key": "flat",
                            "symbol": "ES",
                            "flow_usd": -436_000_000.0,
                            "precision": "exact",
                        },
                        {
                            "label": "down",
                            "scenario_key": "down_2pct",
                            "symbol": "ES",
                            "flow_usd": -1_900_000_000.0,
                            "precision": "bucket_proxy",
                        },
                    ],
                }
            ],
            tactical_model=_StubTacticalModel(),
        )
        series = pd.Series(
            [100.0, 101.0, 102.0],
            index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"]),
        )

        result = validator.validate(
            prices={"ES": series},
            returns={"ES": series.pct_change().dropna()},
            assumed_cta_aum_usd=100_000_000.0,
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["notes_evaluated"], 1)
        self.assertEqual(result["position_direction_agreement_rate"], 1.0)
        self.assertEqual(result["scenario_direction_agreement_rate"], 1.0)
        self.assertAlmostEqual(result["threshold_mean_abs_gap_pct"], (1.0 + (50 / 4900 * 100) + (50 / 4800 * 100)) / 3)
        self.assertIn("Goldman benchmark coverage", result["headline"])


if __name__ == "__main__":
    unittest.main()
