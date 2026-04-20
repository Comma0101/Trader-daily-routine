#!/usr/bin/env python3
"""
CTA Trend Proxy — Daily Runner

Fetches market data, generates trend signals, constructs a risk-parity
portfolio, and prints a positioning report.

Usage:
    uv run python main.py              # full report, all markets
    uv run python main.py --quick      # skip benchmarks, faster
    uv run python main.py --markets ES GC CL  # specific markets only
"""

import argparse
import json
import logging
import sys

import pandas as pd

from config import CROWDING_LOOKBACK_DAYS, FUTURES_UNIVERSE, RUN_PROFILES
from capital_estimator import CapitalEstimator
from data.futures import FuturesData
from data.benchmarks import BenchmarkData
from flow_estimator import FlowEstimator
from model.trend import TrendModel
from model.portfolio import PortfolioConstructor
from model.tactical_equity import TacticalEquityFlowModel
from report import print_full_report
from schema import build_structured_report
from summary import (
    build_summary_facts,
    maybe_generate_llm_summary,
    render_markdown_summary,
    render_terminal_summary,
)
from validation.position_validation import PositionValidator
from validation.return_validation import ReturnValidator
from validation.signal_validation import SignalValidator
from validation.goldman_benchmark import GoldmanBenchmarkValidator
from validation.goldman_calibration import GoldmanCalibrationSearch


