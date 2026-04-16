import unittest

from capital_estimator import CapitalEstimator
from config import PORTFOLIO_PARAMS, SG_TREND_INDEX_FUNDS


class CapitalEstimatorTests(unittest.TestCase):
    def setUp(self):
        self.portfolio_result = {
            "gross_leverage": 0.95,
            "net_exposure": 0.35,
        }

    def test_estimate_uses_reference_basket_when_user_assumption_missing(self):
        result = CapitalEstimator().estimate(self.portfolio_result)

        expected_reference_aum = sum(fund["aum_bn_approx"] for fund in SG_TREND_INDEX_FUNDS) * 1_000_000_000.0
        self.assertEqual(result["aum_basis"]["source"], "sg_tracked_reference_basket")
        self.assertAlmostEqual(result["aum_basis"]["aum_usd"], expected_reference_aum)
        self.assertAlmostEqual(result["gross_risk_deployed_pct_of_aum"], 0.95)
        self.assertAlmostEqual(result["estimated_gross_risk_deployed_usd"], 0.95 * expected_reference_aum)
        self.assertAlmostEqual(
            result["estimated_remaining_gross_headroom_usd"],
            (PORTFOLIO_PARAMS["max_leverage"] - 0.95) * expected_reference_aum,
        )
        self.assertIn("notional exposure", result["note"])
        self.assertIn("not cash outlay", result["note"])
        self.assertIn("formula", result)
        self.assertIn("headroom", result["formula"])

    def test_estimate_prefers_user_assumption_when_supplied(self):
        result = CapitalEstimator().estimate(
            self.portfolio_result,
            assumed_cta_aum_usd=50_000_000_000.0,
        )

        self.assertEqual(result["aum_basis"]["source"], "user_assumption")
        self.assertAlmostEqual(result["aum_basis"]["aum_usd"], 50_000_000_000.0)
        self.assertAlmostEqual(result["estimated_net_risk_deployed_usd"], 17_500_000_000.0)
        self.assertAlmostEqual(
            result["estimated_remaining_gross_headroom_usd"],
            (PORTFOLIO_PARAMS["max_leverage"] - 0.95) * 50_000_000_000.0,
        )


if __name__ == "__main__":
    unittest.main()
