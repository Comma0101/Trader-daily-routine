"""Estimate CTA proxy flow from model weight changes.

When ``components`` (signal / vol-scalar / allocation-budget / cap-factor
histories) are supplied, each weight delta is decomposed into four additive
effects so downstream consumers can separate signal-driven flow from
vol-targeting and allocation noise.
"""

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
        components=None,
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
            prev_1d = _historical_weight(weight_frame, symbol, 1, current_weight=current_weight)
            prev_5d = _historical_weight(weight_frame, symbol, 5, current_weight=current_weight)
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

        # --- Driver decomposition (when component histories are available) ---
        if components is not None:
            for symbol in list(flow["markets"]):
                row = flow["markets"][symbol]
                for lookback, suffix in ((1, "1d"), (5, "5d")):
                    decomp = _decompose_flow(components, symbol, lookback)
                    row[f"decomposition_{suffix}"] = decomp
            flow["aggregate_decomposition_1d"] = _aggregate_decomposition(
                flow["markets"], "1d", aum,
            )
            flow["aggregate_decomposition_5d"] = _aggregate_decomposition(
                flow["markets"], "5d", aum,
            )

        flow["top_notional_increase_1d"] = _rank_flows(flow["markets"].values(), delta_key="delta_weight_1d", direction="increase")
        flow["top_notional_decrease_1d"] = _rank_flows(flow["markets"].values(), delta_key="delta_weight_1d", direction="decrease")
        flow["top_notional_increase_5d"] = _rank_flows(flow["markets"].values(), delta_key="delta_weight_5d", direction="increase")
        flow["top_notional_decrease_5d"] = _rank_flows(flow["markets"].values(), delta_key="delta_weight_5d", direction="decrease")
        flow["sector_flows_1d"] = _aggregate_sector_flows(flow["markets"].values(), delta_key="delta_weight_1d", usd_key="estimated_notional_change_usd_1d")
        flow["sector_flows_5d"] = _aggregate_sector_flows(flow["markets"].values(), delta_key="delta_weight_5d", usd_key="estimated_notional_change_usd_5d")
        return flow


def _historical_weight(weight_frame, symbol, lookback, current_weight=None):
    if weight_frame.empty or symbol not in weight_frame.columns:
        return None

    history = weight_frame[symbol].dropna()
    if history.empty:
        return None

    offset = max(int(lookback or 1), 1)

    if current_weight is not None:
        current_val = _to_float(current_weight)
        last_val = _to_float(history.iloc[-1])
        if current_val is not None and last_val is not None:
            # If the current target is already the last row in history
            # (daily-close mode), step back one extra row to get the prior close.
            if math.isclose(current_val, last_val, rel_tol=1e-9, abs_tol=1e-12):
                offset += 1

    if len(history) >= offset:
        return float(history.iloc[-offset])
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


def _decompose_flow(components, symbol, lookback):
    """Decompose a weight delta into signal / vol / allocation / cap effects.

    Uses a sequential attribution (signal first, then vol, alloc, cap).
    The four effects sum exactly to the daily-close weight delta.
    """
    signals = components.get("signals", pd.DataFrame())
    vol_scalars = components.get("vol_scalars", pd.DataFrame())
    alloc_budgets = components.get("alloc_budgets", pd.DataFrame())
    cap_factors = components.get("cap_factors", pd.Series(dtype=float))

    if signals.empty or symbol not in signals.columns:
        return None

    sig_col = signals[symbol].dropna()
    if len(sig_col) < 2:
        return None

    # Current values (last available row)
    sig_now = float(sig_col.iloc[-1])
    vol_now = _component_last(vol_scalars, symbol)
    alloc_now = _component_last(alloc_budgets, symbol)
    cap_now = float(cap_factors.iloc[-1]) if not cap_factors.empty else 1.0

    # Prior values
    sig_prev = _component_prior(signals, symbol, lookback)
    vol_prev = _component_prior(vol_scalars, symbol, lookback)
    alloc_prev = _component_prior(alloc_budgets, symbol, lookback)
    cap_prev = _series_prior(cap_factors, lookback)

    if any(v is None for v in (sig_now, vol_now, alloc_now,
                                sig_prev, vol_prev, alloc_prev,
                                cap_now, cap_prev)):
        return None

    # Old weight
    w_old = alloc_prev * sig_prev * vol_prev * cap_prev

    # Sequential decomposition: signal → vol → alloc → cap
    w_after_signal = alloc_prev * sig_now * vol_prev * cap_prev
    signal_effect = w_after_signal - w_old

    w_after_vol = alloc_prev * sig_now * vol_now * cap_prev
    vol_effect = w_after_vol - w_after_signal

    w_after_alloc = alloc_now * sig_now * vol_now * cap_prev
    alloc_effect = w_after_alloc - w_after_vol

    w_new = alloc_now * sig_now * vol_now * cap_now
    cap_effect = w_new - w_after_alloc

    return {
        "signal_effect": signal_effect,
        "vol_target_effect": vol_effect,
        "allocation_effect": alloc_effect,
        "leverage_cap_effect": cap_effect,
        "total": signal_effect + vol_effect + alloc_effect + cap_effect,
        "flow_type": _classify_flow(sig_prev, sig_now),
        "signal_prev": sig_prev,
        "signal_now": sig_now,
    }


