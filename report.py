"""
Terminal dashboard for CTA trend proxy.

Prints a human-readable report of current positioning, signal flips,
sector breakdown, crowding risk, and benchmark comparison.
"""

import sys
from datetime import datetime

import pandas as pd
from tabulate import tabulate


def print_header():
    today = datetime.now().strftime("%Y-%m-%d")
    print()
    print(f"  CTA Trend Proxy Report — {today}")
    print("  " + "=" * 52)
    print()


def print_positioning(portfolio_result: dict, universe: dict, trend_model):
    """Print per-market positioning table."""
    details = portfolio_result["signal_details"]
    weights = portfolio_result["weights"]
    vol_scalars = portfolio_result["vol_scalars"]

    rows = []
    for sym in sorted(details.keys(), key=lambda s: universe[s]["sector"]):
        d = details[sym]
        meta = universe[sym]
        label = trend_model.signal_label(d["signal"])
        w = weights.get(sym, 0.0)

        rows.append([
            meta["sector"],
            sym,
            meta["name"],
            f'{d["signal"]:+.1f}',
            label,
            f'{d["signal_short"]:+.0f}',
            f'{d["signal_long"]:+.0f}',
            f'{w:+.4f}',
            f'{vol_scalars.get(sym, 0):.2f}x',
            str(d["days_in_position"]),
        ])

    print("  MARKET POSITIONING")
    print("  " + "-" * 52)
    print(tabulate(
        rows,
        headers=["Sector", "Sym", "Market", "Sig", "Dir", "S20", "S120", "Weight", "VolScl", "Days"],
        tablefmt="simple",
        colalign=("left", "left", "left", "right", "left", "right", "right", "right", "right", "right"),
    ))
    print()


def print_signal_flips(flips_by_market: dict[str, list], universe: dict):
    """Print recent signal flips (high-impact events)."""
    has_flips = any(len(f) > 0 for f in flips_by_market.values())
    if not has_flips:
        print("  SIGNAL FLIPS (5d): None")
        print()
        return

    print("  SIGNAL FLIPS (5d)")
    print("  " + "-" * 52)
    rows = []
    for sym, flips in sorted(flips_by_market.items()):
        for f in flips:
            meta = universe[sym]
            rows.append([
                f["date"].strftime("%Y-%m-%d"),
                sym,
                meta["name"],
                f'{f["from_label"]} → {f["to_label"]}',
                f'{f["price"]:.2f}' if f["price"] else "N/A",
            ])

    print(tabulate(
        rows,
        headers=["Date", "Sym", "Market", "Flip", "Price"],
        tablefmt="simple",
    ))
    print()


def print_sector_summary(portfolio_result: dict):
    """Print sector exposure breakdown."""
    sector_exp = portfolio_result["sector_exposure"]
    gross = portfolio_result["gross_leverage"]
    net = portfolio_result["net_exposure"]

    rows = []
    for sector, exp in sorted(sector_exp.items()):
        if abs(exp) < 0.0001:
            direction = "FLAT"
        elif exp > 0:
            direction = "NET LONG"
        else:
            direction = "NET SHORT"
        rows.append([sector, f"{exp:+.4f}", direction])

    print("  SECTOR EXPOSURE")
    print("  " + "-" * 52)
    print(tabulate(rows, headers=["Sector", "Net Weight", "Direction"], tablefmt="simple"))
    print(f"\n  Gross leverage: {gross:.2f}x  |  Net exposure: {net:+.2f}")
    print()


