import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import pandas as pd
import requests

from llm import (
    DEFAULT_GEMINI_MODEL,
    GeminiRequestError,
    build_gemini_request_payload,
    generate_gemini_summary,
    load_gemini_config,
)
from schema import build_structured_report
from summary import (
    build_summary_facts,
    maybe_generate_llm_summary,
    render_markdown_summary,
    render_terminal_summary,
)


class SummaryFactBuilderRegressionTests(unittest.TestCase):
    def setUp(self):
        self.universe = {
            "ES": {"name": "S&P 500", "sector": "Equity Index"},
            "CL": {"name": "WTI Crude", "sector": "Energy"},
            "GC": {"name": "Gold", "sector": "Metals"},
            "6E": {"name": "Euro FX", "sector": "FX"},
        }
        self.portfolio_result = {
            "weights": {"ES": 0.32, "CL": 0.18, "GC": -0.29, "6E": 0.0},
            "signals": {"ES": 1.0, "CL": 1.0, "GC": -1.0, "6E": 0.0},
            "signal_details": {
                "ES": {
                    "signal": 1.0,
                    "signal_short": 1.0,
                    "signal_long": 1.0,
                    "price": 5100.0,
                    "days_in_position": 18,
                    "reversal_price_short": 5000.0,
                    "reversal_price_long": 4950.0,
                },
                "CL": {
                    "signal": 1.0,
                    "signal_short": 1.0,
                    "signal_long": 1.0,
                    "price": 80.0,
                    "days_in_position": 7,
                    "reversal_price_short": 79.2,
                    "reversal_price_long": 78.5,
                },
                "GC": {
                    "signal": -1.0,
                    "signal_short": -1.0,
                    "signal_long": -1.0,
                    "price": 2300.0,
                    "days_in_position": 12,
                    "reversal_price_short": 2310.0,
                    "reversal_price_long": 2320.0,
                },
                "6E": {
                    "signal": 0.0,
                    "signal_short": -1.0,
                    "signal_long": 1.0,
                    "price": 1.08,
                    "days_in_position": 2,
                    "reversal_price_short": 1.079,
                    "reversal_price_long": 1.081,
                },
            },
            "sector_exposure": {
                "Equity Index": 0.32,
                "Energy": 0.18,
                "Metals": -0.29,
                "FX": 0.0,
            },
            "gross_leverage": 0.79,
            "net_exposure": 0.21,
        }
        self.flips_by_market = {
            "ES": [],
            "CL": [
                {
                    "date": datetime(2026, 4, 14),
                    "from_label": "SHORT",
                    "to_label": "LONG",
                    "price": 79.5,
                }
            ],
            "GC": [],
            "6E": [],
        }

    def _build_facts(self):
        return build_summary_facts(
            portfolio_result=self.portfolio_result,
            universe=self.universe,
            flips_by_market=self.flips_by_market,
            flow_estimate={
                "estimation_label": "Model-implied target notional change (not observed flow)",
                "assumed_cta_aum_usd": 100_000_000_000.0,
                "markets": {
                    "ES": {
                        "symbol": "ES",
                        "market": "S&P 500",
                        "sector": "Equity Index",
                        "delta_weight_1d": 0.03,
                        "delta_weight_5d": 0.07,
                        "estimated_notional_change_usd_1d": 3_000_000_000.0,
                        "estimated_notional_change_usd_5d": 7_000_000_000.0,
                        "decomposition_5d": {
                            "signal_effect": 0.05,
                            "vol_target_effect": 0.01,
                            "allocation_effect": 0.005,
                            "leverage_cap_effect": 0.005,
                            "total": 0.07,
                            "flow_type": "short_cover_to_long",
                        },
                    }
                },
                "top_notional_increase_1d": [
                    {
                        "symbol": "ES",
                        "market": "S&P 500",
                        "delta_weight_1d": 0.03,
                        "estimated_notional_change_usd_1d": 3_000_000_000.0,
                    }
                ],
                "top_notional_decrease_1d": [],
                "aggregate_decomposition_5d": {
                    "signal_effect_weight": 0.05,
                    "vol_target_effect_weight": 0.01,
                    "allocation_effect_weight": 0.005,
                    "leverage_cap_effect_weight": 0.005,
                    "signal_effect_usd": 5_000_000_000.0,
                    "vol_target_effect_usd": 1_000_000_000.0,
                    "allocation_effect_usd": 500_000_000.0,
                    "leverage_cap_effect_usd": 500_000_000.0,
                    "flow_type_counts": {
                        "short_cover_to_long": 1,
                    },
                },
            },
            data_context={
                "mode": "live",
                "official_close_date": "2026-04-15",
                "live_as_of": "2026-04-16T08:45:00-07:00",
            },
            capital_estimate={
                "aum_basis": {
                    "source": "user_assumption",
                    "label": "User CTA AUM assumption",
                    "aum_usd": 100_000_000_000.0,
                },
                "gross_risk_deployed_pct_of_aum": 0.79,
                "net_risk_deployed_pct_of_aum": 0.21,
                "remaining_gross_headroom_pct_of_aum": 4.21,
                "estimated_gross_risk_deployed_usd": 79_000_000_000.0,
                "estimated_net_risk_deployed_usd": 21_000_000_000.0,
                "estimated_remaining_gross_headroom_usd": 421_000_000_000.0,
                "note": "This is risk deployed, not cash spent.",
            },
        )

    def test_build_summary_facts_counts_position_buckets(self):
        facts = self._build_facts()

        self.assertEqual(
            facts["position_counts"],
            {"long": 2, "short": 1, "flat": 1},
        )

    def test_build_summary_facts_ranks_strongest_convictions_by_absolute_weight(self):
        facts = self._build_facts()

        strongest = facts["strongest_convictions"][:3]

        self.assertEqual(
            [item["symbol"] for item in strongest],
            ["ES", "GC", "CL"],
        )
        self.assertEqual(
            [round(abs(item["weight"]), 2) for item in strongest],
            [0.32, 0.29, 0.18],
        )

    def test_build_summary_facts_orders_flip_risks_by_nearest_absolute_reversal_distance(self):
        facts = self._build_facts()

        nearest = facts["nearest_flip_risks"][:4]

        self.assertEqual(
            [item["symbol"] for item in nearest],
            ["6E", "GC", "CL", "ES"],
        )
        self.assertEqual(
            [round(item["distance_pct"], 2) for item in nearest],
            [0.09, 0.43, 1.0, 1.96],
        )

    def test_build_summary_facts_derives_report_date_from_latest_explicit_input_date_when_as_of_omitted(self):
        etf_returns = pd.DataFrame(
            {"DBMF": [0.01, -0.02]},
            index=pd.to_datetime(["2026-04-09", "2026-04-10"]),
        )
        flips_by_market = {
            "ES": [],
            "CL": [],
            "GC": [
                {
                    "date": datetime(2026, 4, 12),
                    "from_label": "LONG",
                    "to_label": "SHORT",
                    "price": 2295.0,
                }
            ],
            "6E": [],
        }

        facts = build_summary_facts(
            portfolio_result=self.portfolio_result,
            universe=self.universe,
            flips_by_market=flips_by_market,
            etf_returns_df=etf_returns,
        )

        self.assertEqual(facts["report_date"], "2026-04-12")

    def test_build_summary_facts_sorts_undated_flips_after_dated_flips(self):
        flips_by_market = {
            "ES": [
                {
                    "date": datetime(2026, 4, 12),
                    "from_label": "LONG",
                    "to_label": "SHORT",
                    "price": 5060.0,
                }
            ],
            "CL": [
                {
                    "date": datetime(2026, 4, 14),
                    "from_label": "SHORT",
                    "to_label": "LONG",
                    "price": 79.5,
                }
            ],
            "GC": [
                {
                    "date": None,
                    "from_label": "LONG",
                    "to_label": "SHORT",
                    "price": 2290.0,
                }
            ],
            "6E": [],
        }

        facts = build_summary_facts(
            portfolio_result=self.portfolio_result,
            universe=self.universe,
            flips_by_market=flips_by_market,
        )

        self.assertEqual(
            [item["symbol"] for item in facts["recent_flips"]],
            ["CL", "ES", "GC"],
        )
        self.assertIsNone(facts["recent_flips"][-1]["date"])

    def test_build_summary_facts_uses_single_benchmark_etf_payload_field_name(self):
        etf_returns = pd.DataFrame(
            {"DBMF": [0.01, -0.02]},
            index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
        )

        facts = build_summary_facts(
            portfolio_result=self.portfolio_result,
            universe=self.universe,
            flips_by_market=self.flips_by_market,
            etf_returns_df=etf_returns,
        )

        self.assertIn("benchmark_etfs", facts)
        self.assertNotIn("etf_snapshot", facts)

    def test_build_summary_facts_adds_caveat_when_sg_signal_validation_is_not_provided(self):
        facts = build_summary_facts(
            portfolio_result=self.portfolio_result,
            universe=self.universe,
            flips_by_market=self.flips_by_market,
        )

        self.assertTrue(
            any(
                "SG signal validation" in caveat and "not provided" in caveat
                for caveat in facts["validation"]["caveats"]
            )
        )

    def test_build_summary_facts_includes_data_method_conclusion_suggestions_and_flow_sections(self):
        facts = self._build_facts()

        self.assertIn("data_used", facts)
        self.assertIn("calculation_method", facts)
        self.assertIn("conclusion", facts)
        self.assertIn("suggestions", facts)
        self.assertIn("flow", facts)
        self.assertIn("capital", facts)
        self.assertIn("thesis", facts)
        self.assertIn("drivers", facts)
        self.assertIn("interpretation", facts)
        self.assertIn("why_now", facts)
        self.assertIn("confidence", facts)
        self.assertIn("actions", facts)
        self.assertIn("investment_overview", facts)
        self.assertIn("live", facts["data_used"]["price_mode"].lower())
        self.assertIn("weight", facts["calculation_method"]["flow"])
        self.assertIn("Driver decomposition", facts["calculation_method"]["flow"])
        self.assertIn("Model-implied", facts["flow"]["estimation_label"])
        self.assertEqual(facts["capital"]["aum_basis"]["source"], "user_assumption")
        self.assertIn("aggregate_decomposition_5d", facts["drivers"])
        self.assertEqual(
            facts["drivers"]["aggregate_decomposition_5d"]["flow_type_counts"]["short_cover_to_long"],
            1,
        )
        self.assertGreaterEqual(len(facts["suggestions"]), 1)

    def test_investment_overview_snapshot_contains_aum_and_deployment(self):
        facts = self._build_facts()
        overview = facts["investment_overview"]

        self.assertEqual(overview["aum_usd"], 100_000_000_000.0)
        self.assertEqual(overview["aum_basis_label"], "User CTA AUM assumption")
        self.assertAlmostEqual(overview["gross_deployed_pct"], 0.79)
        self.assertAlmostEqual(overview["net_deployed_pct"], 0.21)
        self.assertEqual(overview["gross_deployed_usd"], 79_000_000_000.0)
        self.assertEqual(overview["remaining_headroom_usd"], 421_000_000_000.0)

    def test_investment_overview_snapshot_contains_market_flows(self):
        facts = self._build_facts()
        overview = facts["investment_overview"]

        self.assertIn("all_market_flows", overview)
        self.assertIsInstance(overview["all_market_flows"], list)
        symbols = [f["symbol"] for f in overview["all_market_flows"]]
        self.assertIn("ES", symbols)
        es = next(item for item in overview["all_market_flows"] if item["symbol"] == "ES")
        self.assertEqual(es["decomposition_5d"]["flow_type"], "short_cover_to_long")
        self.assertIn("aggregate_decomposition_5d", overview)
        self.assertAlmostEqual(overview["aggregate_decomposition_5d"]["signal_effect_weight"], 0.05)

    def test_build_summary_facts_carries_tactical_equity_snapshot(self):
        facts = build_summary_facts(
            portfolio_result=self.portfolio_result,
            universe=self.universe,
            flips_by_market=self.flips_by_market,
            tactical_equity={
                "available": True,
                "scenario_reference": {
                    "flat": {"label": "flat", "total_estimated_notional_change_usd": 0.0, "total_delta_weight": 0.0},
                    "up_2pct": {"label": "+2%", "total_estimated_notional_change_usd": 1_500_000_000.0, "total_delta_weight": 0.015},
                    "down_2pct": {"label": "-2%", "total_estimated_notional_change_usd": -2_200_000_000.0, "total_delta_weight": -0.022},
                },
            },
        )

        self.assertTrue(facts["tactical_equity"]["available"])
        self.assertIn("tactical_equity", facts["drivers"])
        self.assertIn("Tactical ES/NQ sleeve", facts["conclusion"]["details"][0] + " ".join(facts["conclusion"]["details"]))

    def test_build_summary_facts_carries_goldman_calibration_snapshot(self):
        facts = build_summary_facts(
            portfolio_result=self.portfolio_result,
            universe=self.universe,
            flips_by_market=self.flips_by_market,
            goldman_calibration={
                "available": True,
                "headline": "Goldman calibration best fit: fast | score 50.0",
                "recommendation": "Calibration materially improved fit, but magnitude error is still too wide for dealer-desk quality.",
            },
        )

        self.assertTrue(facts["goldman_calibration"]["available"])
        self.assertIn("goldman_calibration", facts["drivers"])
        self.assertIn("Goldman calibration best fit", " ".join(facts["conclusion"]["details"]))


