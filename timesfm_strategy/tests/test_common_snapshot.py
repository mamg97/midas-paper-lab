"""TimesFM daily consumes only genuine RAW marks; FX is still independent."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run as core

from market_data.snapshot import make_snapshot, write_immutable


DAY = "2026-10-27"
PREV = "2026-10-26"
UNIVERSE = ["AAPL"] + [f"ZZ{i:03d}" for i in range(502)]


class SharedDailyMarkTests(unittest.TestCase):
    def setUp(self):
        self.state = {"books": {
            "timesfm": {"pending": [{"ticker": "AAPL"}], "positions": {}},
            "benchmark_spy": {"pending": [{"ticker": "SPY"}], "positions": {}},
        }}
        self.config = {"fx_ticker": "EURUSD=X"}

    def _prices(self, names, start, end, allow_missing=False):
        if names == ["EURUSD=X"]:
            return {"EURUSD=X": pd.DataFrame(
                {"Close": [1.1, 1.2]}, index=pd.to_datetime([PREV, DAY]))}
        if names == ["AAPL", "SPY"]:
            return {"SPY": pd.DataFrame(
                {"Open": [400.], "Close": [410.], "Dividends": [0.],
                 "Stock Splits": [0.]}, index=pd.to_datetime([DAY]))}
        raise AssertionError("Unexpected provider request: " + repr(names))

    def test_missing_yahoo_stock_recovers_only_from_real_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bars = {
                "AAPL": {"date": DAY, "open": 100., "high": 104.,
                         "low": 99., "close": 103., "volume": 500.,
                         "dividend": 0., "split": 0.},
                "SPY": {"date": DAY, "open": 400., "high": 412.,
                        "low": 398., "close": 410., "volume": 1000.,
                        "dividend": 0., "split": 0.},
            }
            record = make_snapshot(DAY, UNIVERSE, bars,
                                   captured_at_utc="2026-10-27T22:40:00+00:00")
            write_immutable(root / "market_data" / "snapshots", record)
            with (patch.object(core, "ROOT", root),
                  patch.object(core, "_download", side_effect=self._prices)):
                result, fx_entry, fx_mark = core._daily_bars(
                    self.config, self.state, DAY, PREV)
            self.assertEqual(result["AAPL"]["open"], 100.)
            self.assertEqual(result["SPY"]["close"], 410.)
            self.assertEqual(fx_entry, 1.1)
            self.assertEqual(fx_mark, 1.2)
            self.assertNotIn("ZZ000", result)

    def test_without_snapshot_missing_holding_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (patch.object(core, "ROOT", Path(tmp)),
                  patch.object(core, "_download", side_effect=self._prices)):
                with self.assertRaisesRegex(ValueError, "Missing exact-date"):
                    core._daily_bars(self.config, self.state, DAY, PREV)


if __name__ == "__main__":
    unittest.main()
