"""
Benchmark data: managed futures ETFs and SG Trend Indicator.

Three benchmark layers, each useful for different validation:

1. ETF returns (DBMF, KMLM, CTA) — portfolio-level return shape.
   Good for: "does our aggregate return look plausible?"
   Bad for: "is the model long copper today?"

2. SG Trend Indicator — daily signal comparison per market.
   Published daily by SG Prime Services. We provide a scraper stub;
   the actual data requires access to their web tool.

3. NilssonHedge CTA Index — monthly performance benchmark.
   Freely downloadable after registration. Indicates CTA industry
   returns, not positions.
"""

import logging

import pandas as pd
import yfinance as yf

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BENCHMARK_ETFS, DATA_PARAMS

logger = logging.getLogger(__name__)


class BenchmarkData:
    """Fetch and manage benchmark comparison data."""

    def __init__(self):
        self._etf_cache: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # 1. Managed Futures ETFs
    # ------------------------------------------------------------------

    def fetch_etf(self, ticker: str, period_years: int = None) -> pd.DataFrame | None:
        """Fetch daily OHLCV for a benchmark ETF."""
        if ticker in self._etf_cache:
            return self._etf_cache[ticker]

        period_years = period_years or DATA_PARAMS["price_history_years"]
        try:
            t = yf.Ticker(ticker)
            df = t.history(period=f"{period_years}y", interval="1d")
        except Exception as e:
            logger.error("Failed to fetch ETF %s: %s", ticker, e)
            return None

        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.index = pd.DatetimeIndex(df.index).tz_localize(None)
        self._etf_cache[ticker] = df
        return df

    def fetch_all_etfs(self) -> dict[str, pd.DataFrame]:
        """Fetch all benchmark ETFs."""
        results = {}
        for ticker in BENCHMARK_ETFS:
            df = self.fetch_etf(ticker)
            if df is not None:
                results[ticker] = df
        return results

    def etf_returns(self) -> pd.DataFrame:
        """Daily returns for all benchmark ETFs as a single DataFrame."""
        self.fetch_all_etfs()
        series = {}
        for ticker, df in self._etf_cache.items():
            if "Close" in df.columns:
                series[ticker] = df["Close"].pct_change()
        return pd.DataFrame(series).dropna(how="all")

    def etf_cumulative_returns(self) -> pd.DataFrame:
        """Cumulative returns for benchmark ETFs (starting at 1.0)."""
        ret = self.etf_returns()
        return (1 + ret).cumprod()

    # ------------------------------------------------------------------
    # 2. SG Trend Indicator — daily signal data
    # ------------------------------------------------------------------

    def fetch_sg_trend_indicator(self) -> pd.DataFrame | None:
        """Fetch SG Trend Indicator daily signals.

        The SG Trend Indicator is published at:
        https://wholesale.banking.societegenerale.com/fileadmin/indices_feeds/ti_screen/index.html

        This is a STUB — the actual page renders dynamically and requires
        either:
          a) Browser automation (Selenium/Playwright) to scrape, or
          b) Access to SG Markets API (institutional clients), or
          c) Manual CSV download from the web tool.

        To integrate real data, implement one of these approaches and
        return a DataFrame with columns:
          market, signal (+1/-1), ma_short, ma_long, days_held, reversal_price

        For now, returns None and logs a notice.
        """
        logger.info(
            "SG Trend Indicator scraper is a stub. "
            "See: https://wholesale.banking.societegenerale.com/fileadmin/indices_feeds/ti_screen/index.html "
            "Manual download or browser automation needed."
        )
        return None

    # ------------------------------------------------------------------
    # 3. NilssonHedge CTA Index
    # ------------------------------------------------------------------

    def load_nilssonhedge(self, csv_path: str) -> pd.DataFrame | None:
        """Load NilssonHedge CTA index returns from a downloaded CSV.

        NilssonHedge provides free index data after registration at:
        https://nilssonhedge.com/index/cta-index/

        Their daily CTA index is at:
        https://nilssonhedge.com/index/daily-indices/daily-cta-index/

        This is a performance indicator, NOT a position feed.
        Use for: "do aggregate CTA returns match our model's return profile?"

        Args:
            csv_path: path to downloaded CSV with columns: Date, Return (or similar)

        Returns:
            DataFrame with date index and 'return' column, or None if file not found.
        """
        try:
            df = pd.read_csv(csv_path, parse_dates=True)
        except FileNotFoundError:
            logger.warning("NilssonHedge CSV not found at %s", csv_path)
            return None
        except Exception as e:
            logger.error("Error reading NilssonHedge CSV: %s", e)
            return None

        # Normalize column names
        df.columns = [c.strip().lower() for c in df.columns]

        date_col = None
        for candidate in ["date", "period", "month"]:
            if candidate in df.columns:
                date_col = candidate
                break

        ret_col = None
        for candidate in ["return", "returns", "monthly_return", "performance"]:
            if candidate in df.columns:
                ret_col = candidate
                break

        if date_col is None or ret_col is None:
            logger.error("Cannot identify date/return columns in NilssonHedge CSV. Found: %s", list(df.columns))
            return None

        result = pd.DataFrame({
            "date": pd.to_datetime(df[date_col]),
            "return": pd.to_numeric(df[ret_col], errors="coerce"),
        }).dropna().set_index("date").sort_index()

        return result
