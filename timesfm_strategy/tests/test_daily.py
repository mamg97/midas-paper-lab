import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import daily_run
import run


class DailyEURTests(unittest.TestCase):
    def setUp(self):
        self.config = run.read(Path(__file__).resolve().parents[1] / "config-daily.json")
        self.date = "2026-10-13"
        self.orders = [{"ticker": "AAPL", "signal_date": self.date,
                        "predicted_return": .012, "score": .008}]
        self.state = daily_run.initialize(self.config, self.date, self.orders, {"regime": True})
        self.bars = {"AAPL": {"open": 100, "close": 110, "dividend": 0, "split": 0},
                     "SPY": {"open": 400, "close": 405, "dividend": 0, "split": 0}}

    def test_initial_state_is_prospective(self):
        daily_run.verify(self.config)
        self.assertEqual(self.state["first_session"], self.date)
        self.assertEqual(self.state["currency"], "EUR")
        self.assertEqual(self.state["books"]["timesfm_daily"]["trades"], [])
        self.assertEqual(self.state["books"]["timesfm_daily"]["nav"], 100000)
        self.assertEqual(self.state["books"]["benchmark_spy"]["pending"][0]["ticker"], "SPY")

    def test_daily_intraday_fill_settles_at_observed_close(self):
        result, changed = daily_run.process_session(
            self.state, self.config, "2026-10-14", self.date, self.bars,
            fx_entry=1.2, fx_mark=1.15)
        self.assertTrue(changed)
        book = result["books"]["timesfm_daily"]
        self.assertEqual(book["positions"], {})
        self.assertEqual(book["pending"], [])
        self.assertEqual(len(book["trades"]), 1)
        self.assertEqual(book["trades"][0]["entry_date"], "2026-10-14")
        self.assertEqual(book["trades"][0]["exit_date"], "2026-10-14")
        self.assertGreater(book["nav"], 100000)
        self.assertIn("SPY", result["books"]["benchmark_spy"]["positions"])
        self.assertEqual(self.state["last_session"], self.date)

    def test_reject_missed_and_repeated_sessions(self):
        with self.assertRaisesRegex(ValueError, "Missed XNYS"):
            daily_run.process_session(self.state, self.config, "2026-10-15",
                                      "2026-10-14", self.bars, fx_entry=1.2, fx_mark=1.15)
        same, changed = daily_run.process_session(self.state, self.config,
                                                   self.date, "2026-10-12",
                                                   self.bars, fx_entry=1.2, fx_mark=1.15)
        self.assertFalse(changed)
        self.assertEqual(same, self.state)

    def test_frozen_one_day_signal_requires_daily_settlement(self):
        with self.assertRaisesRegex(ValueError, "same-day"):
            daily_run.freeze_signal(self.state, self.config, "2026-10-14", [], {})
        updated, _ = daily_run.process_session(self.state, self.config, "2026-10-14",
                                               self.date, self.bars, fx_entry=1.2, fx_mark=1.15)
        future, changed = daily_run.freeze_signal(updated, self.config, "2026-10-14", [], {})
        self.assertTrue(changed)
        self.assertEqual(future["last_signal_session"], "2026-10-14")
        self.assertEqual(len(future["signal_history"]), 2)
        self.assertEqual(len(self.state["signal_history"]), 1)

    def test_campaigns_are_independent(self):
        weekly = run.read(Path(__file__).resolve().parents[1] / "config.json")
        self.assertNotEqual(run.digest(weekly), run.digest(self.config))
        self.assertEqual(self.config["model"]["horizon_sessions"], 1)
        self.assertEqual(weekly["model"]["horizon_sessions"], 5)
        self.assertEqual(run.load_universe(self.config["universe_file"]),
                         run.load_universe(weekly["universe_file"]))
        self.assertEqual(len(run.load_universe(self.config["universe_file"])), 503)
        changed = copy.deepcopy(self.config)
        changed["initial_capital"] = 99999
        with self.assertRaises(ValueError):
            daily_run.verify(changed)


if __name__ == "__main__":
    unittest.main()
