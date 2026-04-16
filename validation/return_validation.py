"""
Return validation — compare our model's portfolio returns against benchmark ETFs.

This is portfolio-level validation only. It answers:
  "Does our model's aggregate return stream have a similar shape,
   correlation, and drawdown profile to real CTA products?"

It does NOT validate individual market positions.

Benchmarks:
  - DBMF: replicates SG CTA Index via regression (closest comparator)
  - KMLM: rules-based trend following (transparent, different construction)
  - CTA:  Simplify's faster-reacting trend model

A correlation of 0.5-0.7 with DBMF would indicate our model captures
the broad CTA trend-following factor. Much lower suggests a construction
error or very different universe/parameters.
"""

import logging

import numpy as np
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.benchmarks import BenchmarkData

logger = logging.getLogger(__name__)


class ReturnValidator:
    """Compare model portfolio returns against benchmark ETFs."""

    def __init__(self):
        self.benchmarks = BenchmarkData()

    def validate(self, model_returns: pd.Series) -> dict:
        """Compare model returns to benchmark ETFs.

        Args:
            model_returns: daily return series from our portfolio model

        Returns dict with:
            correlations: {etf: rolling and full-period correlation}
            tracking_stats: {etf: tracking error, information ratio}
            drawdown_comparison: {etf: max drawdown for both model and ETF}
            summary: text summary of how the model compares
        """
        etf_returns = self.benchmarks.etf_returns()
        if etf_returns.empty:
            return {"error": "Could not fetch benchmark ETF data"}

        # Align dates
        combined = pd.DataFrame({"model": model_returns})
        combined = combined.join(etf_returns, how="inner")
        combined = combined.dropna()

        if len(combined) < 20:
            return {"error": f"Insufficient overlapping data: {len(combined)} days"}

        correlations = {}
        tracking_stats = {}
        drawdown_comparison = {}

        model_cum = (1 + combined["model"]).cumprod()
        model_maxdd = _max_drawdown(model_cum)

        for etf in etf_returns.columns:
            if etf not in combined.columns:
                continue

            etf_series = combined[etf]
            model_series = combined["model"]

            # Full-period correlation
            full_corr = model_series.corr(etf_series)

            # Rolling 60-day correlation
            rolling_corr = model_series.rolling(60).corr(etf_series)
            recent_corr = rolling_corr.dropna().iloc[-1] if len(rolling_corr.dropna()) > 0 else None

            correlations[etf] = {
                "full_period": float(full_corr),
                "recent_60d": float(recent_corr) if recent_corr is not None else None,
            }

            # Tracking error and information ratio
            diff = model_series - etf_series
            te = diff.std() * np.sqrt(252)
            ir = (diff.mean() * 252) / te if te > 0 else 0

            tracking_stats[etf] = {
                "tracking_error": float(te),
                "information_ratio": float(ir),
            }

            # Drawdown comparison
            etf_cum = (1 + etf_series).cumprod()
            etf_maxdd = _max_drawdown(etf_cum)

            drawdown_comparison[etf] = {
                "model_max_drawdown": float(model_maxdd),
                "etf_max_drawdown": float(etf_maxdd),
            }

        # Summary assessment
        dbmf_corr = correlations.get("DBMF", {}).get("full_period")
        if dbmf_corr is not None:
            if dbmf_corr > 0.6:
                quality = "Good — model captures the broad CTA trend factor"
            elif dbmf_corr > 0.4:
                quality = "Moderate — some trend overlap but significant divergence"
            else:
                quality = "Low — model may have construction issues or very different universe"
        else:
            quality = "Cannot assess — DBMF data not available"

        return {
            "correlations": correlations,
            "tracking_stats": tracking_stats,
            "drawdown_comparison": drawdown_comparison,
            "model_stats": {
                "annualized_return": float(combined["model"].mean() * 252),
                "annualized_vol": float(combined["model"].std() * np.sqrt(252)),
                "max_drawdown": float(model_maxdd),
                "sharpe": float(
                    (combined["model"].mean() * 252) / (combined["model"].std() * np.sqrt(252))
                ) if combined["model"].std() > 0 else 0,
            },
            "overlap_days": len(combined),
            "summary": quality,
        }


def _max_drawdown(cumulative: pd.Series) -> float:
    """Compute maximum drawdown from a cumulative return series."""
    peak = cumulative.expanding().max()
    dd = (cumulative - peak) / peak
    return float(dd.min())
