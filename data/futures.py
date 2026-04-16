"""
Continuous futures data layer.

Fetches daily price data from yfinance and constructs synthetic back-adjusted
series suitable for moving-average signal generation.

KNOWN LIMITATIONS (yfinance continuous contracts):
  - Uses front-month continuous contracts (=F suffix). The exact roll date
    and adjustment method are opaque — yfinance does not document this.
  - Roll gaps can distort moving averages computed on raw price levels.
    We mitigate this by building a synthetic adjusted series from cumulative
    returns (see _back_adjust). This is standard practice but assumes the
    roll gap is entirely artificial, which is approximately but not exactly true.
  - History depth varies by contract. Some tickers return < 2 years.
  - Intraday gaps, missing days, and timezone inconsistencies may occur.
  - FX spot tickers (=X suffix) are not futures and have no roll issue,
    but also don't represent actual futures positioning.

FOR PRODUCTION: Replace with a proper futures data provider (Norgate, CSI,
Nasdaq Data Link, or Interactive Brokers) that provides explicit roll dates,
back-adjusted and ratio-adjusted series, and consistent history depth.
"""

import os
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import FUTURES_UNIVERSE, DATA_PARAMS

logger = logging.getLogger(__name__)


class FuturesData:
    """Fetch and manage continuous futures price data."""

    def __init__(self, universe=None, cache_dir=None, refresh=False):
        self.universe = universe or FUTURES_UNIVERSE
        self.cache_dir = Path(cache_dir or DATA_PARAMS["cache_dir"])
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.refresh = refresh

        # symbol -> DataFrame with columns: Open, High, Low, Close, Volume
        self._raw: dict[str, pd.DataFrame] = {}
        # symbol -> Series of adjusted close prices (back-adjusted from returns)
        self._adjusted: dict[str, pd.Series] = {}
        # symbol -> Series with a live intraday point overlaid on the adjusted daily series
        self._adjusted_live: dict[str, pd.Series] = {}
        # symbol -> latest intraday quote metadata
        self._live_quotes: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_all(self, period_years=None, refresh=None):
        """Fetch data for every market in the universe.

        Returns dict of {symbol: DataFrame} for successfully fetched markets.
        Failures are logged and skipped.
        """
        period_years = period_years or DATA_PARAMS["price_history_years"]
        period_str = f"{period_years}y"
        refresh = self.refresh if refresh is None else refresh

        results = {}
        for symbol, meta in self.universe.items():
            df = self._fetch_one(symbol, meta["ticker"], period_str, refresh=refresh)
            if df is not None and len(df) > 0:
                results[symbol] = df
            else:
                logger.warning("No data for %s (%s)", symbol, meta["ticker"])
        return results

    def fetch(self, symbol, period_years=None, refresh=None):
        """Fetch data for a single symbol."""
        if symbol not in self.universe:
            raise KeyError(f"Unknown symbol: {symbol}")
        period_years = period_years or DATA_PARAMS["price_history_years"]
        meta = self.universe[symbol]
        refresh = self.refresh if refresh is None else refresh
        return self._fetch_one(symbol, meta["ticker"], f"{period_years}y", refresh=refresh)

    def prices(self, symbol, live=False) -> pd.Series:
        """Return back-adjusted close prices for a symbol.

        The adjusted series is constructed by:
        1. Computing daily log returns from raw close prices.
        2. Cumulating returns backward from the most recent price.

        This eliminates roll gaps for signal computation while preserving
        the current price level at the end of the series.
        """
        if live and symbol in self._adjusted_live:
            return self._adjusted_live[symbol]
        if not live and symbol in self._adjusted:
            return self._adjusted[symbol]

        if symbol not in self._raw:
            self.fetch(symbol)

        raw = self._raw.get(symbol)
        if raw is None or raw.empty:
            raise ValueError(f"No data available for {symbol}")

        if symbol not in self._adjusted:
            self._adjusted[symbol] = self._back_adjust(raw["Close"])

        if not live:
            return self._adjusted[symbol]

        ticker = self.universe[symbol]["ticker"]
        live_quote = self._fetch_live_quote(symbol, ticker)
        if live_quote is None:
            return self._adjusted[symbol]

        self._live_quotes[symbol] = live_quote
        self._adjusted_live[symbol] = self._append_live_quote(
            self._adjusted[symbol],
            raw["Close"],
            live_quote,
        )
        return self._adjusted_live[symbol]

    def returns(self, symbol) -> pd.Series:
        """Daily simple returns (not log) for a symbol."""
        p = self.prices(symbol)
        return p.pct_change().dropna()

    def all_prices(self) -> pd.DataFrame:
        """DataFrame of adjusted close prices for all fetched symbols."""
        if not self._raw:
            self.fetch_all()
        series = {}
        for symbol in self._raw:
            try:
                series[symbol] = self.prices(symbol)
            except ValueError:
                continue
        return pd.DataFrame(series)

    def all_returns(self) -> pd.DataFrame:
        """DataFrame of daily returns for all fetched symbols."""
        return self.all_prices().pct_change().dropna(how="all")

    def data_context(self) -> dict:
        """Return reporting context for the current data snapshot."""
        official_dates = [
            pd.Timestamp(df.index.max()).tz_localize(None)
            for df in self._raw.values()
            if df is not None and not df.empty
        ]
        official_close = max(official_dates) if official_dates else None

        live_timestamps = [
            self._normalize_timestamp(quote["timestamp"])
            for quote in self._live_quotes.values()
            if quote and quote.get("timestamp") is not None
        ]
        live_as_of = max(live_timestamps) if live_timestamps else None

        is_live = (
            live_as_of is not None
            and official_close is not None
            and live_as_of.date() > official_close.date()
        )

        return {
            "mode": "live" if is_live else "daily",
            "official_close_date": official_close.strftime("%Y-%m-%d") if official_close is not None else None,
            "as_of": (
                live_as_of.strftime("%Y-%m-%d %H:%M")
                if is_live and live_as_of is not None
                else official_close.strftime("%Y-%m-%d")
                if official_close is not None
                else None
            ),
            "live_as_of": live_as_of.strftime("%Y-%m-%d %H:%M") if live_as_of is not None else None,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch_one(self, symbol, ticker, period, refresh=False) -> pd.DataFrame | None:
        """Fetch a single ticker, using CSV cache if available."""
        cache_path = self.cache_dir / f"{symbol}.csv"

        # Use cache if fresh (same day)
        if not refresh and cache_path.exists():
            mtime = pd.Timestamp.fromtimestamp(cache_path.stat().st_mtime)
            if mtime.date() == pd.Timestamp.now().date():
                df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                self._raw[symbol] = df
                return df

        try:
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=DATA_PARAMS["yfinance_interval"])
        except Exception as e:
            logger.error("Failed to fetch %s (%s): %s", symbol, ticker, e)
            return None

        if df is None or df.empty:
            return None

        # Normalize columns — yfinance sometimes returns MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Keep only OHLCV
        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[keep].copy()
        df.index = pd.DatetimeIndex(df.index).tz_localize(None)
        df = df.dropna(subset=["Close"])

        # Cache to disk
        df.to_csv(cache_path)
        self._raw[symbol] = df
        self._adjusted.pop(symbol, None)
        self._adjusted_live.pop(symbol, None)
        self._live_quotes.pop(symbol, None)
        return df

    def _fetch_live_quote(self, symbol, ticker) -> dict | None:
        """Fetch the most recent intraday quote for a ticker."""
        try:
            t = yf.Ticker(ticker)
            df = t.history(
                period=DATA_PARAMS["yfinance_live_period"],
                interval=DATA_PARAMS["yfinance_live_interval"],
            )
        except Exception as e:
            logger.warning("Failed to fetch live quote for %s (%s): %s", symbol, ticker, e)
            return None

        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if "Close" not in df.columns:
            return None

        df = df[["Close"]].copy()
        df.index = pd.DatetimeIndex(df.index).tz_localize(None)
        df = df.dropna(subset=["Close"])
        if df.empty:
            return None

        return {
            "timestamp": self._normalize_timestamp(df.index[-1]),
            "price": float(df["Close"].iloc[-1]),
        }

    @staticmethod
    def _append_live_quote(adjusted: pd.Series, raw_close: pd.Series, live_quote: dict) -> pd.Series:
        """Append a synthetic live adjusted point using the intraday/raw return."""
        if adjusted.empty or raw_close.empty or not live_quote:
            return adjusted

        live_timestamp = FuturesData._normalize_timestamp(live_quote.get("timestamp"))
        live_price = float(live_quote.get("price", 0.0) or 0.0)
        prior_raw_close = float(raw_close.iloc[-1] or 0.0)
        prior_adjusted = float(adjusted.iloc[-1] or 0.0)

        if live_timestamp is None or live_price <= 0 or prior_raw_close <= 0 or prior_adjusted <= 0:
            return adjusted

        live_adjusted = prior_adjusted * (live_price / prior_raw_close)
        result = adjusted.copy()
        result.loc[live_timestamp] = live_adjusted
        return result.sort_index()

    @staticmethod
    def _normalize_timestamp(value):
        if value is None:
            return None
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            return timestamp.tz_convert(None)
        return timestamp

    @staticmethod
    def _back_adjust(close: pd.Series) -> pd.Series:
        """Build a synthetic back-adjusted price series.

        Approach:
        - Compute daily log returns.
        - Detect likely roll gaps: days where |return| > 5 * rolling median
          absolute return AND the gap reverses within 2 days. Replace these
          with 0 (i.e., assume the gap is an artifact, not a real move).
        - Cumulate adjusted returns backward from the last observed price.

        This is a heuristic. It works reasonably well for liquid futures but
        can misfire on genuinely volatile contracts (e.g., natural gas).
        """
        if close.empty:
            return close.copy()

        log_ret = np.log(close / close.shift(1))

        # Simple roll-gap filter: flag returns > 5x median absolute return
        median_abs = log_ret.abs().rolling(60, min_periods=10).median()
        threshold = 5 * median_abs.clip(lower=0.001)
        is_spike = log_ret.abs() > threshold

        # Only zero out spikes that partially reverse next day (roll signature)
        next_ret = log_ret.shift(-1)
        reverses = (log_ret * next_ret) < 0  # opposite signs
        is_roll_gap = is_spike & reverses

        adjusted_ret = log_ret.copy()
        adjusted_ret[is_roll_gap] = 0.0

        # Cumulate backward from last price
        cum_ret = adjusted_ret.iloc[::-1].cumsum().iloc[::-1]
        last_price = close.iloc[-1]
        adjusted = last_price * np.exp(-cum_ret + cum_ret.iloc[-1])

        adjusted.name = close.name
        return adjusted
