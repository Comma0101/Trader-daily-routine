"""Verify that all COT codes in config.py resolve to valid CFTC data."""

import unittest

from config import FUTURES_UNIVERSE


class CotCodeVerificationTests(unittest.TestCase):
    """Check that each market's cot_code can be fetched from the CFTC via cot_reports."""

    def test_all_markets_have_required_cot_fields(self):
        for symbol, meta in FUTURES_UNIVERSE.items():
            with self.subTest(symbol=symbol):
                self.assertIn("cot_code", meta, f"{symbol} missing cot_code")
                self.assertIn("cot_report", meta, f"{symbol} missing cot_report")
                self.assertIn("cot_category", meta, f"{symbol} missing cot_category")
                self.assertIn(
                    meta["cot_report"], ("TFF", "DISAGG"),
                    f"{symbol} has invalid cot_report: {meta['cot_report']}",
                )

    def test_cot_codes_are_non_empty_strings(self):
        for symbol, meta in FUTURES_UNIVERSE.items():
            with self.subTest(symbol=symbol):
                code = meta.get("cot_code")
                self.assertIsInstance(code, str, f"{symbol} cot_code is not a string")
                self.assertTrue(len(code) > 0, f"{symbol} cot_code is empty")

    def test_cot_codes_resolve_via_cot_reports_library(self):
        """Attempt to fetch a small sample of COT data for each code.

        This test requires network access. It fetches only the most recent
        report to minimize load. Markets that fail are collected and reported.
        """
        try:
            import cot_reports as cot
        except ImportError:
            self.skipTest("cot_reports library not installed")

        failures = []
        known_problematic = set()  # Codes known to have issues

        for symbol, meta in sorted(FUTURES_UNIVERSE.items()):
            code = meta["cot_code"]
            report_type = meta["cot_report"].lower()

            # Map our report type names to cot_reports function names
            try:
                if report_type == "tff":
                    df = cot.cot_year(year=2025, cot_report_type="traders_in_financial_futures_fut")
                elif report_type == "disagg":
                    df = cot.cot_year(year=2025, cot_report_type="disaggregated_fut")
                else:
                    failures.append((symbol, code, f"Unknown report type: {report_type}"))
                    continue

                if df is None or df.empty:
                    failures.append((symbol, code, "Empty dataframe returned"))
                    continue

                # Check if the code appears in the data
                code_col = "CFTC_Contract_Market_Code"
                if code_col not in df.columns:
                    # Try alternative column name
                    code_col = "CFTC Contract Market Code"
                    if code_col not in df.columns:
                        failures.append((symbol, code, f"No code column found in {report_type} data"))
                        continue

                matches = df[df[code_col].astype(str).str.strip() == code.strip()]
                if matches.empty:
                    failures.append((symbol, code, f"Code {code} not found in {report_type} data"))
                    known_problematic.add(symbol)

            except Exception as e:
                failures.append((symbol, code, f"Fetch error: {e}"))

        if failures:
            msg_lines = [f"\n{len(failures)} COT code(s) failed resolution:"]
            for symbol, code, reason in failures:
                msg_lines.append(f"  {symbol} (code={code}): {reason}")
            # Warn but don't fail for known-problematic codes
            if known_problematic:
                msg_lines.append(f"\nKnown suspects: {sorted(known_problematic)}")
            self.fail("\n".join(msg_lines))


if __name__ == "__main__":
    unittest.main()
