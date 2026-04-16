"""
Volatility estimation and vol-targeting.

Implements exponentially weighted moving average (EWMA) volatility,
matching the SG Trend Indicator methodology (3-month EWMA, 15% vol target).
"""

import numpy as np
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import VOL_PARAMS


class VolatilityEstimator:
    """EWMA volatility estimation with vol-target scaling."""

    def __init__(self, ewma_span=None, target_vol=None, trading_days=None):
        self.ewma_span = ewma_span or VOL_PARAMS["ewma_span"]
        self.target_vol = target_vol or VOL_PARAMS["target_vol"]
        self.trading_days = trading_days or VOL_PARAMS["trading_days_per_year"]

    def estimate(self, returns: pd.Series) -> pd.Series:
        """Compute annualized EWMA volatility from daily returns.

        Returns a Series of annualized vol estimates aligned to the input index.
        """
        daily_vol = returns.ewm(span=self.ewma_span, min_periods=max(10, self.ewma_span // 3)).std()
        annual_vol = daily_vol * np.sqrt(self.trading_days)
        return annual_vol

    def vol_scalar(self, returns: pd.Series) -> pd.Series:
        """Position size scalar to achieve the target volatility.

        scalar = target_vol / realized_vol

        When realized vol is low, scalar > 1 (lever up).
        When realized vol is high, scalar < 1 (reduce exposure).
        The scalar is floored at 0 and capped at 5x to prevent extreme leverage
        from low-vol artifacts.
        """
        vol = self.estimate(returns)
        scalar = self.target_vol / vol
        scalar = scalar.clip(lower=0.0, upper=5.0)
        return scalar

    def current_vol(self, returns: pd.Series) -> float:
        """Most recent annualized volatility estimate."""
        vol = self.estimate(returns)
        return vol.dropna().iloc[-1]

    def current_scalar(self, returns: pd.Series) -> float:
        """Most recent vol-target scalar."""
        s = self.vol_scalar(returns)
        return s.dropna().iloc[-1]
