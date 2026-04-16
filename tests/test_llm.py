import unittest

from llm import build_gemini_request_payload, _compact_facts_for_prompt, _prompt_text


class LlmApiKeyTests(unittest.TestCase):
    """Verify API key is sent via header, not URL params."""

    def test_generate_uses_header_not_url_params(self):
        """The requests.post call in generate_gemini_summary uses
        x-goog-api-key header. We verify by inspecting the source —
        no 'params=' with 'key' should exist."""
        import inspect
        import llm

        source = inspect.getsource(llm.generate_gemini_summary)
        self.assertNotIn("params=", source)
        self.assertIn("x-goog-api-key", source)


class LlmPromptTerminologyTests(unittest.TestCase):
    """Verify prompt uses notional terminology, not buyer/seller."""

    def _minimal_facts(self):
        return {
            "report_date": "2026-04-16",
            "scope": {"selected_market_count": 4, "universe_market_count": 21},
            "position_counts": {"long": 2, "short": 1, "flat": 1},
            "crowding": {
                "classification": "HIGH",
                "crowded_market_count": 3,
                "total_market_count": 4,
            },
            "flow": {
                "estimation_label": "Model-implied target notional change (not observed flow)",
                "top_notional_increase_5d": [],
                "top_notional_decrease_5d": [],
            },
            "capital": {},
            "validation": {},
            "investment_overview": {},
        }

    def test_terminal_prompt_uses_notional_not_buyer_seller(self):
        prompt = _prompt_text(self._minimal_facts(), output_format="terminal")
        self.assertNotIn("buyer/seller", prompt.lower())
        self.assertIn("notional increase/decrease", prompt.lower())

    def test_markdown_prompt_uses_notional_increases_decreases(self):
        prompt = _prompt_text(self._minimal_facts(), output_format="markdown")
        self.assertIn("Top Notional Increases", prompt)
        self.assertIn("Top Notional Decreases", prompt)
        self.assertNotIn("Top Buyers", prompt)
        self.assertNotIn("Top Sellers", prompt)

    def test_prompt_includes_proxy_model_framing(self):
        prompt = _prompt_text(self._minimal_facts(), output_format="markdown")
        self.assertIn("PROXY model", prompt)
        self.assertIn("model-implied target notional changes", prompt.lower())

    def test_prompt_includes_validation_grade_instruction(self):
        prompt = _prompt_text(self._minimal_facts(), output_format="markdown")
        self.assertIn("validation grade", prompt.lower())


class LlmCompactFactsTests(unittest.TestCase):
    """Verify compact facts include validation_composite and crowding percentile."""

    def _facts_with_composite_and_crowding(self):
        return {
            "report_date": "2026-04-16",
            "scope": {"selected_market_count": 4, "universe_market_count": 21},
            "position_counts": {"long": 2, "short": 1, "flat": 1},
            "crowding": {
                "classification": "HIGH",
                "crowded_market_count": 3,
                "total_market_count": 4,
                "percentile": 87,
                "percentile_context": "87th percentile vs trailing 1Y",
            },
            "flow": {
                "estimation_label": "Model-implied target notional change (not observed flow)",
                "top_notional_increase_5d": [],
                "top_notional_decrease_5d": [],
            },
            "capital": {},
            "validation": {
                "signal": {"coverage": 0, "note": "SG data unavailable"},
                "position": {"coverage": 5, "agreement_rate": 0.6},
                "return": {"summary": "Good", "correlation_full": 0.55},
                "composite": {
                    "composite_score": 42,
                    "grade": "D",
                    "note": "Low confidence — SG signal validation unavailable",
                },
            },
            "investment_overview": {},
            "nearest_flip_risks": [
                {"symbol": "6E", "market": "Euro FX", "direction": "LONG",
                 "distance_pct": 0.76, "distance_bucket": "very_near"},
            ],
        }

    def test_compact_facts_include_validation_composite(self):
        compact = _compact_facts_for_prompt(self._facts_with_composite_and_crowding())
        self.assertIn("validation_composite", compact)
        self.assertEqual(compact["validation_composite"]["score"], 42)
        self.assertEqual(compact["validation_composite"]["grade"], "D")

    def test_compact_facts_include_crowding_percentile(self):
        compact = _compact_facts_for_prompt(self._facts_with_composite_and_crowding())
        self.assertEqual(compact["crowding"]["percentile"], 87)
        self.assertEqual(compact["crowding"]["percentile_context"], "87th percentile vs trailing 1Y")

    def test_compact_facts_include_distance_bucket_in_flip_risks(self):
        compact = _compact_facts_for_prompt(self._facts_with_composite_and_crowding())
        risks = compact["drivers"]["nearest_flip_risks"]
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0]["distance_bucket"], "very_near")

    def test_compact_facts_use_notional_key_names(self):
        compact = _compact_facts_for_prompt(self._facts_with_composite_and_crowding())
        drivers = compact["drivers"]
        self.assertIn("top_notional_increase_5d", drivers)
        self.assertIn("top_notional_decrease_5d", drivers)
        self.assertNotIn("top_buyers_5d", drivers)
        self.assertNotIn("top_sellers_5d", drivers)