def _classify_flow(sig_prev, sig_now):
    """Label the type of flow based on signal transition."""
    if sig_prev == sig_now:
        return "rebalance"
    if sig_prev == 0 and sig_now != 0:
        return "new_entry"
    if sig_prev != 0 and sig_now == 0:
        return "exit"
    if sig_prev < 0 and sig_now > 0:
        return "short_cover_to_long"
    if sig_prev > 0 and sig_now < 0:
        return "long_exit_to_short"
    # Signal changed magnitude but same sign
    if (sig_prev > 0 and sig_now > 0) or (sig_prev < 0 and sig_now < 0):
        return "conviction_change"
    return "regime_change"


def _aggregate_decomposition(markets, suffix, aum):
    """Sum decomposition effects across all markets."""
    totals = {
        "signal_effect": 0.0,
        "vol_target_effect": 0.0,
        "allocation_effect": 0.0,
        "leverage_cap_effect": 0.0,
    }
    flow_type_counts = {}

    for row in markets.values():
        decomp = row.get(f"decomposition_{suffix}")
        if decomp is None:
            continue
        for key in totals:
            totals[key] += decomp.get(key, 0.0)
        ft = decomp.get("flow_type", "unknown")
        flow_type_counts[ft] = flow_type_counts.get(ft, 0) + 1

    result = {
        "signal_effect_weight": totals["signal_effect"],
        "vol_target_effect_weight": totals["vol_target_effect"],
        "allocation_effect_weight": totals["allocation_effect"],
        "leverage_cap_effect_weight": totals["leverage_cap_effect"],
        "flow_type_counts": flow_type_counts,
    }

    if aum is not None:
        result["signal_effect_usd"] = totals["signal_effect"] * aum
        result["vol_target_effect_usd"] = totals["vol_target_effect"] * aum
        result["allocation_effect_usd"] = totals["allocation_effect"] * aum
        result["leverage_cap_effect_usd"] = totals["leverage_cap_effect"] * aum

    return result


def _component_last(frame, symbol):
    """Last non-NaN value for a symbol in a component DataFrame."""
    if frame.empty or symbol not in frame.columns:
        return None
    col = frame[symbol].dropna()
    return float(col.iloc[-1]) if not col.empty else None


def _component_prior(frame, symbol, lookback):
    """Value from ``lookback`` rows before the end of a component column."""
    if frame.empty or symbol not in frame.columns:
        return None
    col = frame[symbol].dropna()
    if col.empty:
        return None
    offset = max(int(lookback or 1), 1) + 1
    if len(col) >= offset:
        return float(col.iloc[-offset])
    return float(col.iloc[0])


def _series_prior(series, lookback):
    """Value from ``lookback`` rows before the end of a Series."""
    if series.empty:
        return None
    offset = max(int(lookback or 1), 1) + 1
    if len(series) >= offset:
        return float(series.iloc[-offset])
    return float(series.iloc[0])


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
