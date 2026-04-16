import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from data.futures import FuturesData


class FuturesDataLiveTests(unittest.TestCase):
    def test_fetch_uses_same_day_cache_unless_refresh_is_requested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            cache_path = cache_dir / "ES.csv"
            cached = pd.DataFrame(
                {"Close": [100.0]},
                index=pd.to_datetime(["2026-04-15"]),
            )
            cached.to_csv(cache_path)

            today_timestamp = pd.Timestamp("2026-04-16 09:30:00").timestamp()
            fresh = pd.DataFrame(
                {"Close": [101.0]},
                index=pd.to_datetime(["2026-04-16"]),
            )
            ticker = mock.Mock()
            ticker.history.return_value = fresh

            universe = {"ES": {"ticker": "ES=F"}}
            futures = FuturesData(universe=universe, cache_dir=cache_dir)
            os.utime(cache_path, (today_timestamp, today_timestamp))

            with mock.patch("data.futures.pd.Timestamp.now", return_value=pd.Timestamp("2026-04-16 12:00:00")):
                with mock.patch("data.futures.yf.Ticker", return_value=ticker):
                    cached_result = futures._fetch_one("ES", "ES=F", "3y")
                    refreshed_result = futures._fetch_one("ES", "ES=F", "3y", refresh=True)

        self.assertEqual(float(cached_result["Close"].iloc[-1]), 100.0)
        self.assertEqual(float(refreshed_result["Close"].iloc[-1]), 101.0)
        ticker.history.assert_called_once()

    def test_prices_live_appends_intraday_quote_using_prior_raw_close_return(self):
        futures = FuturesData(universe={"ES": {"ticker": "ES=F"}})
        futures._raw["ES"] = pd.DataFrame(
            {"Close": [100.0, 102.0]},
            index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
        )
        futures._adjusted["ES"] = pd.Series(
            [98.0, 100.0],
            index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
            name="Close",
        )

        with mock.patch.object(
            futures,
            "_fetch_live_quote",
            return_value={"timestamp": pd.Timestamp("2026-04-16 13:15:00"), "price": 103.02},
        ):
            live_prices = futures.prices("ES", live=True)

        self.assertEqual(live_prices.index[-1], pd.Timestamp("2026-04-16 13:15:00"))
        self.assertAlmostEqual(float(live_prices.iloc[-1]), 101.0, places=6)

    def test_data_context_prefers_live_timestamp_when_available(self):
        futures = FuturesData(universe={"ES": {"ticker": "ES=F"}})
        futures._raw["ES"] = pd.DataFrame(
            {"Close": [100.0, 102.0]},
            index=pd.to_datetime(["2026-04-14", "2026-04-15"]),
        )
        futures._live_quotes["ES"] = {
            "timestamp": pd.Timestamp("2026-04-16 13:15:00"),
            "price": 103.02,
        }

        context = futures.data_context()

        self.assertEqual(context["official_close_date"], "2026-04-15")
        self.assertEqual(context["as_of"], "2026-04-16 13:15")
        self.assertEqual(context["mode"], "live")


if __name__ == "__main__":
    unittest.main()