class SummaryRenderingRegressionTests(unittest.TestCase):
    def setUp(self):
        self.facts = {
            "report_date": "2026-04-15",
            "scope": {"selected_market_count": 4, "universe_market_count": 21},
            "position_counts": {"long": 2, "short": 1, "flat": 1},
            "crowding": {
                "classification": "MODERATE",
                "crowded_longs": [
                    {"symbol": "ES", "market": "S&P 500"},
                    {"symbol": "CL", "market": "WTI Crude"},
                ],
                "crowded_shorts": [
                    {"symbol": "GC", "market": "Gold"},
                ],
            },
            "strongest_convictions": [
                {
                    "symbol": "ES",
                    "market": "S&P 500",
                    "direction": "LONG",
                    "weight": 0.32,
                },
                {
                    "symbol": "GC",
                    "market": "Gold",
                    "direction": "SHORT",
                    "weight": -0.29,
                },
            ],
            "recent_flips": [
                {
                    "symbol": "CL",
                    "market": "WTI Crude",
                    "date": "2026-04-14",
                    "from_label": "SHORT",
                    "to_label": "LONG",
                }
            ],
            "nearest_flip_risks": [
                {
                    "symbol": "6E",
                    "market": "Euro FX",
                    "distance_pct": 0.09,
                    "direction": "FLAT",
                },
            ],
            "validation": {
                "caveats": ["SG Trend Indicator data not available (stub)."],
            },
            "data_used": {
                "price_mode": "Live nowcast using the latest intraday price over the April 15, 2026 official close.",
                "market_scope": "4 selected markets",
                "validation_inputs": "COT direction and benchmark ETF return checks.",
            },
            "calculation_method": {
                "signals": "20d/120d trend proxy with vol targeting and equal-risk sectors.",
                "flow": "Estimated CTA proxy flow uses current target weight minus 1d and 5d prior weights; dollars require an explicit CTA AUM assumption.",
            },
            "conclusion": {
                "headline": "The tracked subset remains net long with moderate crowding and a nearby FX flip risk.",
            },
            "suggestions": [
                "Watch Euro FX closely because it is near a signal change.",
                "Treat SG confirmation as unavailable until the scraper is implemented.",
            ],
            "flow": {
                "estimation_label": "Model-implied target notional change (not observed flow)",
                "assumed_cta_aum_usd": 100000000000.0,
                "top_notional_increase_1d": [
                    {"symbol": "ES", "market": "S&P 500", "estimated_notional_change_usd_1d": 3000000000.0}
                ],
                "top_notional_increase_5d": [
                    {"symbol": "ES", "market": "S&P 500", "estimated_notional_change_usd_5d": 7000000000.0, "delta_weight_5d": 0.07}
                ],
                "top_notional_decrease_5d": [],
                "aggregate_decomposition_5d": {
                    "signal_effect_usd": 5000000000.0,
                    "vol_target_effect_usd": 1000000000.0,
                    "allocation_effect_usd": 500000000.0,
                    "leverage_cap_effect_usd": 500000000.0,
                    "flow_type_counts": {"short_cover_to_long": 1},
                },
            },
            "capital": {
                "aum_basis": {
                    "source": "user_assumption",
                    "label": "User CTA AUM assumption",
                    "aum_usd": 100000000000.0,
                },
                "gross_risk_deployed_pct_of_aum": 0.79,
                "net_risk_deployed_pct_of_aum": 0.21,
                "remaining_gross_headroom_pct_of_aum": 4.21,
                "estimated_gross_risk_deployed_usd": 79000000000.0,
                "estimated_net_risk_deployed_usd": 21000000000.0,
                "estimated_remaining_gross_headroom_usd": 421000000000.0,
            },
            "investment_overview": {
                "aum_basis_label": "User CTA AUM assumption",
                "aum_usd": 100000000000.0,
                "gross_deployed_pct": 0.79,
                "gross_deployed_usd": 79000000000.0,
                "net_deployed_pct": 0.21,
                "net_deployed_usd": 21000000000.0,
                "remaining_headroom_pct": 4.21,
                "remaining_headroom_usd": 421000000000.0,
                "all_market_flows": [],
                "sector_flows_5d": {},
            },
        }

    def test_render_terminal_summary_returns_multiline_prose_from_facts(self):
        output = render_terminal_summary(self.facts)

        lines = [line for line in output.strip().splitlines() if line.strip()]

        self.assertGreaterEqual(len(lines), 4)
        self.assertLessEqual(len(lines), 6)
        self.assertIn("2 long", output)
        self.assertIn("1 short", output)
        self.assertIn("1 flat", output)
        self.assertIn("MODERATE", output)
        self.assertIn("S&P 500", output)
        self.assertIn("Euro FX", output)
        self.assertIn("SG Trend Indicator data not available", output)
        self.assertNotEqual(output, "summary pending")

    def test_render_terminal_summary_surfaces_recent_flips_and_crowding_concentration(self):
        output = render_terminal_summary(self.facts)

        self.assertIn("WTI Crude", output)
        self.assertIn("SHORT", output)
        self.assertIn("LONG", output)
        self.assertIn("Gold", output)

    def test_render_terminal_summary_avoids_reversal_wording_for_flat_markets(self):
        output = render_terminal_summary(self.facts)

        self.assertIn("Euro FX", output)
        self.assertIn("signal change", output)
        self.assertNotIn("Euro FX is 0.09% from reversal", output)

    def test_render_markdown_summary_returns_headline_and_multiple_bullets_from_facts(self):
        output = render_markdown_summary(self.facts)

        lines = [line for line in output.strip().splitlines() if line.strip()]
        bullet_lines = [line for line in lines if line.startswith("- ")]

        self.assertTrue(lines[0].startswith("## "))
        self.assertIn("4", lines[0])
        self.assertGreaterEqual(len(bullet_lines), 3)
        self.assertTrue(any("MODERATE" in line for line in bullet_lines))
        self.assertTrue(any("S&P 500" in line for line in bullet_lines))
        self.assertTrue(any("Euro FX" in line for line in bullet_lines))
        self.assertTrue(any("SG Trend Indicator data not available" in line for line in bullet_lines))
        self.assertIn("**AUM Basis:**", output)
        self.assertIn("**Deployed:**", output)
        self.assertNotEqual(output, "markdown pending")

    def test_render_markdown_summary_surfaces_recent_flips_and_crowding_concentration(self):
        output = render_markdown_summary(self.facts)

        self.assertIn("WTI Crude", output)
        self.assertIn("Gold", output)
        self.assertIn("SHORT", output)
        self.assertIn("LONG", output)

    def test_render_markdown_summary_avoids_reversal_wording_for_flat_markets(self):
        output = render_markdown_summary(self.facts)

        self.assertIn("Euro FX", output)
        self.assertIn("signal change", output)
        self.assertNotIn("Euro FX is 0.09% from reversal", output)

    def test_render_markdown_summary_explains_data_method_conclusion_and_suggestions(self):
        output = render_markdown_summary(self.facts)

        self.assertIn("Data:", output)
        self.assertIn("Method:", output)
        self.assertIn("Conclusion:", output)
        self.assertIn("Suggestions:", output)
        self.assertIn("notional", output.lower())
        self.assertIn("CTA AUM assumption", output)
        self.assertIn("driver split", output.lower())

    def test_render_terminal_summary_mentions_data_method_capital_and_suggestion_context(self):
        output = render_terminal_summary(self.facts)

        self.assertIn("Data:", output)
        self.assertIn("Method:", output)
        self.assertIn("Capital:", output)
        self.assertIn("Conclusion:", output)
        self.assertIn("Suggestion:", output)
        self.assertIn("driver split", output.lower())


