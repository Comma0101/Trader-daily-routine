"""
Position-proxy validation — compare our trend signals against CFTC COT data.

This is a noisy comparison by design:
  - COT data is weekly (Tuesday snapshot, released Friday).
  - COT categories are broad: "Leveraged Funds" (TFF) and "Managed Money"
    (Disaggregated) include non-CTA participants.
  - We compare DIRECTION only, not magnitude.

The question we're answering: "Is our model on the same side as the
leveraged/managed money crowd in the COT data?"

High agreement → our trend proxy captures the dominant systematic flow.
Low agreement → either our signals are wrong, the COT category is noisy,
or non-trend participants dominate that category for this market.
"""

import logging

import pandas as pd
import numpy as np

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.cot import COTData

logger = logging.getLogger(__name__)


class PositionValidator:
    """Compare model signals against CFTC COT positioning."""

    def __init__(self):
        self.cot = COTData()

    def validate(self, model_signals: dict[str, float]) -> dict:
        """Compare model signal directions to latest COT net positioning.

        Args:
            model_signals: {symbol: composite_signal} from our TrendModel

        Returns dict with:
            results: list of per-market comparison dicts
            agreement_rate: fraction where model and COT agree on direction
            coverage: number of markets with both model signal and COT data
            by_report_type: {TFF: {agreement, count}, DISAGG: {agreement, count}}
        """
        results = []
        by_report = {"TFF": {"agree": 0, "total": 0}, "DISAGG": {"agree": 0, "total": 0}}

        for symbol, model_sig in model_signals.items():
            if abs(model_sig) < 0.01:  # skip flat signals
                continue

            cot_pos = self.cot.latest_positioning(symbol)
            if cot_pos is None:
                continue

            model_dir = "LONG" if model_sig > 0 else "SHORT"
            cot_dir = "LONG" if cot_pos["net"] > 0 else "SHORT" if cot_pos["net"] < 0 else "FLAT"
            agrees = model_dir == cot_dir

            report_type = cot_pos["report_type"]
            by_report[report_type]["total"] += 1
            if agrees:
                by_report[report_type]["agree"] += 1

            results.append({
                "symbol": symbol,
                "model_signal": model_sig,
                "model_direction": model_dir,
                "cot_net": cot_pos["net"],
                "cot_net_pct": cot_pos["net_pct"],
                "cot_direction": cot_dir,
                "agrees": agrees,
                "cot_date": cot_pos["date"],
                "report_type": report_type,
                "category": cot_pos["category"],
            })

        total = len(results)
        agrees = sum(1 for r in results if r["agrees"])

        report_summary = {}
        for rt, data in by_report.items():
            if data["total"] > 0:
                report_summary[rt] = {
                    "agreement_rate": data["agree"] / data["total"],
                    "count": data["total"],
                }

        return {
            "results": results,
            "agreement_rate": agrees / total if total > 0 else None,
            "coverage": total,
            "by_report_type": report_summary,
        }

    def positioning_history(self, symbol: str) -> pd.DataFrame | None:
        """Get full COT positioning history for a symbol.

        Useful for plotting model signals against COT net positioning over time.
        """
        return self.cot.positioning(symbol)
