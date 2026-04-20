"""Tactical CTA-style equity flow model for ES/NQ.

This sleeve is intentionally separate from the broad SG-style proxy. It uses a
multi-horizon trend stack, market-specific capital allocation, and tape
scenarios to approximate the kind of dealer-desk CTA trigger notes commonly
published on major equity indices.
"""

from __future__ import annotations

import math

import pandas as pd

from config import TACTICAL_EQUITY_PARAMS, FUTURES_UNIVERSE
from model.volatility import VolatilityEstimator


class TacticalEquityFlowModel:
    """Multi-horizon tactical equity sleeve for ES/NQ scenario analysis."""

    def __init__(self, params=None, volatility_estimator=None, universe=None):
        self.params = dict(TACTICAL_EQUITY_PARAMS)
        if params:
            self.params.update(params)
        self.vol = volatility_estimator or VolatilityEstimator()
        self.universe = universe or FUTURES_UNIVERSE

        self.markets = tuple(self.params["markets"])
        self.horizons = tuple(int(x) for x in self.params["horizons"])
        self.horizon_weights = {
            int(k): float(v) for k, v in dict(self.params["horizon_weights"]).items()
        }
        self.market_allocations = {
            str(k): float(v) for k, v in dict(self.params["market_allocations"]).items()
        }
        self.max_gross_leverage = float(self.params["max_gross_leverage"])
        self.scenario_moves = tuple(float(x) for x in self.params["scenario_moves"])
        self.signal_mode = str(self.params.get("signal_mode", "binary"))
        self.signal_spans = {
            int(k): float(v) for k, v in dict(self.params.get("signal_spans", {})).items()
        }

    def build(self, prices: dict[str, pd.Series], returns: dict[str, pd.Series], assumed_cta_aum_usd=None) -> dict:
        active_markets = [
            sym for sym in self.markets
            if sym in prices and sym in returns and len(prices[sym]) >= max(self.horizons)
        ]
        if not active_markets:
            return {"available": False, "markets": {}, "scenarios": []}

        market_allocs = _normalize_market_allocations(active_markets, self.market_allocations)

        current_states = {}
        for sym in active_markets:
            current_states[sym] = self._market_state(
                prices[sym],
                returns[sym],
                market_budget=market_allocs[sym],
            )

        current_states = _apply_gross_cap(current_states, self.max_gross_leverage)
        scenarios = []
        for move in self.scenario_moves:
            scenario_states = {}
            for sym in active_markets:
                shifted = _scenario_series(prices[sym], move)
                scenario_states[sym] = self._market_state(
                    shifted,
                    returns[sym],
                    market_budget=market_allocs[sym],
                )
            scenario_states = _apply_gross_cap(scenario_states, self.max_gross_leverage)
            scenarios.append(
                _scenario_snapshot(
                    move,
                    current_states=current_states,
                    scenario_states=scenario_states,
                    assumed_cta_aum_usd=assumed_cta_aum_usd,
                    universe=self.universe,
                )
            )

        return {
            "available": True,
            "model_label": "Tactical multi-horizon equity CTA sleeve",
            "method_note": (
                "Multi-horizon ES/NQ sleeve with market-specific allocations and flat/up/down tape scenarios. "
                "This is a modeled target-position engine, not observed flow."
            ),
            "assumed_cta_aum_usd": float(assumed_cta_aum_usd) if assumed_cta_aum_usd is not None else None,
            "markets": _market_snapshots(current_states, self.universe),
            "scenarios": scenarios,
            "scenario_reference": _scenario_reference(scenarios),
            "horizons": list(self.horizons),
            "market_allocations": market_allocs,
            "signal_mode": self.signal_mode,
            "signal_spans": {f"{h}d": float(v) for h, v in self.signal_spans.items()},
            "gross_leverage": sum(abs(state["target_weight"]) for state in current_states.values()),
        }

    def _market_state(self, prices: pd.Series, returns: pd.Series, market_budget: float) -> dict:
        price = float(prices.iloc[-1])
        horizon_signals = {}
        moving_averages = {}
        composite = 0.0

        for horizon in self.horizons:
            ma = prices.rolling(horizon, min_periods=horizon).mean().iloc[-1]
            moving_averages[horizon] = float(ma)
            signal = _trend_signal(
                price=price,
                moving_average=ma,
                horizon=horizon,
                mode=self.signal_mode,
                spans=self.signal_spans,
            )
            horizon_signals[horizon] = float(signal)
            composite += float(signal) * self.horizon_weights.get(horizon, 0.0)

        vol_scalar = float(self.vol.current_scalar(returns))
        target_weight = market_budget * composite * vol_scalar
        nearest_horizon, nearest_distance = _nearest_horizon_distance(price, moving_averages)

        return {
            "price": price,
            "horizon_signals": horizon_signals,
            "moving_averages": moving_averages,
            "composite_signal": composite,
            "signal_label": _signal_label(composite),
            "vol_scalar": vol_scalar,
            "market_budget": float(market_budget),
            "raw_target_weight": target_weight,
            "target_weight": target_weight,
            "cap_factor": 1.0,
            "nearest_horizon": nearest_horizon,
            "nearest_distance_pct": nearest_distance,
        }


