import copy
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run


class TimesFMEURPaperTests(unittest.TestCase):
    def setUp(self):
        self.config = run.read(Path(__file__).resolve().parents[1] / "config.json")
        self.config["execution"]["min_forecast_return"] = .015
        self.signal_date = "2026-10-16"
        self.orders = [{"ticker": "AAPL", "signal_date": self.signal_date,
                        "predicted_return": .04, "score": .03}]
        self.state = run.initialize(self.config, self.signal_date, self.orders, {"sample": True})

    def test_signal_is_not_a_trade_or_a_return(self):
        b = self.state["books"]["timesfm"]
        self.assertEqual(b["cash"], 100000)
        self.assertEqual(b["trades"], [])
        self.assertEqual(b["positions"], {})
        self.assertEqual(len(b["equity"]), 1)
        self.assertEqual(self.state["books"]["benchmark_spy"]["pending"][0]["ticker"], "SPY")

    def test_next_open_converts_usd_to_eur_and_marks_eur(self):
        bars = {"AAPL": {"open": 100, "close": 110},
                "SPY": {"open": 400, "close": 420}}
        s, changed = run.process_day(self.state, self.config, "2026-10-19",
                                     "2026-10-16", bars,
                                     fx_entry=1.2, fx_mark=1.1, week_end=False)
        self.assertTrue(changed)
        a = s["books"]["timesfm"]
        self.assertEqual(len(a["positions"]), 1)
        self.assertEqual(len(s["books"]["benchmark_spy"]["positions"]), 1)
        pos = a["positions"]["AAPL"]
        self.assertAlmostEqual(pos["entry_price_eur"], 100 / 1.2 * 1.0005, places=7)
        self.assertGreater(a["nav"], 100000)
        self.assertEqual(s["last_session"], "2026-10-19")
        self.assertEqual(self.state["last_session"], "2026-10-16")  # atomic/pure

    def test_weekly_close_settles_strategy_not_buy_and_hold_spy(self):
        bars = {"AAPL": {"open": 100, "close": 110},
                "SPY": {"open": 400, "close": 420}}
        bought, _ = run.process_day(self.state, self.config, "2026-10-19",
                                    "2026-10-16", bars,
                                    fx_entry=1.2, fx_mark=1.1, week_end=False)
        close, _ = run.process_day(bought, self.config, "2026-10-20", "2026-10-19",
                                   {"AAPL": {"open": 111, "close": 112},
                                    "SPY": {"open": 421, "close": 422}},
                                   fx_entry=1.1, fx_mark=1.15, week_end=True)
        self.assertEqual(close["books"]["timesfm"]["positions"], {})
        self.assertEqual(len(close["books"]["timesfm"]["trades"]), 1)
        self.assertIn("SPY", close["books"]["benchmark_spy"]["positions"])
        self.assertEqual(len(close["books"]["benchmark_spy"]["trades"]), 0)

    def test_no_backfill_and_idempotent(self):
        with self.assertRaisesRegex(ValueError, "Missed market session"):
            run.process_day(self.state, self.config, "2026-10-20", "2026-10-19", {},
                            fx_entry=1.2, fx_mark=1.2, week_end=False)
        same, changed = run.process_day(self.state, self.config, self.signal_date,
                                        "2026-10-15", {}, fx_entry=1.2,
                                        fx_mark=1.2, week_end=False)
        self.assertFalse(changed)
        self.assertEqual(same, self.state)

    def test_no_signal_revision_and_preceding_day_required(self):
        with self.assertRaisesRegex(ValueError, "A daily NAV is missing"):
            run.record_signal(self.state, self.config, "2026-10-23", [], {})
        s, changed = run.record_signal(self.state, self.config, self.signal_date, [], {})
        self.assertFalse(changed)
        self.assertEqual(s, self.state)

    def test_dividend_only_for_held_position_and_split_adjusts_shares(self):
        day = {"AAPL": {"open": 100, "close": 105, "dividend": 2},
               "SPY": {"open": 400, "close": 400}}
        bought, _ = run.process_day(self.state, self.config, "2026-10-19",
                                    self.signal_date, day, fx_entry=1.2,
                                    fx_mark=1.2, week_end=False)
        self.assertEqual(bought["books"]["timesfm"]["positions"]["AAPL"]["dividends_eur"], 0)
        shares = bought["books"]["timesfm"]["positions"]["AAPL"]["shares"]
        held, _ = run.process_day(bought, self.config, "2026-10-20", "2026-10-19",
                                  {"AAPL": {"open": 52, "close": 53, "dividend": 1, "split": 2},
                                   "SPY": {"open": 401, "close": 403}}, fx_entry=1.2,
                                  fx_mark=1.25, week_end=False)
        self.assertAlmostEqual(held["books"]["timesfm"]["positions"]["AAPL"]["shares"], 2 * shares)
        self.assertAlmostEqual(held["books"]["timesfm"]["positions"]["AAPL"]["dividends_eur"],
                               2 * shares / 1.25)

    def test_reject_wrong_currency_and_model(self):
        c = copy.deepcopy(self.config)
        c["currency"] = "USD"
        with self.assertRaises(ValueError):
            run.initialize(c, self.signal_date, [], {})
        c = copy.deepcopy(self.config)
        c["model"]["model_id"] = "google/timesfm-3.0-pytorch"
        with self.assertRaises(ValueError):
            run.initialize(c, self.signal_date, [], {})


if __name__ == "__main__":
    unittest.main()
