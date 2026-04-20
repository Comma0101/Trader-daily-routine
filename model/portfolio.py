"""
Portfolio construction — equal-risk sector weighting and position sizing.

Implements:
  - Equal risk budget across sectors (each sector gets 1/N of risk)
  - Within each sector, equal risk per market
  - Vol-targeted position sizing per market
  - Continuous (daily) rebalance
  - Gross leverage cap

Mirrors SG Trend Indicator methodology: equal-risk sector weights,
vol targeting, continuous (daily) rebalance.
"""

import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import FUTURES_UNIVERSE, SECTORS, PORTFOLIO_PARAMS
from model.trend import TrendModel
from model.volatility import VolatilityEstimator


class PortfolioConstructor:
    """Build a risk-parity CTA portfolio from trend signals and vol estimates."""

    def __init__(self, universe=None, sectors=None, trend_model=None, volatility_estimator=None):
        self.universe = universe or FUTURES_UNIVERSE
        self.sectors = sectors or SECTORS
        self.trend = trend_model or TrendModel()
        self.vol = volatility_estimator or VolatilityEstimator()
        self.max_leverage = PORTFOLIO_PARAMS["max_leverage"]

    def sector_map(self) -> dict[str, list[str]]:
        """Map each sector to its constituent symbols."""
        mapping = {}
        for symbol, meta in self.universe.items():
            sector = meta["sector"]
            mapping.setdefault(sector, []).append(symbol)
        return mapping

    def compute_weights(
        self,
        signals: dict[str, float],
        vol_scalars: dict[str, float],
    ) -> dict[str, float]:
        """Compute portfolio weights for each market.

        Process:
        1. Assign each sector 1/N of total risk budget (N = number of active sectors).
        2. Within each sector, split equally among its markets.
        3. Multiply by the trend signal (-1, 0, +1) for direction.
        4. Multiply by the vol scalar for position sizing.
        5. Rescale if gross leverage exceeds the cap.

        Args:
            signals: {symbol: composite_signal} from TrendModel
            vol_scalars: {symbol: vol_target_scalar} from VolatilityEstimator

        Returns:
            {symbol: weight} where weight is signed (positive=long, negative=short).
        """
        sec_map = self.sector_map()

        # Only count sectors that have at least one market with data
        active_sectors = [s for s in self.sectors if any(
            sym in signals and sym in vol_scalars for sym in sec_map.get(s, [])
        )]
        if not active_sectors:
            return {}

        n_sectors = len(active_sectors)
        sector_budget = 1.0 / n_sectors

        weights = {}
        for sector in active_sectors:
            symbols = [s for s in sec_map.get(sector, [])
                       if s in signals and s in vol_scalars]
            if not symbols:
                continue
            per_market = sector_budget / len(symbols)

            for sym in symbols:
                raw_weight = per_market * signals[sym] * vol_scalars[sym]
                weights[sym] = raw_weight

        # Enforce gross leverage cap
        gross = sum(abs(w) for w in weights.values())
        if gross > self.max_leverage and gross > 0:
            scale = self.max_leverage / gross
            weights = {s: w * scale for s, w in weights.items()}

        return weights

    def build(
        self,
        prices: dict[str, pd.Series],
        returns: dict[str, pd.Series],
    ) -> dict:
        """Full portfolio construction from raw data.

        Args:
            prices: {symbol: adjusted_close_series}
            returns: {symbol: daily_return_series}

        Returns dict with:
            weights:        {symbol: signed_weight}
            signals:        {symbol: composite_signal}
            vol_scalars:    {symbol: vol_scalar}
            signal_details: {symbol: full_signal_dict from TrendModel}
            sector_exposure:{sector: net_weight}
            gross_leverage: float
            net_exposure:   float
        """
        signals = {}
        vol_scalars = {}
        signal_details = {}

        for sym in prices:
            if sym not in returns or len(returns[sym]) < self.trend.long_window:
                continue
            try:
                detail = self.trend.current_signal(prices[sym])
                signals[sym] = detail["signal"]
                signal_details[sym] = detail
                vol_scalars[sym] = self.vol.current_scalar(returns[sym])
            except Exception:
                continue

        weights = self.compute_weights(signals, vol_scalars)

        # Sector exposure summary
        sec_map = self.sector_map()
        sector_exposure = {}
        for sector in self.sectors:
            sector_exposure[sector] = sum(
                weights.get(s, 0.0) for s in sec_map.get(sector, [])
            )

        gross = sum(abs(w) for w in weights.values())
        net = sum(weights.values())

        return {
            "weights": weights,
            "signals": signals,
            "vol_scalars": vol_scalars,
            "signal_details": signal_details,
            "sector_exposure": sector_exposure,
            "gross_leverage": gross,
            "net_exposure": net,
        }

    def historical_components(
        self,
        prices: dict[str, pd.Series],
        returns: dict[str, pd.Series],
    ) -> dict:
        """Build daily weight history with per-component breakdowns.

        Returns dict with:
            weights:      DataFrame (dates × markets) — final portfolio weights
            signals:      DataFrame (dates × markets) — raw composite signal
            vol_scalars:  DataFrame (dates × markets) — vol-target scalar
            alloc_budgets: DataFrame (dates × markets) — allocation budget per market
            cap_factors:  Series (dates) — leverage-cap scaling factor (1.0 = not binding)
        """
        empty = {
            "weights": pd.DataFrame(),
            "signals": pd.DataFrame(),
            "vol_scalars": pd.DataFrame(),
            "alloc_budgets": pd.DataFrame(),
            "cap_factors": pd.Series(dtype=float),
        }

        histories = {}
        for sym, price_series in prices.items():
            if sym not in returns or returns[sym].empty:
                continue

            signal_series = self.trend.signals(price_series)["signal"].dropna()
            vol_series = self.vol.vol_scalar(returns[sym]).dropna()
            history = pd.concat(
                [signal_series.rename("signal"), vol_series.rename("vol_scalar")],
                axis=1,
                join="inner",
            ).dropna()

            if not history.empty:
                histories[sym] = history

        if not histories:
            return empty

        all_dates = sorted({date for history in histories.values() for date in history.index})
        columns = sorted(histories)
        idx = pd.DatetimeIndex(all_dates)

        weight_frame = pd.DataFrame(0.0, index=idx, columns=columns)
        signal_frame = pd.DataFrame(0.0, index=idx, columns=columns)
        vol_scalar_frame = pd.DataFrame(0.0, index=idx, columns=columns)
        alloc_budget_frame = pd.DataFrame(0.0, index=idx, columns=columns)
        cap_factors = pd.Series(1.0, index=idx)

        sector_map = self.sector_map()

        for date in idx:
            active_sectors = []
            sector_symbols = {}
            for sector in self.sectors:
                symbols = [
                    sym for sym in sector_map.get(sector, [])
                    if sym in histories and date in histories[sym].index
                ]
                if symbols:
                    active_sectors.append(sector)
                    sector_symbols[sector] = symbols

            if not active_sectors:
                continue

            sector_budget = 1.0 / len(active_sectors)
            for sector in active_sectors:
                per_market = sector_budget / len(sector_symbols[sector])
                for sym in sector_symbols[sector]:
                    point = histories[sym].loc[date]
                    sig = float(point["signal"])
                    vol_s = float(point["vol_scalar"])

                    signal_frame.at[date, sym] = sig
                    vol_scalar_frame.at[date, sym] = vol_s
                    alloc_budget_frame.at[date, sym] = per_market
                    weight_frame.at[date, sym] = per_market * sig * vol_s

            gross = weight_frame.loc[date].abs().sum()
            if gross > self.max_leverage and gross > 0:
                cap = self.max_leverage / gross
                weight_frame.loc[date] *= cap
                cap_factors.at[date] = cap

        return {
            "weights": weight_frame,
            "signals": signal_frame,
            "vol_scalars": vol_scalar_frame,
            "alloc_budgets": alloc_budget_frame,
            "cap_factors": cap_factors,
        }

    def historical_weights(
        self,
        prices: dict[str, pd.Series],
        returns: dict[str, pd.Series],
    ) -> pd.DataFrame:
        """Build a daily weight history from signal and vol histories."""
        return self.historical_components(prices, returns)["weights"]

    def backtest_returns(
        self,
        prices: dict[str, pd.Series],
        returns: dict[str, pd.Series],
    ) -> pd.Series:
        """Create a historical model return series using lagged daily weights."""
        weights = self.historical_weights(prices, returns)
        if weights.empty:
            return pd.Series(dtype=float)

        returns_frame = pd.DataFrame(
            {sym: series for sym, series in returns.items() if sym in weights.columns}
        ).sort_index()
        if returns_frame.empty:
            return pd.Series(dtype=float)

        weights = weights.reindex(returns_frame.index).fillna(0.0)
        lagged_weights = weights.shift(1).fillna(0.0)
        model_returns = (lagged_weights * returns_frame).sum(axis=1)
        model_returns.name = "model"
        return model_returns
