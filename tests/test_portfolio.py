import unittest

import pandas as pd

from model.portfolio import PortfolioConstructor


class _FakeTrendModel:
    long_window = 1

    def current_signal(self, prices: pd.Series) -> dict:
        return {
            "signal": 1.0,
            "signal_short": 1.0,
            "signal_long": 1.0,
            "price": float(prices.iloc[-1]),
            "ma_short": float(prices.iloc[-1]),
            "ma_long": float(prices.iloc[-1]),
            "days_in_position": 1,
            "reversal_price_short": float(prices.iloc[-1]),
            "reversal_price_long": float(prices.iloc[-1]),
        }

    def signals(self, prices: pd.Series) -> pd.DataFrame:
        return pd.DataFrame(
            {"signal": [0.0, 1.0, 1.0, 1.0]},
            index=prices.index,
        )


class _FakeVolatilityEstimator:
    def current_scalar(self, returns: pd.Series) -> float:
        return 1.0

    def vol_scalar(self, returns: pd.Series) -> pd.Series:
        return pd.Series(1.0, index=returns.index)


class PortfolioConstructorHistoryTests(unittest.TestCase):
    def test_backtest_returns_apply_lagged_weights(self):
        dates = pd.date_range("2026-01-01", periods=4, freq="D")
        prices = {"ES": pd.Series([100.0, 101.0, 102.0, 103.0], index=dates)}
        returns = {"ES": prices["ES"].pct_change().dropna()}
        universe = {"ES": {"sector": "Equity Index"}}

        constructor = PortfolioConstructor(
            universe=universe,
            sectors=["Equity Index"],
            trend_model=_FakeTrendModel(),
            volatility_estimator=_FakeVolatilityEstimator(),
        )

        model_returns = constructor.backtest_returns(prices, returns)

        self.assertEqual(list(model_returns.index), list(returns["ES"].index))
        self.assertEqual(model_returns.iloc[0], 0.0)
        self.assertAlmostEqual(model_returns.iloc[1], returns["ES"].iloc[1])
        self.assertAlmostEqual(model_returns.iloc[2], returns["ES"].iloc[2])
