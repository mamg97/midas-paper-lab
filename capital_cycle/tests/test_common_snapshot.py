"""A current snapshot can recover a mark, never a missing historical replay."""
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


class CommonMarksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        root_patch = patch.object(runner, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        row = {"date": DAY, "open": 100., "high": 103., "low": 99.,
               "close": 102., "volume": 500., "dividend": 0., "split": 0.}
        names = ["AAPL"] + [f"S{i:03d}" for i in range(502)]
        record = make_snapshot(DAY, names, {"AAPL": row, "SPY": row},
                               captured_at_utc="2026-10-27T22:00:00+00:00")
        self.path, _ = write_immutable(self.root / "market_data/snapshots", record)
        self.sha = record["sha256"]
        self.panel = {"SPY": pd.DataFrame([{k: v for k, v in row.items() if k != "date"}],
                                         index=pd.DatetimeIndex([DAY]))}

    def test_current_missing_holding_recovers_without_mutating_snapshot(self):
        prior = self.path.read_bytes()
        bars, info = runner._daily_marks(self.panel, DAY, ["AAPL", "SPY"])
        self.assertEqual(set(bars), {"AAPL", "SPY"})
        self.assertEqual(bars["AAPL"]["close"], 102.)
        self.assertEqual(info["hash"], self.sha)
        self.assertEqual(self.path.read_bytes(), prior)

    def test_missing_and_wrong_session_still_fail(self):
        for day, requested in [(DAY, ["ABSENT"]), ("2026-10-28", ["AAPL"])]:
            with self.assertRaisesRegex(ValueError, "No se pueden valorar|Missing verified common"):
                runner._daily_marks({}, day, requested)

    def test_current_snapshot_cannot_recover_missing_prior_holding(self):
        panel = {"SPY": pd.concat([self.panel["SPY"].rename(
            index={pd.Timestamp(DAY): pd.Timestamp("2026-10-26")}), self.panel["SPY"]])}
        state = {"last_session": "2026-10-23", "positions": {"AAPL": {}}, "pending": None}
        with patch.object(runner, "calendar_context", return_value={"is_month_end": False}):
            with self.assertRaisesRegex(ValueError, "No se puede recuperar valoración"):
                runner._replay_nondecision_gap({}, panel, "SPY", state, DAY)

    def test_daily_runner_recovers_after_gap_checks_before_accounting(self):
        config = {"schema_version": 1, "name": "MIDAS_capital_cycle_inflection_2026",
                  "currency": "USD", "universe_file": "unused.csv", "benchmark_ticker": "SPY",
                  "allowed_sectors": []}
        state = {"positions": {"AAPL": {}}, "pending": None, "last_session": "2026-10-26"}
        updated = {"nav": 1000., "positions": {}, "cash": 1000.}
        with (patch.object(runner, "_read", side_effect=[config, state]),
              patch.object(runner, "eligible_session", return_value=DAY),
              patch.object(runner, "calendar_context", return_value={"is_month_end": False}),
              patch.object(runner, "_file_hash", return_value="frozen"),
              patch.object(runner, "load_universe", return_value=(["AAPL"], {}, {})),
              patch.object(runner, "_decision_due", return_value=False),
              patch.object(runner, "download_panel", return_value=(self.panel, {})),
              patch.object(runner, "fundamentals_snapshot") as fundamentals,
              patch.object(runner, "advance", return_value=(updated, False)) as advance,
              patch.object(runner, "benchmark_return_pct", return_value=0.),
              patch.object(runner, "_atomic_json") as save):
            result = runner.run("config.json", self.root / "state")
        self.assertEqual(advance.call_args.args[1]["AAPL"]["close"], 102.)
        self.assertEqual(result["quote_source"]["hash"], self.sha)
        fundamentals.assert_not_called()
        save.assert_not_called()
