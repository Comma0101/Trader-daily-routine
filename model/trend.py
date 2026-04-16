"""
Trend signal generation — SG Trend Indicator baseline.

Baseline model: two-speed moving average crossover (20d short, 120d long).
Signal per horizon: +1 if price > MA, -1 if price < MA.
Composite: average of both horizons → values in {-1, 0, +1}.

This matches the SG Trend Indicator structure. The 5-horizon blend
(20/60/125/250/500) is a future enhancement, gated on out-of-sample evidence.
"""

import numpy as np
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TREND_PARAMS


class TrendModel:
    """Two-speed MA crossover trend model."""

    def __init__(self, short_window=None, long_window=None):
        self.short_window = short_window or TREND_PARAMS["short_window"]
        self.long_window = long_window or TREND_PARAMS["long_window"]

    def moving_averages(self, prices: pd.Series) -> pd.DataFrame:
        """Compute short and long moving averages.

        Returns DataFrame with columns: price, ma_short, ma_long.
        """
        return pd.DataFrame({
            "price": prices,
            "ma_short": prices.rolling(self.short_window, min_periods=self.short_window).mean(),
            "ma_long": prices.rolling(self.long_window, min_periods=self.long_window).mean(),
        })

    def signals(self, prices: pd.Series) -> pd.DataFrame:
        """Generate trend signals from price series.

        Returns DataFrame with columns:
          - signal_short: +1/-1 based on price vs short MA
          - signal_long:  +1/-1 based on price vs long MA
          - signal:       composite (-1, 0, or +1)
        """
        ma = self.moving_averages(prices)

        signal_short = np.sign(ma["price"] - ma["ma_short"])
        signal_long = np.sign(ma["price"] - ma["ma_long"])
        composite = (signal_short + signal_long) / 2.0

        return pd.DataFrame({
            "signal_short": signal_short,
            "signal_long": signal_long,
            "signal": composite,
        }, index=prices.index)

    def current_signal(self, prices: pd.Series) -> dict:
        """Get the most recent signal state for a single market.

        Returns dict with: signal, signal_short, signal_long, price,
        ma_short, ma_long, days_in_position, reversal_price_short, reversal_price_long.
        """
        ma = self.moving_averages(prices)
        sig = self.signals(prices)

        last = sig.dropna().iloc[-1]
        last_ma = ma.dropna().iloc[-1]

        # Count consecutive days the composite signal has held this value
        composite = sig["signal"].dropna()
        current_val = composite.iloc[-1]
        days = 1
        for v in composite.iloc[-2::-1]:
            if v == current_val:
                days += 1
            else:
                break

        return {
            "signal": float(last["signal"]),
            "signal_short": float(last["signal_short"]),
            "signal_long": float(last["signal_long"]),
            "price": float(last_ma["price"]),
            "ma_short": float(last_ma["ma_short"]),
            "ma_long": float(last_ma["ma_long"]),
            "days_in_position": days,
            # Price levels where signals would flip
            "reversal_price_short": float(last_ma["ma_short"]),
            "reversal_price_long": float(last_ma["ma_long"]),
        }

    def signal_label(self, signal_value: float) -> str:
        """Human-readable label for a signal value."""
        if signal_value > 0.5:
            return "LONG"
        elif signal_value < -0.5:
            return "SHORT"
        elif signal_value > 0:
            return "LEAN LONG"
        elif signal_value < 0:
            return "LEAN SHORT"
        else:
            return "FLAT"

    def detect_flips(self, prices: pd.Series, lookback_days: int = 5) -> list[dict]:
        """Detect recent signal flips (changes in composite signal).

        Returns list of dicts with: date, from_signal, to_signal, price.
        Looks back `lookback_days` trading days from the most recent date.
        """
        sig = self.signals(prices)["signal"].dropna()
        if len(sig) < 2:
            return []

        recent = sig.iloc[-lookback_days:]
        changes = recent[recent != recent.shift(1)].iloc[1:]  # skip first (no prior)

        flips = []
        for date, new_val in changes.items():
            idx = sig.index.get_loc(date)
            old_val = sig.iloc[idx - 1]
            flips.append({
                "date": date,
                "from_signal": float(old_val),
                "to_signal": float(new_val),
                "from_label": self.signal_label(float(old_val)),
                "to_label": self.signal_label(float(new_val)),
                "price": float(prices.loc[date]) if date in prices.index else None,
            })
        return flips