def main():
    parser = argparse.ArgumentParser(description="CTA Trend Proxy — Daily Report")
    parser.add_argument("--profile", choices=sorted(RUN_PROFILES), help="Use a named agent-friendly run profile")
    parser.add_argument("--quick", action="store_true", help="Skip benchmark ETF fetch")
    parser.add_argument("--markets", nargs="+", help="Only these market symbols (e.g. ES GC CL)")
    parser.add_argument("--live", action="store_true", help="Overlay the latest intraday price as a live nowcast")
    parser.add_argument("--refresh", action="store_true", help="Bypass same-day CSV cache and refetch prices")
    parser.add_argument(
        "--assumed-cta-aum",
        type=float,
        help="Optional aggregate CTA AUM assumption in USD for proxy dollar/contract flow estimates",
    )
    parser.add_argument("--summary", action="store_true", help="Print a human-readable summary above the full report")
    parser.add_argument("--summary-only", action="store_true", help="Print only the human-readable summary output")
    parser.add_argument(
        "--llm-summary",
        action="store_true",
        help="Rewrite the summary with Gemini when GEMINI_API_KEY is configured",
    )
    parser.add_argument(
        "--summary-format",
        choices=("terminal", "markdown"),
        default=None,
        help="Render summary output for the terminal or as Markdown",
    )
    parser.add_argument(
        "--output",
        choices=("json",),
        help="Emit a machine-readable JSON payload for agents",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    args = parser.parse_args()

    _apply_profile_defaults(args)
    summary_format = args.summary_format or "terminal"

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Determine universe
    if args.markets:
        unknown = [m for m in args.markets if m not in FUTURES_UNIVERSE]
        if unknown:
            print(f"Unknown markets: {unknown}", file=sys.stderr)
            print(f"Available: {sorted(FUTURES_UNIVERSE.keys())}", file=sys.stderr)
            sys.exit(1)
        universe = {m: FUTURES_UNIVERSE[m] for m in args.markets}
    else:
        universe = FUTURES_UNIVERSE

    show_progress = not args.summary_only and args.output != "json"

    # 1. Fetch data
    if show_progress:
        print("Fetching market data...")
    fd = FuturesData(universe=universe, refresh=args.refresh)
    fd.fetch_all(refresh=args.refresh)

    prices = {}
    daily_prices = {}
    returns = {}
    for sym in universe:
        try:
            daily_prices[sym] = fd.prices(sym, live=False)
            prices[sym] = fd.prices(sym, live=args.live)
            returns[sym] = daily_prices[sym].pct_change().dropna()
        except (ValueError, KeyError):
            continue

    if not prices:
        print("ERROR: No market data fetched. Check your internet connection.", file=sys.stderr)
        sys.exit(1)

    if show_progress:
        print(f"  Loaded {len(prices)}/{len(universe)} markets")

    # 2. Build portfolio (signals + sizing)
    if show_progress:
        print("Computing signals...")
    tm = TrendModel()
    pc = PortfolioConstructor(universe=universe)
    portfolio = pc.build(prices, returns)

    if show_progress:
        print(f"  {len(portfolio['weights'])} markets with signals")

    # 3. Detect recent flips
    flips_by_market = {}
    for sym in portfolio["signal_details"]:
        flips_by_market[sym] = tm.detect_flips(prices[sym], lookback_days=5)

    history = pc.historical_components(daily_prices, returns)
    weight_history = history["weights"]
    flow_estimate = FlowEstimator(universe=universe).estimate(
        current_weights=portfolio.get("weights", {}),
        historical_weights=weight_history,
        current_prices={
            sym: details.get("price")
            for sym, details in portfolio.get("signal_details", {}).items()
        },
        assumed_cta_aum_usd=args.assumed_cta_aum,
        components=history,
    )
    capital_estimate = CapitalEstimator().estimate(
        portfolio,
        assumed_cta_aum_usd=args.assumed_cta_aum,
    )
    tactical_equity = TacticalEquityFlowModel(universe=universe).build(
        prices=daily_prices,
        returns=returns,
        assumed_cta_aum_usd=args.assumed_cta_aum,
    )
    goldman_benchmark = GoldmanBenchmarkValidator().validate(
        prices=daily_prices,
        returns=returns,
        assumed_cta_aum_usd=args.assumed_cta_aum,
    )
    goldman_calibration = GoldmanCalibrationSearch().fit(
        prices=daily_prices,
        returns=returns,
        assumed_cta_aum_usd=args.assumed_cta_aum,
    )

    # 4. Fetch benchmarks (optional)
    etf_returns_df = None
    if not args.quick:
        if show_progress:
            print("Fetching benchmark ETFs...")
        bd = BenchmarkData()
        etf_returns_df = bd.etf_returns()

    # 5. Validation
    if show_progress:
        print("Running validation...")
    signal_validation = SignalValidator().validate(portfolio["signals"])
    position_validation = PositionValidator().validate(portfolio["signals"])

    return_validation = None
    if not args.quick:
        model_returns = pc.backtest_returns(daily_prices, returns)
        if model_returns.empty:
            return_validation = {"error": "Model return history not available"}
        else:
            return_validation = ReturnValidator().validate(model_returns)

    report_context = fd.data_context()

    # 5b. Historical crowding ratios for percentile ranking
    historical_crowding_ratios = _compute_historical_crowding_ratios(
        tm, daily_prices, CROWDING_LOOKBACK_DAYS,
    )

    summary_text = None
    summary_facts = None
    summary_requested = args.summary or args.summary_only or args.llm_summary or args.output == "json"
    if summary_requested:
        summary_facts = build_summary_facts(
            portfolio_result=portfolio,
            universe=universe,
            flips_by_market=flips_by_market,
            flow_estimate=flow_estimate,
            capital_estimate=capital_estimate,
            signal_validation=signal_validation,
            position_validation=position_validation,
            return_validation=return_validation,
            etf_returns_df=etf_returns_df,
            as_of=report_context.get("as_of"),
            data_context=report_context,
            historical_crowding_ratios=historical_crowding_ratios,
            tactical_equity=tactical_equity,
            goldman_benchmark=goldman_benchmark,
            goldman_calibration=goldman_calibration,
        )
        if args.llm_summary:
            summary_text = maybe_generate_llm_summary(
                summary_facts,
                use_llm=True,
                output_format=summary_format,
            )
        elif summary_format == "markdown":
            summary_text = render_markdown_summary(summary_facts)
        else:
            summary_text = render_terminal_summary(summary_facts)

    if args.output == "json":
        structured = build_structured_report(summary_facts) if summary_facts else {}
        payload = {
            "profile": args.profile,
            "markets": sorted(universe.keys()),
            "summary_format": summary_format,
            "summary_text": summary_text,
            "structured_report": structured,
        }
        print(json.dumps(_json_ready(payload), indent=2))
        return

    if args.summary_only:
        print(summary_text)
        return

    # 6. Print report
    composite_validation = None
    crowding_facts = None
    if summary_facts:
        composite_validation = summary_facts.get("validation", {}).get("composite")
        crowding_facts = summary_facts.get("crowding")

    print_full_report(
        portfolio_result=portfolio,
        universe=universe,
        trend_model=tm,
        flips_by_market=flips_by_market,
        summary_text=summary_text,
        report_context=report_context,
        flow_estimate=flow_estimate,
        capital_estimate=capital_estimate,
        tactical_equity=tactical_equity,
        goldman_benchmark=goldman_benchmark,
        goldman_calibration=goldman_calibration,
        etf_returns_df=etf_returns_df,
        signal_validation=signal_validation,
        position_validation=position_validation,
        return_validation=return_validation,
        composite_validation=composite_validation,
        crowding_facts=crowding_facts,
    )


def _compute_historical_crowding_ratios(trend_model, daily_prices, lookback_days):
    """Compute daily crowded_count/total ratio for trailing lookback window."""
    signal_frames = {}
    for sym, price_series in daily_prices.items():
        try:
            sig = trend_model.signals(price_series)["signal"].dropna()
            if not sig.empty:
                signal_frames[sym] = sig
        except Exception:
            continue

    if not signal_frames:
        return []

    combined = pd.DataFrame(signal_frames)
    combined = combined.iloc[-lookback_days:]

    ratios = []
    for _, row in combined.iterrows():
        valid = row.dropna()
        if len(valid) == 0:
            continue
        crowded = ((valid >= 1.0) | (valid <= -1.0)).sum()
        ratios.append(crowded / len(valid))

    return ratios


def _apply_profile_defaults(args):
    if not args.profile:
        return

    profile = RUN_PROFILES[args.profile]
    for key, value in profile.items():
        if key == "description":
            continue
        if key == "summary_format":
            if args.summary_format is None:
                args.summary_format = value
            continue
        if key == "markets":
            if not args.markets:
                args.markets = list(value)
            continue
        if isinstance(value, bool):
            setattr(args, key, getattr(args, key) or value)
        elif getattr(args, key, None) in (None, []):
            setattr(args, key, value)


def _json_ready(value):
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
        try:
            return value.isoformat()
        except TypeError:
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


if __name__ == "__main__":
    main()