def print_crowding(portfolio_result: dict, universe: dict, trend_model, crowding_facts=None):
    """Print crowding risk — markets where signal is max long or max short."""
    details = portfolio_result["signal_details"]
    max_long = []
    max_short = []

    for sym, d in details.items():
        if d["signal"] >= 1.0:
            max_long.append((sym, universe[sym]["name"], d["days_in_position"]))
        elif d["signal"] <= -1.0:
            max_short.append((sym, universe[sym]["name"], d["days_in_position"]))

    print("  CROWDING RISK")
    print("  " + "-" * 52)

    if max_long:
        long_sorted = sorted(max_long, key=lambda x: -x[2])
        print(f"  MAX LONG ({len(max_long)} markets):")
        for sym, name, days in long_sorted:
            print(f"    {sym:4s} {name:22s} ({days}d held)")
    else:
        print("  MAX LONG: None")

    if max_short:
        short_sorted = sorted(max_short, key=lambda x: -x[2])
        print(f"  MAX SHORT ({len(max_short)} markets):")
        for sym, name, days in short_sorted:
            print(f"    {sym:4s} {name:22s} ({days}d held)")
    else:
        print("  MAX SHORT: None")

    total = len(details)
    crowded = len(max_long) + len(max_short)
    print(f"\n  {crowded}/{total} markets at max signal — ", end="")
    if crowded / total > 0.7:
        print("HIGH crowding (reversal risk elevated)")
    elif crowded / total > 0.4:
        print("MODERATE crowding")
    else:
        print("LOW crowding")

    if crowding_facts and crowding_facts.get("percentile") is not None:
        pctile = crowding_facts["percentile"]
        context = crowding_facts.get("percentile_context", f"{pctile}th percentile")
        print(f"  {context}")

    print()


def print_reversal_levels(portfolio_result: dict, universe: dict):
    """Print price levels where signals would flip."""
    details = portfolio_result["signal_details"]

    rows = []
    for sym in sorted(details.keys(), key=lambda s: universe[s]["sector"]):
        d = details[sym]
        meta = universe[sym]
        price = d["price"]
        rev_short = d["reversal_price_short"]
        rev_long = d["reversal_price_long"]

        # Distance to nearest flip as percentage
        dist_short = (price - rev_short) / price * 100 if price else 0
        dist_long = (price - rev_long) / price * 100 if price else 0
        nearest = min(abs(dist_short), abs(dist_long))

        if nearest < 5.0:  # show markets in very_near, near, or moderate zones
            bucket = _bucket_distance(nearest)
            rows.append([
                sym,
                meta["name"],
                f"{price:.2f}",
                f"{rev_short:.2f} ({dist_short:+.1f}%)",
                f"{rev_long:.2f} ({dist_long:+.1f}%)",
                f"({bucket})",
            ])

    if rows:
        print("  SIGNAL WATCH LIST (within 5% of flip)")
        print("  " + "-" * 52)
        print(tabulate(
            rows,
            headers=["Sym", "Market", "Price", "20d MA (dist)", "120d MA (dist)", "Zone"],
            tablefmt="simple",
        ))
    else:
        print("  SIGNAL WATCH LIST: No markets within 5% of a flip")
    print()


def _compound_return(series: pd.Series) -> float | None:
    clean = series.dropna()
    if clean.empty:
        return None
    return float((1.0 + clean).prod() - 1.0)


def summarize_etf_performance(etf_returns_df, as_of=None):
    """Summarize benchmark ETF performance with calendar YTD compounding."""
    if etf_returns_df is None or etf_returns_df.empty:
        return []

    as_of = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(etf_returns_df.index.max())
    rows = []

    for col in etf_returns_df.columns:
        series = etf_returns_df[col].dropna()
        if series.empty:
            continue

        ytd_series = series[series.index.year == as_of.year]
        last_1d = float(series.iloc[-1])
        last_5d = _compound_return(series.iloc[-5:]) if len(series) >= 5 else None
        last_20d = _compound_return(series.iloc[-20:]) if len(series) >= 20 else None
        ytd = _compound_return(ytd_series)

        rows.append([
            col,
            f"{last_1d:+.2%}",
            f"{last_5d:+.2%}" if last_5d is not None else "N/A",
            f"{last_20d:+.2%}" if last_20d is not None else "N/A",
            f"{ytd:+.2%}" if ytd is not None else "N/A",
        ])

    return rows


