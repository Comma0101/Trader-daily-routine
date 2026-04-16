"""
CFTC Commitment of Traders (COT) data fetcher.

Handles the critical distinction between report types:
  - Financial futures (equity indices, bonds, FX): uses the Traders in
    Financial Futures (TFF) report → "Leveraged Funds" category.
  - Physical commodities (energy, metals, agriculture): uses the
    Disaggregated report → "Managed Money" category.

CTA-like participants are NOT uniformly in "Managed Money" — that category
only exists in the Disaggregated report for physical commodities. In the TFF
framework, hedge funds and CTAs fall under "Leveraged Funds."

Source: https://www.cftc.gov/idc/groups/public/%40commitmentsoftraders/documents/file/tfmexplanatorynotes.pdf

NOTE: COT data is released weekly (Friday, as of Tuesday). It is a noisy
proxy for CTA positioning, not ground truth. Use for directional validation
only — "are we roughly on the same side?" not "is our position size correct?"
"""

import io
import logging
from datetime import datetime, timedelta
from contextlib import redirect_stderr, redirect_stdout

import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import FUTURES_UNIVERSE

logger = logging.getLogger(__name__)

# Column mappings per report type.
# The cot_reports library returns DataFrames with these column patterns.
COT_COLUMNS = {
    "TFF": {
        "long": "Lev_Money_Positions_Long_All",
        "short": "Lev_Money_Positions_Short_All",
        "spreading": "Lev_Money_Positions_Spread_All",
    },
    "DISAGG": {
        "long": "M_Money_Positions_Long_All",
        "short": "M_Money_Positions_Short_All",
        "spreading": "M_Money_Positions_Spread_All",
    },
}


class COTData:
    """Fetch and parse CFTC COT data with correct report-type mapping."""

    def __init__(self, universe=None):
        self.universe = universe or FUTURES_UNIVERSE
        self._tff_data: pd.DataFrame | None = None
        self._disagg_data: pd.DataFrame | None = None

    def fetch(self, year=None) -> dict[str, pd.DataFrame]:
        """Fetch COT reports for the current (or specified) year.

        Returns dict with keys 'TFF' and 'DISAGG', each a DataFrame
        of the full report. Caches in memory after first fetch.
        """
        try:
            from cot_reports import cot_reports as cot
        except ImportError:
            logger.error("cot_reports not installed. Run: uv add cot-reports")
            return {}

        if year is None:
            year = datetime.now().year

        reports = {}

        if self._tff_data is None:
            try:
                self._tff_data = self._quiet_cot_year(
                    cot,
                    year=year,
                    cot_report_type="traders_in_financial_futures_futopt",
                )
                logger.info("Fetched TFF report: %d rows", len(self._tff_data))
            except Exception as e:
                logger.error("Failed to fetch TFF report: %s", e)
                self._tff_data = pd.DataFrame()
        reports["TFF"] = self._tff_data

        if self._disagg_data is None:
            try:
                self._disagg_data = self._quiet_cot_year(
                    cot,
                    year=year,
                    cot_report_type="disaggregated_futopt",
                )
                logger.info("Fetched Disaggregated report: %d rows", len(self._disagg_data))
            except Exception as e:
                logger.error("Failed to fetch Disaggregated report: %s", e)
                self._disagg_data = pd.DataFrame()
        reports["DISAGG"] = self._disagg_data

        return reports

    def positioning(self, symbol: str) -> pd.DataFrame | None:
        """Get net positioning time series for a symbol's relevant trader category.

        Returns DataFrame with columns: date, long, short, net, net_pct
        (net_pct = net / (long + short), a normalized measure of directional bias).
        """
        if symbol not in self.universe:
            logger.warning("Unknown symbol: %s", symbol)
            return None

        meta = self.universe[symbol]
        report_type = meta["cot_report"]
        cot_code = meta["cot_code"]
        cols = COT_COLUMNS[report_type]

        reports = self.fetch()
        df = reports.get(report_type)

        if df is None or df.empty:
            return None

        # Filter by contract code
        code_col = "CFTC_Contract_Market_Code"
        if code_col not in df.columns:
            # Try alternative column names
            for alt in ["Contract_Market_Code", "CFTC Contract Market Code"]:
                if alt in df.columns:
                    code_col = alt
                    break
            else:
                logger.error("Cannot find contract code column in %s report", report_type)
                return None

        mask = df[code_col].astype(str).str.strip() == str(cot_code).strip()
        filtered = df[mask].copy()

        if filtered.empty:
            logger.warning("No COT data for %s (code=%s, report=%s)", symbol, cot_code, report_type)
            return None

        # Extract positioning columns
        date_col = None
        for candidate in ["Report_Date_as_YYYY-MM-DD", "As_of_Date_In_Form_YYMMDD", "Report_Date"]:
            if candidate in filtered.columns:
                date_col = candidate
                break

        if date_col is None:
            logger.error("Cannot find date column in COT data")
            return None

        result = pd.DataFrame()
        result["date"] = pd.to_datetime(filtered[date_col])

        # Find matching columns (names may vary slightly)
        long_col = self._find_col(filtered.columns, cols["long"])
        short_col = self._find_col(filtered.columns, cols["short"])

        if long_col is None or short_col is None:
            logger.error("Cannot find long/short columns for %s in %s report", symbol, report_type)
            return None

        result["long"] = filtered[long_col].values.astype(float)
        result["short"] = filtered[short_col].values.astype(float)
        result["net"] = result["long"] - result["short"]

        total = result["long"] + result["short"]
        result["net_pct"] = (result["net"] / total.replace(0, float("nan"))).fillna(0)

        result = result.sort_values("date").reset_index(drop=True)
        return result

    def latest_positioning(self, symbol: str) -> dict | None:
        """Most recent COT positioning for a symbol.

        Returns dict with: date, long, short, net, net_pct, report_type, category.
        """
        pos = self.positioning(symbol)
        if pos is None or pos.empty:
            return None

        latest = pos.iloc[-1]
        meta = self.universe[symbol]
        return {
            "date": latest["date"],
            "long": int(latest["long"]),
            "short": int(latest["short"]),
            "net": int(latest["net"]),
            "net_pct": float(latest["net_pct"]),
            "report_type": meta["cot_report"],
            "category": "Leveraged Funds" if meta["cot_report"] == "TFF" else "Managed Money",
        }

    @staticmethod
    def _find_col(columns, pattern: str) -> str | None:
        """Find a column matching a pattern (case-insensitive, partial match)."""
        pattern_lower = pattern.lower()
        for col in columns:
            if pattern_lower in col.lower():
                return col
        return None

    @staticmethod
    def _quiet_cot_year(cot_module, year, cot_report_type):
        """Suppress cot_reports console chatter and return the requested report."""
        sink = io.StringIO()
        with redirect_stdout(sink), redirect_stderr(sink):
            return cot_module.cot_year(year=year, cot_report_type=cot_report_type)
