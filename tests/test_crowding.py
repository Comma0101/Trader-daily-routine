"""Tests for model/crowding.py."""

import unittest

from model.crowding import compute_crowding_percentile


class CrowdingPercentileTests(unittest.TestCase):
    def test_percentile_with_known_history(self):
        # Current ratio 0.6 is higher than 8 of 10 values
        history = [0.1, 0.2, 0.3, 0.3, 0.4, 0.4, 0.5, 0.5, 0.6, 0.7]
        result = compute_crowding_percentile(0.6, history)

        self.assertEqual(result["current_ratio"], 0.6)
        self.assertIsInstance(result["percentile"], int)
        self.assertGreater(result["percentile"], 50)
        self.assertEqual(result["classification"], "MODERATE")
        self.assertIn("percentile", result["context"])

    def test_empty_history(self):
        result = compute_crowding_percentile(0.8, [])

        self.assertIsNone(result["percentile"])
        self.assertEqual(result["classification"], "HIGH")
        self.assertIn("No historical data", result["context"])

    def test_all_crowded_history(self):
        history = [1.0] * 252
        result = compute_crowding_percentile(1.0, history)

        self.assertEqual(result["percentile"], 50)
        self.assertEqual(result["classification"], "HIGH")

    def test_single_day_history(self):
        result = compute_crowding_percentile(0.5, [0.3])

        self.assertIsInstance(result["percentile"], int)
        self.assertEqual(result["percentile"], 100)
        self.assertIn("1d", result["context"])

    def test_low_crowding(self):
        history = [0.5, 0.6, 0.7, 0.8] * 63
        result = compute_crowding_percentile(0.2, history)

        self.assertEqual(result["classification"], "LOW")
        self.assertLess(result["percentile"], 10)

    def test_high_crowding_percentile_context_shows_1y(self):
        history = [0.3] * 252
        result = compute_crowding_percentile(0.8, history)

        self.assertIn("1Y", result["context"])

    def test_short_history_shows_day_count(self):
        history = [0.3] * 50
        result = compute_crowding_percentile(0.8, history)

        self.assertIn("50d", result["context"])


if __name__ == "__main__":
    unittest.main()
