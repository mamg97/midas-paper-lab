"""Exact-session mandatory Yahoo bar recovery: no stale prices or invented fills."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market import download_panel


def daily_frame(day):
    return pd.DataFrame(
        {"Open": [100.0], "High": [103.0], "Low": [99.0],
         "Close": [101.0], "Adj Close": [101.0], "Volume": [600]},
        index=pd.DatetimeIndex([day]),
    )


class MandatoryPriceRetryTests(unittest.TestCase):
    def test_bulk_missing_recovers_held_quote_with_exact_session(self):
        with patch("yfinance.download", side_effect=[
            pd.DataFrame(), daily_frame("2026-10-16"),
        ]) as yf:
            panel, failures = download_panel(
                ["AAA"], period="6mo", asof="2026-10-16",
                min_history=1, required={"AAA"},
            )
        self.assertEqual(yf.call_count, 2)
        self.assertFalse(yf.call_args.kwargs["threads"])
        self.assertEqual(float(panel["AAA"]["close"].iloc[-1]), 101.0)
        self.assertEqual(failures, {})

    def test_stale_bar_is_not_accepted_after_isolated_retry(self):
        with patch("yfinance.download", side_effect=[
            pd.DataFrame(), daily_frame("2026-10-15"),
        ]) as yf:
            panel, failures = download_panel(
                ["AAA"], period="6mo", asof="2026-10-16",
                min_history=1, required={"AAA"},
            )
        self.assertEqual(yf.call_count, 2)
        self.assertNotIn("AAA", panel)
        self.assertEqual(failures["AAA"], "missing_asof")

    def test_only_required_quotes_are_retried(self):
        with patch("yfinance.download", return_value=pd.DataFrame()) as yf:
            panel, failures = download_panel(
                ["AAA", "BBB"], period="6mo", asof="2026-10-16",
                min_history=1, required=set(),
            )
        self.assertEqual(yf.call_count, 1)
        self.assertEqual(panel, {})
        self.assertEqual(set(failures), {"AAA", "BBB"})

    def test_missing_required_symbol_must_be_in_frozen_request(self):
        with patch("yfinance.download") as yf:
            with self.assertRaisesRegex(ValueError, "outside requested"):
                download_panel(
                    ["AAA"], period="6mo", asof="2026-10-16",
                    min_history=1, required={"NOT_IN_UNIVERSE"},
                )
        yf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
