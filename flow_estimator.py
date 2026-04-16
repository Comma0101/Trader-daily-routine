"""Estimate CTA proxy flow from model weight changes."""

from __future__ import annotations

import math

import pandas as pd

from config import FUTURES_UNIVERSE


class FlowEstimator:
    """Estimate model-implied CTA proxy flows from target weight changes."""

    def __init__(self, universe=None):
        self.universe = universe or FUTURES_UNIVERSE

    def estimate(
        self,
        current_weights,
        historical_weights,
        current_prices,
        assumed_cta_aum_usd=None,
    ) -> dict:
        flow = {
            "estimation_label": "Model-implied target notional change (not observed flow)",
            "assumed_cta_aum_usd": float(assumed_cta_aum_usd) if assumed_cta_aum_usd is not None else None,
            "markets": {},
            "top_notional_increase_1d": [],
            "top_notional_decrease_1d": [],
            "top_notional_increase_5d": [],
            "top_notional_decrease_5d": [],
            "sector_flows_1d": {},
            "sector_flows_5d": {},
        }

        if not isinstance(current_weights, dict) or not current_weights:
            return flow

        weight_frame = historical_weights if isinstance(historical_weights, pd.DataFrame) else pd.DataFrame()
        aum = flow["assumed_cta_aum_usd"]

        for symbol, current_weight in sorted(current_weights.items()):
            meta = self.universe.get(symbol, {})
            price = _to_float(current_prices.get(symbol)) if isinstance(current_prices, dict) else None
            prev_1d = _historical_weight(weight_frame, symbol, 1)
            prev_5d = _historical_weight(weight_frame, symbol, 5)
            delta_1d = None if prev_1d is None else float(current_weight or 0.0) - prev_1d
            delta_5d = None if prev_5d is None else float(current_weight or 0.0) - prev_5d

            row = {
                "symbol": symbol,
                "market": meta.get("name", symbol),
                "sector": meta.get("sector"),
                "price_used": price,
                "delta_weight_1d": delta_1d,
                "delta_weight_5d": delta_5d,
                "estimated_notional_change_usd_1d": None,
                "estimated_notional_change_usd_5d": None,
                "estimated_contract_equivalent_1d": None,
                "estimated_contract_equivalent_5d": None,
            }

            multiplier = _to_float(meta.get("contract_multiplier"))
            fx_rate = _to_float(meta.get("fx_rate_to_usd")) or 1.0
            contract_notional = None
            if price is not None and multiplier is not None and fx_rate:
                contract_notional = price * multiplier * fx_rate

            if aum is not None:
                if delta_1d is not None:
                    row["estimated_notional_change_usd_1d"] = delta_1d * aum
                    if contract_notional:
                        row["estimated_contract_equivalent_1d"] = row["estimated_notional_change_usd_1d"] / contract_notional
                if delta_5d is not None:
                    row["estimated_notional_change_usd_5d"] = delta_5d * aum
                    if contract_notional:
                        row["estimated_contract_equivalent_5d"] = row["estimated_notional_change_usd_5d"] / contract_notional

            flow["markets"][symbol] = row

        flow["top_notional_increase_1d"] = _rank_flows(flow["markets"].values(), delta_key="delta_weight_1d", direction="increase")
        flow["top_notional_decrease_1d"] = _rank_flows(flow["markets"].values(), delta_key="delta_weight_1d", direction="decrease")
        flow["top_notional_increase_5d"] = _rank_flows(flow["markets"].values(), delta_key="delta_weight_5d", direction="increase")
        flow["top_notional_decrease_5d"] = _rank_flows(flow["markets"].values(), delta_key="delta_weight_5d", direction="decrease")
        flow["sector_flows_1d"] = _aggregate_sector_flows(flow["markets"].values(), delta_key="delta_weight_1d", usd_key="estimated_notional_change_usd_1d")
        flow["sector_flows_5d"] = _aggregate_sector_flows(flow["markets"].values(), delta_key="delta_weight_5d", usd_key="estimated_notional_change_usd_5d")
        return flow


def _historical_weight(weight_frame, symbol, lookback):
    if weight_frame.empty or symbol not in weight_frame.columns:
        return None

    history = weight_frame[symbol].dropna()
    if history.empty:
        return None

    if lookback <= 1:
        return float(history.iloc[-1])
    if len(history) >= lookback:
        return float(history.iloc[-lookback])
    return float(history.iloc[0])


def _rank_flows(rows, delta_key, direction):
    ranked = []
    for row in rows:
        delta = row.get(delta_key)
        if delta is None:
            continue
        if direction == "increase" and delta > 0:
            ranked.append(dict(row))
        elif direction == "decrease" and delta < 0:
            ranked.append(dict(row))

    if direction == "increase":
        ranked.sort(key=lambda item: (-round(float(item[delta_key]), 10), item["symbol"]))
    else:
        ranked.sort(key=lambda item: (round(float(item[delta_key]), 10), item["symbol"]))
    return ranked[:5]


def _aggregate_sector_flows(rows, delta_key, usd_key):
    sectors = {}
    for row in rows:
        sector = row.get("sector") or "Unknown"
        sectors.setdefault(sector, {"delta_weight": 0.0, "_usd_accum": 0.0, "has_usd": False})

        delta = row.get(delta_key)
        if delta is not None:
            sectors[sector]["delta_weight"] += float(delta)

        usd_value = row.get(usd_key)
        if usd_value is not None:
            sectors[sector]["_usd_accum"] += float(usd_value)
            sectors[sector]["has_usd"] = True

    for sector, values in sectors.items():
        if not values["has_usd"]:
            values["estimated_notional_change_usd"] = None
        else:
            values["estimated_notional_change_usd"] = values["_usd_accum"]
        del values["_usd_accum"]
        del values["has_usd"]

    return sectors


def _to_float(value):
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return numeric