def print_benchmark_etfs(etf_returns_df):
    """Print recent benchmark ETF performance."""
    if etf_returns_df is None or etf_returns_df.empty:
        print("  BENCHMARK ETFs: Data not available")
        print()
        return

    print("  BENCHMARK ETFs (recent performance)")
    print("  " + "-" * 52)
    rows = summarize_etf_performance(etf_returns_df)
    print(tabulate(rows, headers=["ETF", "1D", "5D", "20D", "YTD"], tablefmt="simple"))
    print()


def print_validation_summary(signal_validation=None, position_validation=None, return_validation=None, composite_validation=None):
    """Print compact validation results and notes."""
    if not any([signal_validation, position_validation, return_validation, composite_validation]):
        return

    print("  VALIDATION")
    print("  " + "-" * 52)

    if composite_validation:
        score = composite_validation.get("composite_score", 0)
        grade = composite_validation.get("grade", "?")
        note = composite_validation.get("note", "")
        print(f"  Composite: {score}/100 ({grade}) — {note}")

    if signal_validation:
        note = signal_validation.get("note")
        if note:
            print(f"  SG signal validation: {note}")
        else:
            agreement = signal_validation.get("agreement_rate")
            coverage = signal_validation.get("coverage", 0)
            if agreement is None:
                print("  SG signal validation: No comparable data")
            else:
                print(f"  SG signal agreement: {agreement:.1%} ({coverage} markets)")

    if position_validation:
        coverage = position_validation.get("coverage", 0)
        agreement = position_validation.get("agreement_rate")
        if coverage == 0 or agreement is None:
            print("  COT directional agreement: No current overlap")
        else:
            print(f"  COT directional agreement: {agreement:.1%} ({coverage} markets)")
            for report_type, stats in sorted(position_validation.get("by_report_type", {}).items()):
                print(
                    f"    {report_type}: {stats['agreement_rate']:.1%} "
                    f"({stats['count']} markets)"
                )

    if return_validation:
        error = return_validation.get("error")
        if error:
            print(f"  Return validation: {error}")
        else:
            print(
                f"  Return validation: {return_validation['summary']} "
                f"({return_validation['overlap_days']} overlap days)"
            )
            dbmf = return_validation.get("correlations", {}).get("DBMF")
            if dbmf:
                recent = dbmf.get("recent_60d")
                recent_text = f"{recent:.2f}" if recent is not None else "N/A"
                print(
                    f"    DBMF corr: {dbmf['full_period']:.2f} full | "
                    f"{recent_text} 60d"
                )

    print()