class StructuredReportFlowSchemaTests(unittest.TestCase):
    def test_structured_report_surfaces_flow_driver_decomposition(self):
        facts = SummaryFactBuilderRegressionTests()
        facts.setUp()
        built = facts._build_facts()

        report = build_structured_report(built)

        self.assertIn("flow_summary", report)
        self.assertIn("tactical_equity_flow", report)
        self.assertIn("goldman_calibration", report)
        self.assertAlmostEqual(
            report["flow_summary"]["aggregate_decomposition_5d"]["signal_effect_weight"],
            0.05,
        )
        self.assertEqual(
            report["flow_summary"]["aggregate_decomposition_5d"]["flow_type_counts"]["short_cover_to_long"],
            1,
        )
        self.assertEqual(report["market_table"][0]["flow_type_5d"], "short_cover_to_long")
        self.assertIn("driver_decomposition_5d", report["market_table"][0])


class SummaryLlmFallbackRegressionTests(unittest.TestCase):
    def test_gemini_summary_falls_back_to_the_deterministic_terminal_renderer_when_config_missing(self):
        facts = {"position_counts": {"long": 2, "short": 1, "flat": 1}}

        with tempfile.TemporaryDirectory() as temp_dir:
            missing_env_path = Path(temp_dir) / ".env"

            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("llm._repo_env_path", return_value=missing_env_path):
                    with mock.patch(
                        "summary.render_terminal_summary",
                        return_value="DETERMINISTIC TERMINAL SUMMARY",
                    ) as render_terminal:
                        output = maybe_generate_llm_summary(
                            facts,
                            use_llm=True,
                            output_format="terminal",
                        )

        render_terminal.assert_called_once_with(facts)
        self.assertEqual(output, "DETERMINISTIC TERMINAL SUMMARY")

    def test_gemini_summary_falls_back_to_the_deterministic_markdown_renderer_when_provider_errors(self):
        facts = {"position_counts": {"long": 2, "short": 1, "flat": 1}}

        with mock.patch(
            "summary.generate_gemini_summary",
            side_effect=GeminiRequestError("provider error"),
        ):
            with mock.patch(
                "summary.render_markdown_summary",
                return_value="DETERMINISTIC MARKDOWN SUMMARY",
            ) as render_markdown:
                output = maybe_generate_llm_summary(
                    facts,
                    use_llm=True,
                    output_format="markdown",
                )

        render_markdown.assert_called_once_with(facts)
        self.assertEqual(output, "DETERMINISTIC MARKDOWN SUMMARY")

    def test_generate_gemini_summary_uses_env_configured_model(self):
        facts = {"position_counts": {"long": 2, "short": 1, "flat": 1}}
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Gemini summary output"},
                        ]
                    }
                }
            ]
        }

        with mock.patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-test-model"},
            clear=True,
        ):
            with mock.patch("llm.requests.post", return_value=response) as post:
                output = generate_gemini_summary(facts, output_format="markdown")

        self.assertEqual(output, "Gemini summary output")
        post.assert_called_once()
        self.assertEqual(
            post.call_args.args[0],
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-test-model:generateContent",
        )
        self.assertNotIn("params", post.call_args.kwargs)
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "test-key")
        self.assertEqual(
            post.call_args.kwargs["json"]["generationConfig"]["maxOutputTokens"],
            3072,
        )

    def test_generate_gemini_summary_uses_default_model_when_env_override_is_missing(self):
        facts = {"position_counts": {"long": 2, "short": 1, "flat": 1}}
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Gemini summary output"},
                        ]
                    }
                }
            ]
        }

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            with mock.patch("llm.requests.post", return_value=response) as post:
                generate_gemini_summary(facts, output_format="terminal")

        self.assertEqual(
            post.call_args.args[0],
            f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_GEMINI_MODEL}:generateContent",
        )

    def test_load_gemini_config_reads_repo_env_file_when_process_env_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "GEMINI_API_KEY=test-env-key\nGEMINI_MODEL=gemini-from-env-file\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("llm._repo_env_path", return_value=env_path):
                    config = load_gemini_config()

        self.assertEqual(config["api_key"], "test-env-key")
        self.assertEqual(config["model"], "gemini-from-env-file")

    def test_load_gemini_config_prefers_process_environment_over_repo_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "GEMINI_API_KEY=file-key\nGEMINI_MODEL=file-model\n",
                encoding="utf-8",
            )

            with mock.patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "process-key", "GEMINI_MODEL": "process-model"},
                clear=True,
            ):
                with mock.patch("llm._repo_env_path", return_value=env_path):
                    config = load_gemini_config()

        self.assertEqual(config["api_key"], "process-key")
        self.assertEqual(config["model"], "process-model")

    def test_generate_gemini_summary_wraps_request_timeouts_in_gemini_request_error(self):
        facts = {"position_counts": {"long": 2, "short": 1, "flat": 1}}

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            with mock.patch(
                "llm.requests.post",
                side_effect=requests.exceptions.ReadTimeout("timed out"),
            ):
                with self.assertRaises(GeminiRequestError):
                    generate_gemini_summary(facts, output_format="markdown")

    def test_gemini_markdown_without_subsections_falls_back_to_deterministic_markdown(self):
        facts = {"position_counts": {"long": 2, "short": 1, "flat": 1}}

        with mock.patch(
            "summary.generate_gemini_summary",
            return_value="**CTA Positioning Update: High Crowding Across Long-Only Portfolio**",
        ):
            with mock.patch(
                "summary.render_markdown_summary",
                return_value="## Deterministic Summary\n- Bullet one",
            ) as render_markdown:
                output = maybe_generate_llm_summary(
                    facts,
                    use_llm=True,
                    output_format="markdown",
                )

        render_markdown.assert_called_once_with(facts)
        self.assertEqual(output, "## Deterministic Summary\n- Bullet one")

    def test_valid_professional_markdown_note_is_accepted(self):
        facts = {"position_counts": {"long": 2, "short": 1, "flat": 1}}
        note = (
            "## CTA Daily Note — 2026-04-16\n\n"
            "CTAs remain net long across the tracked subset with high crowding. "
            "Euro FX is the key risk, sitting just 0.76% from reversal.\n\n"
            "### Investment Overview\n"
            "- **AUM Basis:** $112.8B (SG Trend Index tracked-fund basket)\n"
            "- **Risk Deployed:** $95.2B gross (0.95x) / $21.0B net (0.21x)\n"
            "- **Remaining Headroom:** $405.0B (4.05x)\n\n"
            "### Positioning Snapshot\n"
            "The model is 3 long, 1 short, and 0 flat. Crowding is HIGH.\n\n"
            "### Flow Activity (5-Day)\n"
            "- **Top Buyers:** Euro FX (+$53.9B est.)\n"
            "- **Top Sellers:** Crude Oil (-$384M est.)\n"
            "- **Sector Rotation:** Net buying in FX\n\n"
            "### Key Risks\n"
            "- Euro FX is 0.76% from reversal\n"
            "- HIGH crowding (4/4 at max signal)\n"
            "- SG signal validation unavailable\n\n"
            "### Assumptions & Caveats\n"
            "- CTA AUM assumption: $112.8B\n"
            "- Data mode: live nowcast\n"
        )

        with mock.patch(
            "summary.load_gemini_config",
            return_value={"model": "gemini-3-pro-preview", "fallback_model": "gemini-2.5-flash"},
        ):
            with mock.patch("summary.generate_gemini_summary", return_value=note):
                output = maybe_generate_llm_summary(
                    facts,
                    use_llm=True,
                    output_format="markdown",
                )

        self.assertEqual(output, note.strip())

    def test_valid_professional_markdown_note_with_bold_headline_is_accepted(self):
        facts = {"position_counts": {"long": 2, "short": 1, "flat": 1}}
        note = (
            "## CTA Daily Note — 2026-04-16\n\n"
            "CTA positioning is 4 long, 0 short, and 0 flat with high crowding.\n\n"
            "### Investment Overview\n"
            "- **AUM Basis:** $100B\n"
            "- **Risk Deployed:** $95.2B gross\n"
            "- **Remaining Headroom:** $404.8B\n\n"
            "### Positioning Snapshot\n"
            "All markets are at max signal with high crowding.\n\n"
            "### Flow Activity (5-Day)\n"
            "- **Top Buyers:** Euro FX (+$53.9B)\n"
            "- **Top Sellers:** Crude Oil (-$384M)\n\n"
            "### Key Risks\n"
            "- Euro FX is close to reversal\n"
            "- Crowding is elevated\n\n"
            "### Assumptions & Caveats\n"
            "- SG validation unavailable\n"
        )

        with mock.patch(
            "summary.load_gemini_config",
            return_value={"model": "gemini-3-pro-preview", "fallback_model": "gemini-2.5-flash"},
        ):
            with mock.patch("summary.generate_gemini_summary", return_value=note):
                output = maybe_generate_llm_summary(
                    facts,
                    use_llm=True,
                    output_format="markdown",
                )

        self.assertEqual(output, note.strip())

    def test_invalid_primary_markdown_note_retries_with_fallback_model(self):
        facts = {"position_counts": {"long": 2, "short": 1, "flat": 1}}
        valid_note = (
            "## CTA Daily Note — 2026-04-16\n\n"
            "CTAs remain net long with high crowding.\n\n"
            "### Investment Overview\n"
            "- **AUM Basis:** $112.8B\n\n"
            "### Positioning Snapshot\n"
            "3 long, 1 short.\n\n"
            "### Flow Activity (5-Day)\n"
            "- **Top Buyers:** Euro FX\n\n"
            "### Key Risks\n"
            "- Euro FX near reversal\n\n"
            "### Assumptions & Caveats\n"
            "- SG validation unavailable\n"
        )

        with mock.patch(
            "summary.load_gemini_config",
            return_value={"model": "gemini-3-pro-preview", "fallback_model": "gemini-2.5-flash"},
        ):
            with mock.patch(
                "summary.generate_gemini_summary",
                side_effect=["**Positioning is crowded", valid_note],
            ) as generate:
                output = maybe_generate_llm_summary(
                    facts,
                    use_llm=True,
                    output_format="markdown",
                )

        self.assertEqual(output, valid_note.strip())
        self.assertEqual(generate.call_args_list[0].kwargs["model_override"], None)
        self.assertEqual(generate.call_args_list[1].kwargs["model_override"], "gemini-2.5-flash")

    def test_build_gemini_request_payload_requires_professional_note_structure(self):
        payload = build_gemini_request_payload(
            {
                "data_used": {"price_mode": "daily"},
                "calculation_method": {"flow": "weight delta"},
                "conclusion": {"headline": "net long"},
                "suggestions": ["watch flips"],
            },
            output_format="markdown",
        )

        prompt_text = payload["contents"][0]["parts"][0]["text"]
        self.assertIn("what the data means", prompt_text)
        self.assertIn("why it matters now", prompt_text)
        self.assertIn("professional daily CTA note", prompt_text)
        self.assertIn("Do not invent", prompt_text)
        self.assertIn("### Investment Overview", prompt_text)
        self.assertIn("### Positioning Snapshot", prompt_text)
        self.assertIn("### Flow Activity", prompt_text)
        self.assertIn("### Key Risks", prompt_text)
        self.assertIn("### Assumptions", prompt_text)
        self.assertEqual(
            payload["generationConfig"]["thinkingConfig"]["thinkingLevel"],
            "LOW",
        )

    def test_build_gemini_request_payload_compacts_large_fact_payloads_for_markdown(self):
        large_facts = {
            "report_date": "2026-04-16",
            "scope": {"selected_market_count": 21, "universe_market_count": 21},
            "position_counts": {"long": 11, "short": 3, "flat": 7},
            "data_used": {"price_mode": "live"},
            "calculation_method": {"flow": "weight delta"},
            "conclusion": {"headline": "crowded long regime"},
            "suggestions": ["watch euro fx", "respect crowding", "treat validation cautiously"],
            "thesis": "Trend remains net long but crowded.",
            "interpretation": "Signals still favor long exposure, though reversal risk is building.",
            "why_now": "Several markets sit close to reversal thresholds.",
            "confidence": {"label": "mixed"},
            "strongest_convictions": [
                {
                    "symbol": f"S{i}",
                    "market": f"Market {i}",
                    "direction": "LONG",
                    "weight": 0.10,
                    "days_in_position": 5 + i,
                }
                for i in range(30)
            ],
            "recent_flips": [
                {
                    "symbol": f"F{i}",
                    "market": f"Flip Market {i}",
                    "date": "2026-04-16",
                    "from_label": "FLAT",
                    "to_label": "LONG",
                    "price": 100.0 + i,
                }
                for i in range(30)
            ],
            "nearest_flip_risks": [
                {
                    "symbol": f"R{i}",
                    "market": f"Risk Market {i}",
                    "distance_pct": 0.5 + i / 100,
                }
                for i in range(30)
            ],
            "flow": {
                "top_notional_increase_5d": [
                    {"symbol": f"B{i}", "market": f"Increase {i}", "estimated_notional_change_usd_5d": 1_000_000_000.0}
                    for i in range(20)
                ],
                "top_notional_decrease_5d": [
                    {"symbol": f"L{i}", "market": f"Decrease {i}", "estimated_notional_change_usd_5d": -500_000_000.0}
                    for i in range(20)
                ],
            },
            "capital": {
                "aum_basis": {"label": "User CTA AUM assumption", "aum_usd": 100_000_000_000.0},
                "estimated_gross_risk_deployed_usd": 95_000_000_000.0,
                "estimated_remaining_gross_headroom_usd": 405_000_000_000.0,
                "note": "Risk deployed, not cash spent.",
            },
            "validation": {
                "signal": {"status": "unavailable", "note": "SG missing"},
                "position": {"agreement_pct": 0.55, "coverage": 11},
                "return": {"summary": "Low"},
            },
            "actions": ["Watch Euro FX", "Respect crowding", "Treat COT as weekly"],
        }

        payload = build_gemini_request_payload(large_facts, output_format="markdown")
        prompt_text = payload["contents"][0]["parts"][0]["text"]

        self.assertLess(len(prompt_text), 8500)

    def test_build_gemini_request_payload_disables_thinking_for_gemini_2_5_flash(self):
        payload = build_gemini_request_payload(
            {"conclusion": {"headline": "net long"}},
            output_format="markdown",
            model_name="gemini-2.5-flash",
        )

        self.assertEqual(
            payload["generationConfig"]["thinkingConfig"]["thinkingBudget"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
