import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import pandas as pd

import main
from report import print_full_report, print_validation_summary, summarize_etf_performance


class ReportSummaryTests(unittest.TestCase):
    def test_etf_summary_uses_calendar_ytd_compounding(self):
        dates = pd.to_datetime(
            ["2025-12-31", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
        )
        etf_returns = pd.DataFrame(
            {
                "DBMF": [0.10, 0.01, 0.02, -0.01, 0.03],
            },
            index=dates,
        )

        rows = summarize_etf_performance(etf_returns, as_of=pd.Timestamp("2026-01-07"))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "DBMF")
        self.assertEqual(rows[0][4], "+5.05%")

    def test_validation_summary_prints_available_sections(self):
        output = io.StringIO()
        with redirect_stdout(output):
            print_validation_summary(
                signal_validation={"coverage": 0, "note": "SG data unavailable"},
                position_validation={
                    "coverage": 9,
                    "agreement_rate": 2 / 3,
                    "by_report_type": {
                        "TFF": {"agreement_rate": 0.4, "count": 5},
                        "DISAGG": {"agreement_rate": 1.0, "count": 4},
                    },
                },
                return_validation={
                    "summary": "Good",
                    "overlap_days": 120,
                    "correlations": {"DBMF": {"full_period": 0.62, "recent_60d": 0.58}},
                },
            )

        rendered = output.getvalue()
        self.assertIn("VALIDATION", rendered)
        self.assertIn("SG data unavailable", rendered)
        self.assertIn("COT directional agreement", rendered)
        self.assertIn("DBMF corr", rendered)


