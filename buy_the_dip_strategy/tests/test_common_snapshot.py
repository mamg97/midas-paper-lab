"""Daily RAW fallback must not replace the monthly adjusted signal panel."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run as runner
from market_data.snapshot import make_snapshot, write_immutable

DAY = "2026-10-27"
UNIVERSE = ["AAPL"] + [f"S{i:03d}" for i in range(502)]


def bar():
    return {"date": DAY, "open": 100., "high": 103., "low": 99.,
            "close": 102., "volume": 500., "dividend": 0., "split": 0.}


class CommonDailyMarksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch.object(runner, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.record = make_snapshot(
            DAY, UNIVERSE, {"AAPL": bar(), "SPY": bar(), "S000": bar()},
            captured_at_utc="2026-10-27T22:00:00+00:00")
        self.path, _ = write_immutable(self.root / "market_data/snapshots", self.record)

    def test_recovers_required_marks_without_adding_candidates(self):
        before = self.path.read_bytes()
        got, info = runner._daily_marks({}, DAY, ["AAPL", "SPY"])
        self.assertEqual(set(got), {"AAPL", "SPY"})
        self.assertEqual(got["AAPL"]["close"], 102.)
        self.assertEqual(info["hash"], self.record["sha256"])
        self.assertNotIn("adj_close", got["AAPL"])
        self.assertEqual(before, self.path.read_bytes())

    def test_preserves_vendor_disagreement_and_input_panel(self):
        panel = {"AAPL": pd.DataFrame([{k: v for k, v in bar().items() if k != "date"}],
                                     index=pd.DatetimeIndex([DAY]))}
        panel["AAPL"].loc[:, "close"] = 101.
        before = copy.deepcopy(panel)
        got, info = runner._daily_marks(panel, DAY, ["AAPL", "SPY"])
        self.assertEqual(got["AAPL"]["close"], 102.)
        self.assertEqual(info["status"], "common_raw_primary")
        pd.testing.assert_frame_equal(panel["AAPL"], before["AAPL"])

    def test_missing_or_wrong_session_stays_closed(self):
        for day, requested in [(DAY, ["S001"]), ("2026-10-28", ["AAPL"])]:
            with self.subTest(day=day, requested=requested):
                with self.assertRaisesRegex(ValueError, "No se pueden valorar|Missing verified common"):
                    runner._daily_marks({}, day, requested)

    def test_tampered_snapshot_stays_closed(self):
        value = json.loads(self.path.read_text())
        value["bars"]["AAPL"]["close"] = 101.
        self.path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "No se pueden valorar|Missing verified common"):
            runner._daily_marks({}, DAY, ["AAPL"])

    def test_signal_day_replay_uses_original_full_universe_hash_scope(self):
        """A monthly-signal retry must not become a false revision alarm."""
        config = {"schema_version": 1, "name": "MIDAS_buy_the_dip_corpus_v0_2026",
                  "currency": "USD", "universe_file": "unused.csv", "benchmark_ticker": "SPY"}
        state = {"positions": {"AAPL": {}}, "pending": None,
                 "last_session": DAY, "last_signal_session": DAY,
                 "universe_hash": "frozen"}
        updated = {"nav": 1000., "positions": {}, "cash": 1000.}
        with (patch.object(runner, "_read", side_effect=[config, state]),
              patch.object(runner, "eligible_session", return_value=DAY),
              patch.object(runner, "calendar_context", return_value={"is_month_end": False}),
              patch.object(runner, "_file_hash", return_value="frozen"),
              patch.object(runner, "load_universe", return_value=(UNIVERSE, {}, {})),
              patch.object(runner, "_decision_due", return_value=False),
              patch.object(runner, "download_panel") as download,
              patch.object(runner, "fundamentals_snapshot") as fundamentals,
              patch.object(runner, "advance", return_value=(updated, False)) as advance,
              patch.object(runner, "benchmark_return_pct", return_value=0.),
              patch.object(runner, "_atomic_json") as save):
            result = runner.run("config.json", self.root / "state")
        bars = advance.call_args.args[1]
        self.assertEqual(set(bars), {"AAPL", "SPY", "S000"})
        self.assertIsNone(advance.call_args.kwargs["decision"])
        self.assertEqual(result["quote_source"]["hash"], self.record["sha256"])
        download.assert_not_called()
        fundamentals.assert_not_called()
        save.assert_not_called()

    def test_daily_runner_uses_fallback_before_accounting(self):
        config = {"schema_version": 1, "name": "MIDAS_buy_the_dip_corpus_v0_2026",
                  "currency": "USD", "universe_file": "unused.csv", "benchmark_ticker": "SPY"}
        state = {"positions": {"AAPL": {}}, "pending": None}
        updated = {"nav": 1000., "positions": {}, "cash": 1000.}
        with (patch.object(runner, "_read", side_effect=[config, state]),
              patch.object(runner, "eligible_session", return_value=DAY),
              patch.object(runner, "calendar_context", return_value={"is_month_end": False}),
              patch.object(runner, "_file_hash", return_value="frozen"),
              patch.object(runner, "load_universe", return_value=(UNIVERSE, {}, {})),
              patch.object(runner, "_decision_due", return_value=False),
              patch.object(runner, "download_panel", return_value=({}, {"AAPL": "missing_asof"})),
              patch.object(runner, "fundamentals_snapshot") as fundamentals,
              patch.object(runner, "advance", return_value=(updated, False)) as advance,
              patch.object(runner, "benchmark_return_pct", return_value=0.),
              patch.object(runner, "_atomic_json") as save):
            result = runner.run("config.json", self.root / "state")
        self.assertEqual(advance.call_args.args[1]["AAPL"]["close"], 102.)
        self.assertIsNone(advance.call_args.kwargs["decision"])
        self.assertEqual(result["quote_source"]["hash"], self.record["sha256"])
        fundamentals.assert_not_called()
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
