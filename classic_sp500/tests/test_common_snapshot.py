"""Prove actual classic fetch_live can reuse (not synthesize) a shared bar."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run as classic

from market_data.snapshot import make_snapshot, write_immutable


class ClassicCommonQuoteTests(unittest.TestCase):
    def test_real_fetch_live_reuses_exact_common_mark(self):
        day = "2026-10-27"
        frozen = ["AAPL"] + [f"ZZ{i:03d}" for i in range(502)]
        bar = {"date": day, "open": 100, "high": 103, "low": 99,
               "close": 102, "volume": 1000, "dividend": 0, "split": 0}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = make_snapshot(day, frozen,
                                   {"AAPL": bar, "SPY": dict(bar, close=101)},
                                   captured_at_utc="2026-10-27T22:35:00+00:00")
            write_immutable(root / "market_data" / "snapshots", record)
            cfg = {"execution": {"history_calendar_days": 100},
                   "benchmark_ticker": "SPY"}
            with (patch.object(classic, "ROOT", root),
                  patch.object(classic.market, "_download", return_value={})):
                historical, today = classic.fetch_live(
                    cfg, day, "2026-10-26", frozen)
            self.assertEqual(historical, {})
            self.assertEqual(today["AAPL"]["close"], 102)
            self.assertEqual(today["SPY"]["close"], 101)
            self.assertNotIn("ZZ000", today)
            self.assertEqual(len(today), 2)

    def test_no_snapshot_preserves_original_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"execution": {"history_calendar_days": 100},
                   "benchmark_ticker": "SPY"}
            with (patch.object(classic, "ROOT", Path(tmp)),
                  patch.object(classic.market, "_download", return_value={})):
                with self.assertRaisesRegex(ValueError, "Missing verified common"):
                    classic.fetch_live(cfg, "2026-10-27", "2026-10-26", ["AAPL"])



if __name__ == "__main__":
    unittest.main()