class ReportSummaryIntegrationTests(unittest.TestCase):
    def test_full_report_prints_summary_before_report_header_when_summary_text_is_provided(self):
        portfolio_result = {
            "signal_details": {
                "ES": {
                    "signal": 0.0,
                    "signal_short": -1.0,
                    "signal_long": 1.0,
                    "price": 100.0,
                    "days_in_position": 1,
                    "reversal_price_short": 99.0,
                    "reversal_price_long": 101.0,
                }
            },
            "weights": {"ES": 0.0},
            "vol_scalars": {"ES": 1.0},
            "sector_exposure": {"Equity Index": 0.0},
            "gross_leverage": 0.0,
            "net_exposure": 0.0,
        }
        universe = {"ES": {"name": "S&P 500", "sector": "Equity Index"}}
        trend_model = mock.Mock()
        trend_model.signal_label.return_value = "FLAT"

        output = io.StringIO()
        with redirect_stdout(output):
            print_full_report(
                portfolio_result=portfolio_result,
                universe=universe,
                trend_model=trend_model,
                flips_by_market={"ES": []},
                summary_text="Summary line 1\nSummary line 2",
            )

        rendered = output.getvalue()
        self.assertIn("Summary line 1", rendered)
        self.assertIn("CTA Trend Proxy Report", rendered)
        self.assertLess(rendered.index("Summary line 1"), rendered.index("CTA Trend Proxy Report"))

    def test_full_report_prints_estimated_flow_section_when_flow_data_is_provided(self):
        portfolio_result = {
            "signal_details": {
                "ES": {
                    "signal": 1.0,
                    "signal_short": 1.0,
                    "signal_long": 1.0,
                    "price": 100.0,
                    "days_in_position": 3,
                    "reversal_price_short": 99.0,
                    "reversal_price_long": 98.0,
                }
            },
            "weights": {"ES": 0.25},
            "vol_scalars": {"ES": 1.0},
            "sector_exposure": {"Equity Index": 0.25},
            "gross_leverage": 0.25,
            "net_exposure": 0.25,
        }
        universe = {"ES": {"name": "S&P 500", "sector": "Equity Index"}}
        trend_model = mock.Mock()
        trend_model.signal_label.return_value = "LONG"

        output = io.StringIO()
        with redirect_stdout(output):
            print_full_report(
                portfolio_result=portfolio_result,
                universe=universe,
                trend_model=trend_model,
                flips_by_market={"ES": []},
                flow_estimate={
                    "estimation_label": "Model-implied target notional change (not observed flow)",
                    "assumed_cta_aum_usd": 100_000_000_000.0,
                    "top_notional_increase_1d": [
                        {
                            "symbol": "ES",
                            "market": "S&P 500",
                            "delta_weight_1d": 0.03,
                            "estimated_notional_change_usd_1d": 3_000_000_000.0,
                        }
                    ],
                    "top_notional_decrease_1d": [],
                },
            )

        rendered = output.getvalue()
        self.assertIn("MODELED TARGET NOTIONAL CHANGES", rendered)
        self.assertIn("S&P 500", rendered)
        self.assertIn("$3.00B", rendered)

    def test_full_report_prints_capital_state_section_when_capital_data_is_provided(self):
        portfolio_result = {
            "signal_details": {
                "ES": {
                    "signal": 1.0,
                    "signal_short": 1.0,
                    "signal_long": 1.0,
                    "price": 100.0,
                    "days_in_position": 3,
                    "reversal_price_short": 99.0,
                    "reversal_price_long": 98.0,
                }
            },
            "weights": {"ES": 0.25},
            "vol_scalars": {"ES": 1.0},
            "sector_exposure": {"Equity Index": 0.25},
            "gross_leverage": 0.95,
            "net_exposure": 0.35,
        }
        universe = {"ES": {"name": "S&P 500", "sector": "Equity Index"}}
        trend_model = mock.Mock()
        trend_model.signal_label.return_value = "LONG"

        output = io.StringIO()
        with redirect_stdout(output):
            print_full_report(
                portfolio_result=portfolio_result,
                universe=universe,
                trend_model=trend_model,
                flips_by_market={"ES": []},
                capital_estimate={
                    "aum_basis": {
                        "source": "user_assumption",
                        "label": "User CTA AUM assumption",
                        "aum_usd": 100_000_000_000.0,
                    },
                    "estimated_gross_risk_deployed_usd": 95_000_000_000.0,
                    "estimated_net_risk_deployed_usd": 35_000_000_000.0,
                    "estimated_remaining_gross_headroom_usd": 405_000_000_000.0,
                    "note": "This is risk deployed, not cash spent.",
                },
            )

        rendered = output.getvalue()
        self.assertIn("ESTIMATED CTA CAPITAL STATE", rendered)
        self.assertIn("$95.00B", rendered)
        self.assertIn("risk deployed, not cash spent", rendered)

    def test_full_report_prints_tactical_equity_section_when_available(self):
        portfolio_result = {
            "signal_details": {
                "ES": {
                    "signal": 1.0,
                    "signal_short": 1.0,
                    "signal_long": 1.0,
                    "price": 100.0,
                    "days_in_position": 3,
                    "reversal_price_short": 99.0,
                    "reversal_price_long": 98.0,
                }
            },
            "weights": {"ES": 0.25},
            "vol_scalars": {"ES": 1.0},
            "sector_exposure": {"Equity Index": 0.25},
            "gross_leverage": 0.25,
            "net_exposure": 0.25,
        }
        universe = {"ES": {"name": "S&P 500", "sector": "Equity Index"}}
        trend_model = mock.Mock()
        trend_model.signal_label.return_value = "LONG"

        output = io.StringIO()
        with redirect_stdout(output):
            print_full_report(
                portfolio_result=portfolio_result,
                universe=universe,
                trend_model=trend_model,
                flips_by_market={"ES": []},
                tactical_equity={
                    "available": True,
                    "assumed_cta_aum_usd": 100_000_000_000.0,
                    "method_note": "Tactical multi-horizon sleeve.",
                    "markets": {
                        "ES": {
                            "signal_label": "LONG",
                            "target_weight": 0.70,
                            "nearest_horizon": "20d",
                            "nearest_distance_pct": 1.2,
                            "horizon_signals": {"20d": 1.0, "60d": 1.0},
                        }
                    },
                    "scenarios": [
                        {"label": "flat", "total_delta_weight": 0.0, "total_estimated_notional_change_usd": 0.0},
                        {"label": "+2%", "total_delta_weight": 0.02, "total_estimated_notional_change_usd": 2_000_000_000.0},
                    ],
                },
            )

        rendered = output.getvalue()
        self.assertIn("TACTICAL EQUITY CTA SCENARIOS", rendered)
        self.assertIn("Tactical multi-horizon sleeve.", rendered)
        self.assertIn("+2%", rendered)
        self.assertIn("$2.00B", rendered)

    def test_full_report_prints_goldman_benchmark_section_when_available(self):
        portfolio_result = {
            "signal_details": {
                "ES": {
                    "signal": 1.0,
                    "signal_short": 1.0,
                    "signal_long": 1.0,
                    "price": 100.0,
                    "days_in_position": 3,
                    "reversal_price_short": 99.0,
                    "reversal_price_long": 98.0,
                }
            },
            "weights": {"ES": 0.25},
            "vol_scalars": {"ES": 1.0},
            "sector_exposure": {"Equity Index": 0.25},
            "gross_leverage": 0.25,
            "net_exposure": 0.25,
        }
        universe = {"ES": {"name": "S&P 500", "sector": "Equity Index"}}
        trend_model = mock.Mock()
        trend_model.signal_label.return_value = "LONG"

        output = io.StringIO()
        with redirect_stdout(output):
            print_full_report(
                portfolio_result=portfolio_result,
                universe=universe,
                trend_model=trend_model,
                flips_by_market={"ES": []},
                goldman_benchmark={
                    "available": True,
                    "headline": "Goldman benchmark coverage: 3 public notes | position agreement 67%",
                    "notes": [
                        {
                            "published_date": "2026-04-09",
                            "reference_symbol": "ES",
                            "position_comparison": {"agrees": True},
                            "scenario_comparisons": [{"comparable": True}],
                            "threshold_comparison": {"short_term": {}},
                        }
                    ],
                },
            )

        rendered = output.getvalue()
        self.assertIn("GOLDMAN BENCHMARK", rendered)
        self.assertIn("position agreement 67%", rendered)
        self.assertIn("2026-04-09", rendered)

    def test_full_report_prints_goldman_calibration_section_when_available(self):
        portfolio_result = {
            "signal_details": {
                "ES": {
                    "signal": 1.0,
                    "signal_short": 1.0,
                    "signal_long": 1.0,
                    "price": 100.0,
                    "days_in_position": 3,
                    "reversal_price_short": 99.0,
                    "reversal_price_long": 98.0,
                }
            },
            "weights": {"ES": 0.25},
            "vol_scalars": {"ES": 1.0},
            "sector_exposure": {"Equity Index": 0.25},
            "gross_leverage": 0.25,
            "net_exposure": 0.25,
        }
        universe = {"ES": {"name": "S&P 500", "sector": "Equity Index"}}
        trend_model = mock.Mock()
        trend_model.signal_label.return_value = "LONG"

        output = io.StringIO()
        with redirect_stdout(output):
            print_full_report(
                portfolio_result=portfolio_result,
                universe=universe,
                trend_model=trend_model,
                flips_by_market={"ES": []},
                goldman_calibration={
                    "available": True,
                    "headline": "Goldman calibration best fit: fast | score 55.0 | +18% vs baseline",
                    "recommendation": "Calibration materially improved fit, but magnitude error is still too wide for dealer-desk quality.",
                    "top_candidates": [
                        {
                            "label": "fast",
                            "objective_score": 55.0,
                            "position_direction_agreement_rate": 1.0,
                            "scenario_direction_agreement_rate": 1.0,
                            "scenario_mean_abs_error_pct": 62.0,
                            "threshold_mean_abs_gap_pct": 1.5,
                        }
                    ],
                },
            )

        rendered = output.getvalue()
        self.assertIn("GOLDMAN CALIBRATION", rendered)
        self.assertIn("best fit: fast", rendered)
        self.assertIn("dealer-desk quality", rendered)


