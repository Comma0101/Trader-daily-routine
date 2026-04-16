"""Estimate overall CTA capital state from portfolio exposure."""

from __future__ import annotations

from config import PORTFOLIO_PARAMS, SG_TREND_INDEX_FUNDS


class CapitalEstimator:
    """Estimate deployed risk and remaining risk headroom."""

    def __init__(self, max_gross_multiple=None, tracked_funds=None):
        self.max_gross_multiple = float(
            max_gross_multiple if max_gross_multiple is not None
            else PORTFOLIO_PARAMS.get("max_gross_multiple", PORTFOLIO_PARAMS.get("max_leverage", 5.0))
        )
        self.tracked_funds = tracked_funds or SG_TREND_INDEX_FUNDS

    def estimate(self, portfolio_result, assumed_cta_aum_usd=None):
        gross = float(portfolio_result.get("gross_leverage", 0.0) or 0.0)
        net = float(portfolio_result.get("net_exposure", 0.0) or 0.0)

        reference_aum = sum(float(fund.get("aum_bn_approx", 0.0) or 0.0) for fund in self.tracked_funds) * 1_000_000_000.0
        if assumed_cta_aum_usd is not None:
            aum_basis = {
                "source": "user_assumption",
                "label": "User CTA AUM assumption",
                "aum_usd": float(assumed_cta_aum_usd),
            }
        else:
            aum_basis = {
                "source": "sg_tracked_reference_basket",
                "label": "Approximate SG Trend Index tracked-fund basket, not the full CTA industry",
                "aum_usd": reference_aum,
            }

        # headroom = max(0, max_gross_multiple - gross_leverage) * aum_usd
        remaining_gross = max(0.0, self.max_gross_multiple - gross)
        basis_aum = float(aum_basis["aum_usd"])

        return {
            "aum_basis": aum_basis,
            "gross_risk_deployed_pct_of_aum": gross,
            "net_risk_deployed_pct_of_aum": net,
            "remaining_gross_headroom_pct_of_aum": remaining_gross,
            "estimated_gross_risk_deployed_usd": gross * basis_aum,
            "estimated_net_risk_deployed_usd": net * basis_aum,
            "estimated_remaining_gross_headroom_usd": remaining_gross * basis_aum,
            "formula": f"headroom = max(0, {self.max_gross_multiple} - {gross:.2f}) * AUM",
            "note": (
                "Deployed = gross_leverage * AUM. This is futures notional exposure, not cash outlay."
            ),
        }