def _scenario_snapshot(move, current_states, scenario_states, assumed_cta_aum_usd, universe):
    markets = {}
    total_delta_weight = 0.0
    total_delta_usd = 0.0 if assumed_cta_aum_usd is not None else None

    for sym, current in current_states.items():
        scenario = scenario_states[sym]
        delta_weight = float(scenario["target_weight"]) - float(current["target_weight"])
        flow_type = _classify_transition(
            float(current["composite_signal"]),
            float(scenario["composite_signal"]),
        )
        notional = delta_weight * float(assumed_cta_aum_usd) if assumed_cta_aum_usd is not None else None
        total_delta_weight += delta_weight
        if total_delta_usd is not None:
            total_delta_usd += notional

        markets[sym] = {
            "symbol": sym,
            "market": universe.get(sym, {}).get("name", sym),
            "current_signal": float(current["composite_signal"]),
            "scenario_signal": float(scenario["composite_signal"]),
            "current_weight": float(current["target_weight"]),
            "scenario_weight": float(scenario["target_weight"]),
            "delta_weight": delta_weight,
            "estimated_notional_change_usd": notional,
            "flow_type": flow_type,
            "price_now": float(current["price"]),
            "price_scenario": float(scenario["price"]),
        }

    return {
        "move_pct": float(move),
        "label": _scenario_label(move),
        "markets": markets,
        "total_delta_weight": total_delta_weight,
        "total_estimated_notional_change_usd": total_delta_usd,
    }


def _market_snapshots(states, universe):
    snapshots = {}
    for sym, state in states.items():
        snapshots[sym] = {
            "symbol": sym,
            "market": universe.get(sym, {}).get("name", sym),
            "price": float(state["price"]),
            "signal": float(state["composite_signal"]),
            "signal_label": state["signal_label"],
            "vol_scalar": float(state["vol_scalar"]),
            "market_budget": float(state["market_budget"]),
            "target_weight": float(state["target_weight"]),
            "cap_factor": float(state["cap_factor"]),
            "nearest_horizon": state["nearest_horizon"],
            "nearest_distance_pct": state["nearest_distance_pct"],
            "horizon_signals": {
                f"{h}d": float(v) for h, v in state["horizon_signals"].items()
            },
            "moving_averages": {
                f"{h}d": float(v) for h, v in state["moving_averages"].items()
            },
        }
    return snapshots


def _scenario_reference(scenarios):
    by_move = {round(float(item["move_pct"]), 6): item for item in scenarios}
    reference = {}
    for move, label in ((0.0, "flat"), (0.02, "up_2pct"), (0.05, "up_5pct"), (-0.02, "down_2pct"), (-0.05, "down_5pct")):
        item = by_move.get(round(move, 6))
        if item is not None:
            reference[label] = item
    return reference


def _normalize_market_allocations(active_markets, market_allocations):
    allocs = {sym: float(market_allocations.get(sym, 0.0)) for sym in active_markets}
    total = sum(allocs.values())
    if total <= 0:
        equal = 1.0 / len(active_markets)
        return {sym: equal for sym in active_markets}
    return {sym: value / total for sym, value in allocs.items()}


def _apply_gross_cap(states, max_gross_leverage):
    gross = sum(abs(state["target_weight"]) for state in states.values())
    if gross <= 0 or gross <= max_gross_leverage:
        return states

    scale = max_gross_leverage / gross
    for state in states.values():
        state["target_weight"] *= scale
        state["cap_factor"] = scale
    return states


def _scenario_series(prices: pd.Series, move_pct: float) -> pd.Series:
    shifted = prices.copy()
    shifted.iloc[-1] = float(prices.iloc[-1]) * (1.0 + float(move_pct))
    return shifted


def _nearest_horizon_distance(price, moving_averages):
    nearest_horizon = None
    nearest_distance = None
    for horizon, ma in moving_averages.items():
        if ma in (None, 0):
            continue
        distance = abs((float(price) - float(ma)) / float(price) * 100.0)
        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest_horizon = f"{int(horizon)}d"
    return nearest_horizon, nearest_distance


def _classify_transition(current_signal, scenario_signal):
    current_bucket = _signal_bucket(current_signal)
    scenario_bucket = _signal_bucket(scenario_signal)
    if current_bucket == scenario_bucket:
        if math.isclose(float(current_signal), float(scenario_signal), rel_tol=1e-9, abs_tol=1e-12):
            return "hold"
        return "conviction_change"
    if current_bucket == "short" and scenario_bucket == "long":
        return "short_cover_to_long"
    if current_bucket == "long" and scenario_bucket == "short":
        return "long_exit_to_short"
    if current_bucket == "flat" and scenario_bucket != "flat":
        return "new_entry"
    if current_bucket != "flat" and scenario_bucket == "flat":
        return "exit"
    return "regime_change"


def _signal_bucket(signal):
    value = float(signal or 0.0)
    if value > 0.1:
        return "long"
    if value < -0.1:
        return "short"
    return "flat"


def _signal_label(signal):
    value = float(signal or 0.0)
    if value >= 0.6:
        return "LONG"
    if value > 0.1:
        return "LEAN LONG"
    if value <= -0.6:
        return "SHORT"
    if value < -0.1:
        return "LEAN SHORT"
    return "FLAT"


def _scenario_label(move):
    if math.isclose(move, 0.0, abs_tol=1e-12):
        return "flat"
    sign = "+" if move > 0 else ""
    return f"{sign}{move:.0%}"


def _sign(value):
    if value > 0:
        return 1.0
    if value < 0:
        return -1.0
    return 0.0


def _trend_signal(price, moving_average, horizon, mode, spans):
    if moving_average in (None, 0) or pd.isna(moving_average):
        return 0.0

    distance = (float(price) - float(moving_average)) / float(moving_average)
    if mode == "distance_scaled":
        span = float(spans.get(int(horizon), spans.get("default", 0.05)))
        if span <= 0:
            return _sign(distance)
        return max(-1.0, min(1.0, distance / span))
    return _sign(distance)
