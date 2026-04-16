"""Tests for validation/composite_score.py."""

import unittest

from validation.composite_score import compute_composite_score


class CompositeScoreTests(unittest.TestCase):
    def test_all_three_validators_available(self):
        signal = {"agreement_rate": 0.8, "coverage": 10}
        position = {"agreement_rate": 0.7, "coverage": 8}
        return_val = {
            "correlations": {"DBMF": {"full_period": 0.6}},
            "overlap_days": 100,
        }

        result = compute_composite_score(signal, position, return_val)

        self.assertGreater(result["composite_score"], 0)
        self.assertLessEqual(result["composite_score"], 100)
        self.assertIn(result["grade"], ("A", "B", "C", "D", "F"))
        self.assertTrue(result["components"]["signal"]["available"])
        self.assertTrue(result["components"]["position"]["available"])
        self.assertTrue(result["components"]["return"]["available"])
        self.assertAlmostEqual(result["available_weight"], 1.0)
        self.assertEqual(result["note"], "All validators available.")

    def test_sg_signal_unavailable_redistributes_weights(self):
        signal = {"agreement_rate": None, "note": "SG stub"}
        position = {"agreement_rate": 0.7, "coverage": 8}
        return_val = {
            "correlations": {"DBMF": {"full_period": 0.5}},
            "overlap_days": 100,
        }

        result = compute_composite_score(signal, position, return_val)

        self.assertFalse(result["components"]["signal"]["available"])
        self.assertTrue(result["components"]["position"]["available"])
        self.assertTrue(result["components"]["return"]["available"])
        self.assertAlmostEqual(result["available_weight"], 0.60)
        self.assertIn("signal", result["note"])

    def test_all_validators_unavailable_scores_zero_grade_f(self):
        result = compute_composite_score(None, None, None)

        self.assertEqual(result["composite_score"], 0.0)
        self.assertEqual(result["grade"], "F")
        self.assertAlmostEqual(result["available_weight"], 0.0)

    def test_grade_boundary_a(self):
        signal = {"agreement_rate": 0.9, "coverage": 10}
        position = {"agreement_rate": 0.85, "coverage": 10}
        return_val = {
            "correlations": {"DBMF": {"full_period": 0.7}},
            "overlap_days": 200,
        }

        result = compute_composite_score(signal, position, return_val)
        self.assertEqual(result["grade"], "A")

    def test_grade_boundary_b(self):
        signal = {"agreement_rate": 0.7, "coverage": 10}
        position = {"agreement_rate": 0.65, "coverage": 10}
        return_val = {
            "correlations": {"DBMF": {"full_period": 0.4}},
            "overlap_days": 100,
        }

        result = compute_composite_score(signal, position, return_val)
        self.assertIn(result["grade"], ("B", "C"))

    def test_grade_boundary_d(self):
        signal = {"agreement_rate": 0.3, "coverage": 5}
        position = {"agreement_rate": 0.3, "coverage": 5}
        return_val = {
            "correlations": {"DBMF": {"full_period": -0.2}},
            "overlap_days": 50,
        }

        result = compute_composite_score(signal, position, return_val)
        self.assertIn(result["grade"], ("D", "F"))

    def test_position_zero_coverage_is_unavailable(self):
        position = {"agreement_rate": None, "coverage": 0}
        result = compute_composite_score(None, position, None)

        self.assertFalse(result["components"]["position"]["available"])

    def test_return_with_error_is_unavailable(self):
        return_val = {"error": "Insufficient data"}
        result = compute_composite_score(None, None, return_val)

        self.assertFalse(result["components"]["return"]["available"])

    def test_custom_weights(self):
        signal = {"agreement_rate": 1.0, "coverage": 10}
        position = {"agreement_rate": 0.0, "coverage": 10}
        return_val = {
            "correlations": {"DBMF": {"full_period": 0.0}},
            "overlap_days": 50,
        }

        # Heavy weight on signal should push score up
        result = compute_composite_score(
            signal, position, return_val,
            weights={"signal": 0.90, "position": 0.05, "return": 0.05},
        )
        self.assertGreater(result["composite_score"], 80)


if __name__ == "__main__":
    unittest.main()