class MainSummaryCliTests(unittest.TestCase):
    def _configure_main_dependencies(self):
        futures_data = mock.Mock()
        futures_data.fetch_all.return_value = None
        futures_data.prices.return_value = pd.Series(
            [100.0, 101.0],
            index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
        )
        futures_data.returns.return_value = pd.Series(
            [0.0, 0.01],
            index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
        )

        trend_model = mock.Mock()
        trend_model.detect_flips.return_value = []

        portfolio_constructor = mock.Mock()
        portfolio_constructor.build.return_value = {
            "weights": {"ES": 0.25},
            "signals": {"ES": 1.0},
            "signal_details": {
                "ES": {
                    "signal": 1.0,
                    "signal_short": 1.0,
                    "signal_long": 1.0,
                    "price": 101.0,
                    "days_in_position": 3,
                    "reversal_price_short": 99.0,
                    "reversal_price_long": 98.0,
                }
            },
            "vol_scalars": {"ES": 1.0},
            "sector_exposure": {"Equity Index": 0.25},
            "gross_leverage": 0.25,
            "net_exposure": 0.25,
        }
        portfolio_constructor.backtest_returns.return_value = pd.Series(
            [0.01],
            index=pd.to_datetime(["2026-04-15"]),
        )
        portfolio_constructor.historical_components.return_value = {
            "weights": pd.DataFrame(
                {"ES": [0.20, 0.22]},
                index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
            ),
            "signals": pd.DataFrame(
                {"ES": [1.0, 1.0]},
                index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
            ),
            "vol_scalars": pd.DataFrame(
                {"ES": [1.0, 1.0]},
                index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
            ),
            "alloc_budgets": pd.DataFrame(
                {"ES": [0.25, 0.25]},
                index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
            ),
            "cap_factors": pd.Series(
                [1.0, 1.0],
                index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
            ),
        }

        benchmark_data = mock.Mock()
        benchmark_data.etf_returns.return_value = pd.DataFrame(
            {"DBMF": [0.01]},
            index=pd.to_datetime(["2026-04-15"]),
        )
        futures_data.data_context.return_value = {
            "mode": "daily",
            "official_close_date": "2026-04-15",
            "as_of": "2026-04-15",
        }

        signal_validator = mock.Mock()
        signal_validator.validate.return_value = {"coverage": 0, "note": "SG data unavailable"}

        position_validator = mock.Mock()
        position_validator.validate.return_value = {
            "coverage": 0,
            "agreement_rate": None,
            "by_report_type": {},
        }

        return_validator = mock.Mock()
        return_validator.validate.return_value = {
            "summary": "Good",
            "overlap_days": 1,
            "correlations": {},
        }

        flow_estimator = mock.Mock()
        flow_estimator.estimate.return_value = {
            "estimation_label": "Model-implied target notional change (not observed flow)",
            "assumed_cta_aum_usd": 1_000_000.0,
            "markets": {
                "ES": {
                    "delta_weight_1d": 0.03,
                    "estimated_notional_change_usd_1d": 30_000.0,
                }
            },
            "top_notional_increase_1d": [{"symbol": "ES", "estimated_notional_change_usd_1d": 30_000.0}],
            "top_notional_decrease_1d": [],
        }

        capital_estimator = mock.Mock()
        capital_estimator.estimate.return_value = {
            "aum_basis": {
                "source": "user_assumption",
                "label": "User CTA AUM assumption",
                "aum_usd": 1_000_000.0,
            },
            "estimated_gross_risk_deployed_usd": 250_000.0,
            "estimated_net_risk_deployed_usd": 250_000.0,
            "estimated_remaining_gross_headroom_usd": 4_750_000.0,
            "note": "This is risk deployed, not cash spent.",
        }

        return {
            "futures_data": futures_data,
            "trend_model": trend_model,
            "portfolio_constructor": portfolio_constructor,
            "benchmark_data": benchmark_data,
            "signal_validator": signal_validator,
            "position_validator": position_validator,
            "return_validator": return_validator,
            "flow_estimator": flow_estimator,
            "capital_estimator": capital_estimator,
        }

    def test_main_summary_only_markdown_prints_only_summary_content(self):
        deps = self._configure_main_dependencies()
        output = io.StringIO()
        errors = io.StringIO()

        with mock.patch.object(sys, "argv", ["main.py", "--summary-only", "--summary-format", "markdown"]):
            with mock.patch.object(main, "FUTURES_UNIVERSE", {"ES": {"name": "S&P 500", "sector": "Equity Index"}}):
                with mock.patch("main.FuturesData", return_value=deps["futures_data"]):
                    with mock.patch("main.TrendModel", return_value=deps["trend_model"]):
                        with mock.patch("main.PortfolioConstructor", return_value=deps["portfolio_constructor"]):
                            with mock.patch("main.BenchmarkData", return_value=deps["benchmark_data"]):
                                with mock.patch("main.SignalValidator", return_value=deps["signal_validator"]):
                                    with mock.patch("main.PositionValidator", return_value=deps["position_validator"]):
                                        with mock.patch("main.ReturnValidator", return_value=deps["return_validator"]):
                                            with mock.patch(
                                                "main.build_summary_facts",
                                                return_value={"report_date": "2026-04-15"},
                                                create=True,
                                            ) as build_summary_facts:
                                                with mock.patch(
                                                    "main.render_markdown_summary",
                                                    return_value="## Shareable Summary\n- Bullet one",
                                                    create=True,
                                                ) as render_markdown_summary:
                                                    with mock.patch("main.print_full_report") as print_full_report:
                                                        with redirect_stdout(output), redirect_stderr(errors):
                                                            try:
                                                                main.main()
                                                            except SystemExit as exc:
                                                                self.fail(f"main() exited unexpectedly: {exc}")

        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(output.getvalue().strip(), "## Shareable Summary\n- Bullet one")
        build_summary_facts.assert_called_once()
        render_markdown_summary.assert_called_once_with({"report_date": "2026-04-15"})
        print_full_report.assert_not_called()

    def test_main_summary_passes_rendered_terminal_summary_into_full_report(self):
        deps = self._configure_main_dependencies()
        output = io.StringIO()
        errors = io.StringIO()

        with mock.patch.object(sys, "argv", ["main.py", "--summary", "--quick"]):
            with mock.patch.object(main, "FUTURES_UNIVERSE", {"ES": {"name": "S&P 500", "sector": "Equity Index"}}):
                with mock.patch("main.FuturesData", return_value=deps["futures_data"]):
                    with mock.patch("main.TrendModel", return_value=deps["trend_model"]):
                        with mock.patch("main.PortfolioConstructor", return_value=deps["portfolio_constructor"]):
                            with mock.patch("main.SignalValidator", return_value=deps["signal_validator"]):
                                with mock.patch("main.PositionValidator", return_value=deps["position_validator"]):
                                    with mock.patch(
                                        "main.build_summary_facts",
                                        return_value={"report_date": "2026-04-15"},
                                        create=True,
                                    ) as build_summary_facts:
                                        with mock.patch(
                                            "main.render_terminal_summary",
                                            return_value="Terminal summary",
                                            create=True,
                                        ) as render_terminal_summary:
                                            with mock.patch("main.print_full_report") as print_full_report:
                                                with redirect_stdout(output), redirect_stderr(errors):
                                                    try:
                                                        main.main()
                                                    except SystemExit as exc:
                                                        self.fail(f"main() exited unexpectedly: {exc}")

        self.assertEqual(errors.getvalue(), "")
        build_summary_facts.assert_called_once()
        render_terminal_summary.assert_called_once_with({"report_date": "2026-04-15"})
        print_full_report.assert_called_once()
        self.assertEqual(print_full_report.call_args.kwargs["summary_text"], "Terminal summary")

    def test_main_unknown_markets_writes_fatal_error_to_stderr(self):
        output = io.StringIO()
        errors = io.StringIO()

        with mock.patch.object(sys, "argv", ["main.py", "--summary-only", "--markets", "BAD"]):
            with mock.patch.object(main, "FUTURES_UNIVERSE", {"ES": {"name": "S&P 500", "sector": "Equity Index"}}):
                with redirect_stdout(output), redirect_stderr(errors):
                    with self.assertRaises(SystemExit) as raised:
                        main.main()

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("Unknown markets: ['BAD']", errors.getvalue())
        self.assertIn("Available: ['ES']", errors.getvalue())

    def test_main_json_output_includes_flow_estimate_when_assumed_cta_aum_is_provided(self):
        deps = self._configure_main_dependencies()

        output = io.StringIO()
        errors = io.StringIO()

        with mock.patch.object(
            sys,
            "argv",
            ["main.py", "--output", "json", "--quick", "--assumed-cta-aum", "1000000"],
        ):
            with mock.patch.object(main, "FUTURES_UNIVERSE", {"ES": {"name": "S&P 500", "sector": "Equity Index"}}):
                with mock.patch("main.FuturesData", return_value=deps["futures_data"]):
                    with mock.patch("main.TrendModel", return_value=deps["trend_model"]):
                        with mock.patch("main.PortfolioConstructor", return_value=deps["portfolio_constructor"]):
                            with mock.patch("main.SignalValidator", return_value=deps["signal_validator"]):
                                with mock.patch("main.PositionValidator", return_value=deps["position_validator"]):
                                    with mock.patch("main.FlowEstimator", return_value=deps["flow_estimator"], create=True):
                                        with mock.patch("main.CapitalEstimator", return_value=deps["capital_estimator"], create=True):
                                            with redirect_stdout(output), redirect_stderr(errors):
                                                try:
                                                    main.main()
                                                except SystemExit as exc:
                                                    self.fail(f"main() exited unexpectedly: {exc}")

        self.assertEqual(errors.getvalue(), "")
        payload = json.loads(output.getvalue())
        self.assertIn("structured_report", payload)
        raw_facts = payload["structured_report"]["raw_facts"]
        self.assertIn("flow", raw_facts)
        self.assertIn("capital", raw_facts)

    def test_main_summary_only_no_market_data_writes_fatal_error_to_stderr(self):
        futures_data = mock.Mock()
        futures_data.fetch_all.return_value = None
        futures_data.prices.side_effect = ValueError("missing")
        futures_data.returns.side_effect = ValueError("missing")

        output = io.StringIO()
        errors = io.StringIO()

        with mock.patch.object(sys, "argv", ["main.py", "--summary-only"]):
            with mock.patch.object(main, "FUTURES_UNIVERSE", {"ES": {"name": "S&P 500", "sector": "Equity Index"}}):
                with mock.patch("main.FuturesData", return_value=futures_data):
                    with redirect_stdout(output), redirect_stderr(errors):
                        with self.assertRaises(SystemExit) as raised:
                            main.main()

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("ERROR: No market data fetched. Check your internet connection.", errors.getvalue())

    def test_main_live_summary_passes_live_as_of_into_summary_facts(self):
        deps = self._configure_main_dependencies()
        deps["futures_data"].data_context.return_value = {
            "mode": "live",
            "official_close_date": "2026-04-15",
            "as_of": "2026-04-16 13:15",
        }
        output = io.StringIO()
        errors = io.StringIO()

        with mock.patch.object(sys, "argv", ["main.py", "--summary-only", "--summary-format", "markdown", "--live", "--quick"]):
            with mock.patch.object(main, "FUTURES_UNIVERSE", {"ES": {"name": "S&P 500", "sector": "Equity Index"}}):
                with mock.patch("main.FuturesData", return_value=deps["futures_data"]):
                    with mock.patch("main.TrendModel", return_value=deps["trend_model"]):
                        with mock.patch("main.PortfolioConstructor", return_value=deps["portfolio_constructor"]):
                            with mock.patch("main.SignalValidator", return_value=deps["signal_validator"]):
                                with mock.patch("main.PositionValidator", return_value=deps["position_validator"]):
                                    with mock.patch(
                                        "main.build_summary_facts",
                                        return_value={"report_date": "2026-04-16"},
                                        create=True,
                                    ) as build_summary_facts:
                                        with mock.patch(
                                            "main.render_markdown_summary",
                                            return_value="## Shareable Summary\n- Bullet one",
                                            create=True,
                                        ):
                                            with redirect_stdout(output), redirect_stderr(errors):
                                                main.main()

        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(output.getvalue().strip(), "## Shareable Summary\n- Bullet one")
        self.assertEqual(build_summary_facts.call_args.kwargs["as_of"], "2026-04-16 13:15")

    def test_main_profile_daily_note_uses_agent_friendly_defaults(self):
        deps = self._configure_main_dependencies()
        output = io.StringIO()
        errors = io.StringIO()

        with mock.patch.object(sys, "argv", ["main.py", "--profile", "daily_note"]):
            with mock.patch.object(main, "FUTURES_UNIVERSE", {"ES": {"name": "S&P 500", "sector": "Equity Index"}}):
                with mock.patch("main.FuturesData", return_value=deps["futures_data"]) as futures_data_cls:
                    with mock.patch("main.TrendModel", return_value=deps["trend_model"]):
                        with mock.patch("main.PortfolioConstructor", return_value=deps["portfolio_constructor"]):
                            with mock.patch("main.SignalValidator", return_value=deps["signal_validator"]):
                                with mock.patch("main.PositionValidator", return_value=deps["position_validator"]):
                                    with mock.patch(
                                        "main.build_summary_facts",
                                        return_value={"report_date": "2026-04-15"},
                                        create=True,
                                    ):
                                        with mock.patch(
                                            "main.maybe_generate_llm_summary",
                                            return_value="## Profile Summary\n- Bullet one",
                                            create=True,
                                        ) as llm_summary:
                                            with mock.patch("main.print_full_report") as print_full_report:
                                                with redirect_stdout(output), redirect_stderr(errors):
                                                    main.main()

        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(output.getvalue().strip(), "## Profile Summary\n- Bullet one")
        futures_data_cls.assert_called_once_with(
            universe={"ES": {"name": "S&P 500", "sector": "Equity Index"}},
            refresh=True,
        )
        deps["futures_data"].prices.assert_any_call("ES", live=True)
        llm_summary.assert_called_once_with(
            {"report_date": "2026-04-15"},
            use_llm=True,
            output_format="markdown",
        )
        print_full_report.assert_not_called()

    def test_main_output_json_prints_machine_readable_payload(self):
        deps = self._configure_main_dependencies()
        output = io.StringIO()
        errors = io.StringIO()

        with mock.patch.object(sys, "argv", ["main.py", "--profile", "daily_note", "--output", "json"]):
            with mock.patch.object(main, "FUTURES_UNIVERSE", {"ES": {"name": "S&P 500", "sector": "Equity Index"}}):
                with mock.patch("main.FuturesData", return_value=deps["futures_data"]):
                    with mock.patch("main.TrendModel", return_value=deps["trend_model"]):
                        with mock.patch("main.PortfolioConstructor", return_value=deps["portfolio_constructor"]):
                            with mock.patch("main.SignalValidator", return_value=deps["signal_validator"]):
                                with mock.patch("main.PositionValidator", return_value=deps["position_validator"]):
                                    with mock.patch(
                                        "main.build_summary_facts",
                                        return_value={"report_date": "2026-04-15", "position_counts": {"long": 1, "short": 0, "flat": 0}},
                                        create=True,
                                    ):
                                        with mock.patch(
                                            "main.maybe_generate_llm_summary",
                                            return_value="## Profile Summary\n- Bullet one",
                                            create=True,
                                        ):
                                            with redirect_stdout(output), redirect_stderr(errors):
                                                main.main()

        payload = json.loads(output.getvalue())
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(payload["profile"], "daily_note")
        self.assertEqual(payload["summary_format"], "markdown")
        self.assertEqual(payload["summary_text"], "## Profile Summary\n- Bullet one")
        self.assertIn("structured_report", payload)
        raw_facts = payload["structured_report"]["raw_facts"]
        self.assertEqual(raw_facts["report_date"], "2026-04-15")
