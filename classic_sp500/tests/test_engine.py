import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run as classic


class SAndP500ClassicTests(unittest.TestCase):
    def setUp(self):
        self.config = classic.market.read(Path(__file__).resolve().parents[1] / "config.json")
        self.symbols = classic.verify_config(self.config)
        self.day = "2026-10-13"
        self.fake = {"buy_hold_equal_weight": [
            ("AAPL", "buy", .05), ("MSFT", "buy", .03)
        ]}
        self.diagnostic = {"eligible": 503, "total": 503, "missing": {}, "ticker_coverage_pct": 100}
        self.book = classic.initialize(self.config, self.day, self.fake, self.diagnostic)

    def test_universe_matches_existing_canonical_503(self):
        self.assertEqual(len(self.symbols), 503)
        self.assertIn("AAPL", self.symbols)
        self.assertIn("BRK-B", self.symbols)
        self.assertEqual(set(self.book["books"]), set(self.config["strategies"]) | {"benchmark_spy"})
        self.assertEqual(self.book["first_session"], self.day)
        self.assertTrue(all(b["trades"] == [] for b in self.book["books"].values()))

    def test_universe_cannot_be_reduced(self):
        c = copy.deepcopy(self.config)
        c["universe_file"] = "paper_demo/universe_eight.csv"
        with self.assertRaises(ValueError):
            classic.verify_config(c)
        c = copy.deepcopy(self.config)
        c["initial_capital"] = 80000
        with self.assertRaises(ValueError):
            classic.verify_config(c)

    def test_next_open_503_equal_weight_benchmark_and_positions(self):
        prices = {"AAPL": {"open": 100, "low": 99, "high": 105, "close": 104},
                  "MSFT": {"open": 200, "low": 200, "high": 203, "close": 202},
                  "SPY": {"open": 400, "low": 398, "high": 406, "close": 405}}
        updated, changed = classic.settle(self.config, self.book, "2026-10-14",
                                          self.day, prices)
        self.assertTrue(changed)
        self.assertIn("AAPL", updated["books"]["buy_hold_equal_weight"]["positions"])
        self.assertIn("MSFT", updated["books"]["buy_hold_equal_weight"]["positions"])
        self.assertIn("SPY", updated["books"]["benchmark_spy"]["positions"])
        self.assertGreater(updated["books"]["buy_hold_equal_weight"]["nav"], 100000)
        self.assertEqual(self.book["last_session"], self.day)
        self.assertEqual(updated["last_session"], "2026-10-14")
        self.assertEqual(len(updated["books"]["macd_12_26_9"]["equity"]), 2)

    def test_no_retroactive_reconstruction(self):
        with self.assertRaisesRegex(ValueError, "Missing market session"):
            classic.settle(self.config, self.book, "2026-10-15", "2026-10-14", {})
        same, changed = classic.settle(self.config, self.book, self.day, "2026-10-12", {})
        self.assertFalse(changed)
        self.assertEqual(same, self.book)

    def test_full_coverage_is_requested_not_faked(self):
        with self.assertRaisesRegex(ValueError, "insufficient dated data"):
            classic.rank_signals(self.config, {}, self.day)
        self.assertEqual(self.book["coverage"][0]["total"], 503)

    def test_sp500_new_diary_differs_from_legacy_book(self):
        legacy = classic.market.read(Path(__file__).resolve().parents[2] / "paper_demo/config.json")
        self.assertEqual(len(legacy["tickers"]), 8)
        self.assertNotEqual(classic.market.digest(legacy), self.book["config_hash"])
        self.assertEqual(self.book["currency"], "USD")


    def test_missing_mandatory_close_gets_isolated_same_session_retry(self):
        from unittest.mock import patch
        synthetic = object()
        quoted = {"Open": 101.0, "High": 103.0, "Low": 99.0, "Close": 102.0}
        calls = []

        def download(symbols, start, end, allow_missing=False):
            calls.append(list(symbols))
            if len(calls) == 1:
                return {"SPY": synthetic}
            self.assertEqual(symbols, ["SYNTH"])
            return {"SYNTH": synthetic}

        with (patch.object(classic.market, "_download", side_effect=download),
              patch.object(classic.market, "_last_row", return_value=quoted)):
            frames, bars = classic.fetch_live(
                self.config, "2026-10-14", "2026-10-13", ["AAPL"], required={"SYNTH"})
        self.assertEqual(len(calls), 2)
        self.assertIn("SYNTH", frames)
        self.assertEqual(bars["SYNTH"]["close"], 102.0)

    def test_isolated_retry_never_fabricates_missing_mandatory_close(self):
        from unittest.mock import patch
        with patch.object(classic.market, "_download", side_effect=[
            {}, {"SYNTH": object()}
        ]) as download, patch.object(
            classic.market, "_last_row", side_effect=ValueError("Missing exact dated OHLC")
        ):
            frames, bars = classic.fetch_live(
                self.config, "2026-10-14", "2026-10-13", ["AAPL"], required={"SYNTH"})
        self.assertNotIn("SYNTH", bars)
        self.assertEqual(download.call_count, 2)
        self.assertEqual(frames, {})

    def test_non_held_missing_symbols_are_not_individually_refetched(self):
        from unittest.mock import patch
        with patch.object(classic.market, "_download", return_value={}) as download:
            frames, bars = classic.fetch_live(
                self.config, "2026-10-14", "2026-10-13", ["AAPL"], required=set())
        self.assertEqual((frames, bars), ({}, {}))
        self.assertEqual(download.call_count, 1)


if __name__ == "__main__":
    unittest.main()
