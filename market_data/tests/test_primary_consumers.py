"""All five real adapters must read the same bytes without a RAW re-download."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from market_data.snapshot import make_snapshot, write_immutable

ROOT = Path(__file__).resolve().parents[2]
DAY = "2026-10-27"
SCRIPT = r'''
import importlib.util, json, sys
from pathlib import Path
from unittest.mock import patch
root, fixture, family = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / family))
file = root / family / ("daily.py" if family == "weekly_ml" else "run.py")
spec = importlib.util.spec_from_file_location("consumer_adapter", file)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
core.ROOT = fixture
day = "2026-10-27"
if family in ("buy_the_dip_strategy", "capital_cycle"):
    bars, info = core._daily_marks({}, day, ["AAPL", "SPY"])
elif family == "classic_sp500":
    with patch.object(core.market, "_download", return_value={}) as provider:
        _, bars = core.fetch_live({"benchmark_ticker": "SPY", "execution": {"history_calendar_days": 100}},
                                  day, "2026-10-26", ["AAPL"])
    assert provider.call_count == 1  # Historical signal panel, never RAW retries.
elif family == "weekly_ml":
    bars = core.download_bars(["AAPL", "SPY"], day)
else:
    state = {"books": {"one": {"pending": [{"ticker": "AAPL"}], "positions": {"SPY": {}}}}}
    def fx(names, start, end, **kw):
        assert names == ["EURUSD=X"]  # FX is the ONLY separate product requested.
        return {"EURUSD=X": object()}
    with patch.object(core, "_download", side_effect=fx), patch.object(core, "_last_row", return_value={"Close": 1.1}):
        bars, _, _ = core._daily_bars({"fx_ticker": "EURUSD=X"}, state, day, "2026-10-26")
print(json.dumps({s: {k: bars[s][k] for k in ("open", "close")} for s in ["AAPL", "SPY"]}))
'''


class PrimaryConsumerParityTests(unittest.TestCase):
    def test_five_families_share_exact_dated_raw_marks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = {"date": DAY, "open": 100., "high": 103., "low": 99., "close": 102.,
                   "volume": 500., "dividend": 0., "split": 0.}
            names = ["AAPL"] + [f"S{i:03d}" for i in range(502)]
            record = make_snapshot(DAY, names, {"AAPL": row, "SPY": row},
                                   captured_at_utc="2026-10-27T23:00:00+00:00")
            path, _ = write_immutable(root / "market_data/snapshots", record)
            before = path.read_bytes()
            expected = {s: {"open": 100., "close": 102.} for s in ["AAPL", "SPY"]}
            for family in ["classic_sp500", "timesfm_strategy", "buy_the_dip_strategy", "capital_cycle", "weekly_ml"]:
                with self.subTest(family=family):
                    result = subprocess.run([sys.executable, "-c", SCRIPT, str(ROOT), str(root), family],
                                            check=True, capture_output=True, text=True)
                    self.assertEqual(json.loads(result.stdout), expected)
            self.assertEqual(path.read_bytes(), before)