def print_investment_overview(portfolio_result=None, flow_estimate=None, capital_estimate=None):
    """Print a comprehensive investment overview with AUM, deployment, and per-market flows."""
    if not capital_estimate and not flow_estimate:
        return

    print("  INVESTMENT OVERVIEW")
    print("  " + "-" * 52)

    if capital_estimate:
        basis = capital_estimate.get("aum_basis", {})
        aum_usd = basis.get("aum_usd")
        if aum_usd is not None:
            print(f"  AUM basis: {basis.get('label', 'Unknown')} ({_format_usd(aum_usd)})")

        gross_pct = capital_estimate.get("gross_risk_deployed_pct_of_aum")
        gross_usd = capital_estimate.get("estimated_gross_risk_deployed_usd")
        net_pct = capital_estimate.get("net_risk_deployed_pct_of_aum")
        net_usd = capital_estimate.get("estimated_net_risk_deployed_usd")
        headroom_pct = capital_estimate.get("remaining_gross_headroom_pct_of_aum")
        headroom_usd = capital_estimate.get("estimated_remaining_gross_headroom_usd")

        parts = []
        if gross_usd is not None:
            parts.append(f"Gross: {_format_usd(gross_usd)} ({_format_pct(gross_pct)})")
        if net_usd is not None:
            parts.append(f"Net: {_format_usd(net_usd)} ({_format_pct(net_pct)})")
        if headroom_usd is not None:
            parts.append(f"Headroom: {_format_usd(headroom_usd)} ({_format_pct(headroom_pct)})")
        if parts:
            print(f"  {' | '.join(parts)}")

    if flow_estimate:
        markets = flow_estimate.get("markets", {})
        if markets:
            weights = portfolio_result.get("weights", {}) if portfolio_result else {}
            details = portfolio_result.get("signal_details", {}) if portfolio_result else {}
            universe_meta = {}

            rows = []
            for symbol in sorted(markets.keys()):
                fm = markets[symbol]
                w = weights.get(symbol, 0.0)
                sig = details.get(symbol, {}).get("signal", 0.0)
                direction = "LONG" if sig > 0 else ("SHORT" if sig < 0 else "FLAT")
                delta_5d = fm.get("delta_weight_5d")
                flow_5d = fm.get("estimated_notional_change_usd_5d")
                contracts_5d = fm.get("estimated_contract_equivalent_5d")

                rows.append([
                    symbol,
                    fm.get("market", symbol),
                    direction,
                    f"{float(w):+.4f}",
                    _format_pct(delta_5d),
                    _format_usd(flow_5d),
                    f"{contracts_5d:+.0f}" if contracts_5d is not None else "N/A",
                ])

            print()
            print(tabulate(
                rows,
                headers=["Sym", "Market", "Dir", "Weight", "5D dW", "5D dNotional", "5D Ctrs"],
                tablefmt="simple",
                colalign=("left", "left", "left", "right", "right", "right", "right"),
            ))

        sector_flows = flow_estimate.get("sector_flows_5d", {})
        if sector_flows:
            sector_rows = []
            for sector in sorted(sector_flows.keys()):
                sf = sector_flows[sector]
                sector_rows.append([
                    sector,
                    _format_pct(sf.get("delta_weight")),
                    _format_usd(sf.get("estimated_notional_change_usd")),
                ])
            print()
            print("  Sector subtotals (5D):")
            print(tabulate(
                sector_rows,
                headers=["Sector", "dW", "Flow"],
                tablefmt="simple",
            ))

    print()


def print_flow_summary(flow_estimate=None):
    """Print estimated CTA proxy flow."""
    if not flow_estimate:
        return

    print("  MODELED TARGET NOTIONAL CHANGES")
    print("  " + "-" * 52)

    assumed_aum = flow_estimate.get("assumed_cta_aum_usd")
    if assumed_aum is None:
        print("  Relative changes only — no CTA AUM assumption provided")
    else:
        print(f"  CTA AUM assumption: {_format_usd(assumed_aum)}")

    rows = []
    row_symbols = []
    for key in ("top_notional_increase_1d", "top_notional_decrease_1d", "top_notional_increase_5d", "top_notional_decrease_5d"):
        for item in flow_estimate.get(key, [])[:3]:
            symbol = item.get("symbol")
            if symbol and symbol not in row_symbols:
                row_symbols.append(symbol)

    markets = dict(flow_estimate.get("markets", {}))
    for key in ("top_notional_increase_1d", "top_notional_decrease_1d", "top_notional_increase_5d", "top_notional_decrease_5d"):
        for item in flow_estimate.get(key, [])[:3]:
            symbol = item.get("symbol")
            if symbol and symbol not in markets:
                markets[symbol] = dict(item)
    for symbol in row_symbols:
        item = markets.get(symbol, {})
        if not item:
            continue

        delta_1d = item.get("delta_weight_1d")
        delta_5d = item.get("delta_weight_5d")
        if abs(float(delta_1d or 0.0)) > 1e-12:
            side = "INCR" if delta_1d > 0 else "DECR"
        elif abs(float(delta_5d or 0.0)) > 1e-12:
            side = "INCR" if delta_5d > 0 else "DECR"
        else:
            side = "FLAT"

        rows.append(
            [
                side,
                symbol,
                item.get("market", symbol),
                _format_pct(delta_1d),
                _format_usd(item.get("estimated_notional_change_usd_1d")),
                _format_pct(delta_5d),
                _format_usd(item.get("estimated_notional_change_usd_5d")),
            ]
        )

    if rows:
        print(
            tabulate(
                rows,
                headers=["Side", "Sym", "Market", "1D dW", "1D dNotional", "5D dW", "5D dNotional"],
                tablefmt="simple",
            )
        )
    else:
        print("  No non-zero notional changes available")
    print()


