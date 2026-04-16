"""
Signal validation — compare our trend signals against SG Trend Indicator.

This is per-market, per-day validation: "does our model agree with SG's
published signal direction for each market?"

SG Trend Indicator uses 20d and 120d MAs on the same futures universe,
so agreement should be high if our data and construction are correct.
Disagreement points to data issues (roll gaps, different contract months)
or parameter drift.
"""

import logging

import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.benchmarks import BenchmarkData

logger = logging.getLogger(__name__)


class SignalValidator:
    """Compare model signals against SG Trend Indicator."""

    def __init__(self):
        self.benchmarks = BenchmarkData()

    def validate(
        self,
        model_signals: dict[str, float],
        sg_signals: dict[str, float] | None = None,
    ) -> dict:
        """Compare model signals to SG Trend Indicator signals.

        Args:
            model_signals: {symbol: composite_signal} from our TrendModel
            sg_signals: {symbol: sg_signal} from SG Trend Indicator.
                        If None, attempts to fetch (will return stub notice).

        Returns dict with:
            agreement_rate: fraction of markets where signs match
            matches: list of symbols where model and SG agree
            mismatches: list of {symbol, model_signal, sg_signal}
            coverage: how many markets had both signals
        """
        if sg_signals is None:
            sg_data = self.benchmarks.fetch_sg_trend_indicator()
            if sg_data is None:
                return {
                    "agreement_rate": None,
                    "matches": [],
                    "mismatches": [],
                    "coverage": 0,
                    "note": "SG Trend Indicator data not available (stub). "
                            "Provide sg_signals dict or implement scraper.",
                }
            # If we had real data, we'd extract signals per market here
            sg_signals = {}

        # Compare where both have data
        common = set(model_signals.keys()) & set(sg_signals.keys())
        if not common:
            return {
                "agreement_rate": None,
                "matches": [],
                "mismatches": [],
                "coverage": 0,
                "note": "No overlapping markets between model and SG signals.",
            }

        matches = []
        mismatches = []
        for sym in sorted(common):
            m_sig = _sign_bucket(model_signals[sym])
            s_sig = _sign_bucket(sg_signals[sym])
            if m_sig == s_sig:
                matches.append(sym)
            else:
                mismatches.append({
                    "symbol": sym,
                    "model_signal": model_signals[sym],
                    "sg_signal": sg_signals[sym],
                    "model_dir": m_sig,
                    "sg_dir": s_sig,
                })

        total = len(common)
        return {
            "agreement_rate": len(matches) / total if total > 0 else None,
            "matches": matches,
            "mismatches": mismatches,
            "coverage": total,
        }


def _sign_bucket(val: float) -> str:
    """Bucket a signal value into LONG/SHORT/FLAT."""
    if val > 0.25:
        return "LONG"
    elif val < -0.25:
        return "SHORT"
    else:
        return "FLAT"
