"""Tests for threshold distance bucketing in summary.py."""

import unittest

from summary import _bucket_threshold_distance


class ThresholdBucketTests(unittest.TestCase):
    def test_very_near(self):
        self.assertEqual(_bucket_threshold_distance(0.5), "very_near")
        self.assertEqual(_bucket_threshold_distance(0.0), "very_near")
        self.assertEqual(_bucket_threshold_distance(0.99), "very_near")

    def test_near(self):
        self.assertEqual(_bucket_threshold_distance(1.0), "near")
        self.assertEqual(_bucket_threshold_distance(1.5), "near")
        self.assertEqual(_bucket_threshold_distance(2.49), "near")

    def test_moderate(self):
        self.assertEqual(_bucket_threshold_distance(2.5), "moderate")
        self.assertEqual(_bucket_threshold_distance(3.0), "moderate")
        self.assertEqual(_bucket_threshold_distance(4.99), "moderate")

    def test_far(self):
        self.assertEqual(_bucket_threshold_distance(5.0), "far")
        self.assertEqual(_bucket_threshold_distance(10.0), "far")
        self.assertEqual(_bucket_threshold_distance(100.0), "far")

    def test_negative_treated_as_absolute(self):
        self.assertEqual(_bucket_threshold_distance(-0.5), "very_near")
        self.assertEqual(_bucket_threshold_distance(-3.0), "moderate")

    def test_none_treated_as_zero(self):
        self.assertEqual(_bucket_threshold_distance(None), "very_near")


if __name__ == "__main__":
    unittest.main()
