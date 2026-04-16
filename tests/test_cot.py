import io
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

import pandas as pd

from data.cot import COTData


class COTDataFetchTests(unittest.TestCase):
    def test_fetch_suppresses_cot_reports_stdout_chatter(self):
        fake_cot = types.SimpleNamespace()

        def fake_cot_year(year, cot_report_type):
            print(f"Selected: {cot_report_type}")
            return pd.DataFrame(
                {
                    "CFTC_Contract_Market_Code": [],
                    "Report_Date_as_YYYY-MM-DD": [],
                }
            )

        fake_cot.cot_year = fake_cot_year
        fake_package = types.SimpleNamespace(cot_reports=fake_cot)

        output = io.StringIO()
        with redirect_stdout(output):
            with mock.patch.dict(sys.modules, {"cot_reports": fake_package}):
                reports = COTData().fetch(year=2026)

        self.assertEqual(output.getvalue(), "")
        self.assertIn("TFF", reports)
        self.assertIn("DISAGG", reports)


if __name__ == "__main__":
    unittest.main()