def print_capital_state(capital_estimate=None):
    """Print estimated CTA capital state."""
    if not capital_estimate:
        return

    print("  ESTIMATED CTA CAPITAL STATE")
    print("  " + "-" * 52)
    basis = capital_estimate.get("aum_basis", {})
    if basis.get("aum_usd") is not None:
        print(f"  AUM basis: {basis.get('label', 'Unknown')} ({_format_usd(basis.get('aum_usd'))})")
    rows = [
        ["Gross risk deployed", _format_usd(capital_estimate.get("estimated_gross_risk_deployed_usd"))],
        ["Net risk deployed", _format_usd(capital_estimate.get("estimated_net_risk_deployed_usd"))],
        ["Remaining gross headroom", _format_usd(capital_estimate.get("estimated_remaining_gross_headroom_usd"))],
    ]
    print(tabulate(rows, headers=["Metric", "Estimate"], tablefmt="simple"))
    note = capital_estimate.get("note")
    if note:
        print(f"\n  Note: {note}")
    print()


def print_data_context(report_context=None):
    """Print whether the report is using official daily closes or a live nowcast."""
    if not report_context:
        return

    official_close_date = report_context.get("official_close_date")
    if not official_close_date:
        return

    if report_context.get("mode") == "live" and report_context.get("live_as_of"):
        print(
            "  Data mode: LIVE nowcast"
            f"  |  Official close: {official_close_date}"
            f"  |  Live as of: {report_context['live_as_of']}"
        )
    else:
        print(f"  Data mode: DAILY close  |  Official close: {official_close_date}")
    print()


def print_full_report(
    portfolio_result,
    universe,
    trend_model,
    flips_by_market,
    summary_text=None,
    report_context=None,
    flow_estimate=None,
    capital_estimate=None,
    etf_returns_df=None,
    signal_validation=None,
    position_validation=None,
    return_validation=None,
    composite_validation=None,
    crowding_facts=None,
):
    """Print the complete daily report."""
    if summary_text:
        print(summary_text.strip())
        print()

    print_header()
    print_data_context(report_context=report_context)
    print_investment_overview(
        portfolio_result=portfolio_result,
        flow_estimate=flow_estimate,
        capital_estimate=capital_estimate,
    )
    print_positioning(portfolio_result, universe, trend_model)
    print_signal_flips(flips_by_market, universe)
    print_sector_summary(portfolio_result)
    print_crowding(portfolio_result, universe, trend_model, crowding_facts=crowding_facts)
    print_reversal_levels(portfolio_result, universe)
    print_flow_summary(flow_estimate=flow_estimate)
    print_capital_state(capital_estimate=capital_estimate)
    print_validation_summary(
        signal_validation=signal_validation,
        position_validation=position_validation,
        return_validation=return_validation,
        composite_validation=composite_validation,
    )
    if etf_returns_df is not None:
        print_benchmark_etfs(etf_returns_df)


def _format_usd(value):
    if value is None:
        return "N/A"
    amount = float(value)
    abs_amount = abs(amount)
    prefix = "-" if amount < 0 else ""
    if abs_amount >= 1_000_000_000:
        return f"{prefix}${abs_amount / 1_000_000_000:.2f}B"
    if abs_amount >= 1_000_000:
        return f"{prefix}${abs_amount / 1_000_000:.2f}M"
    if abs_amount >= 1_000:
        return f"{prefix}${abs_amount / 1_000:.2f}K"
    return f"{prefix}${abs_amount:,.0f}"


def _format_pct(value):
    if value is None:
        return "N/A"
    return f"{float(value):+.2%}"


def _bucket_distance(distance_pct):
    d = abs(float(distance_pct or 0))
    if d < 1.0:
        return "very_near"
    if d < 2.5:
        return "near"
    if d < 5.0:
        return "moderate"
    return "far"
