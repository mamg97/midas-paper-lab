import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weekly_ml"))
from daily import freeze_signal, process_day, ENGINE_VERSION
from paper import digest


class DailyPaperTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "models": ["lgbm_return"], "currency": "USD",
            "paper_policy": {
                "capital": 100000, "commission": 0.001, "slippage": 0.0005,
                "invest_fraction": 0.95, "max_entry_weight": 0.12,
                "max_positions": 10, "min_predicted_return": 0.005,
                "min_direction_probability": .55,
                "ensemble_min_positive_votes": 3,
                "fractional_shares": True, "share_precision": 6,
                "min_notional": 10
            }
        }

    def signal(self, day="2026-10-09"):
        return {
            "asof": day, "config_hash": digest(self.config),
            "models": {"lgbm_return": {"AAA": {"predicted_return": 0.02}}}
        }

    def first(self):
        state, changed = freeze_signal(self.config, self.signal())
        self.assertTrue(changed)
        self.assertEqual(state["engine"], ENGINE_VERSION)
        self.assertEqual(state["last_session"], "2026-10-09")
        return state

    def monday(self):
        state = self.first()
        return process_day(self.config, state, "2026-10-12",
                           {"AAA": {"open": 100, "close": 105},
                            "SPY": {"open": 700, "close": 705},
                            "RSP": {"open": 200, "close": 203}},
                           previous_session="2026-10-09",
                           first_after_signal=True, week_end=False)[0]

    def test_frozen_signal_does_not_book_historical_open(self):
        state = self.first()
        self.assertEqual(state["strategies"]["lgbm_return"]["trades"], [])
        self.assertFalse(state["strategies"]["lgbm_return"]["positions"])
        self.assertEqual(len(state["strategies"]["lgbm_return"]["pending"]), 1)
        second, changed = freeze_signal(self.config, self.signal(), state)
        self.assertFalse(changed)
        self.assertEqual(second, state)
        with self.assertRaisesRegex(ValueError, "revisada"):
            changed_signal = self.signal()
            changed_signal["models"]["lgbm_return"]["AAA"]["predicted_return"] = 0.03
            freeze_signal(self.config, changed_signal, state)

    def test_open_day_marks_position_and_costs_then_closes_on_friday(self):
        state = self.monday()
        book = state["strategies"]["lgbm_return"]
        self.assertTrue(book["positions"])
        self.assertFalse(book["pending"])
        self.assertEqual(book["equity"][-1]["date"], "2026-10-12")
        self.assertNotEqual(book["nav"], 100000)
        self.assertLess(book["cash"], 100000)
        self.assertEqual(len(book["trades"]), 0)
        for day, prev, close in [
            ("2026-10-13", "2026-10-12", 106),
            ("2026-10-14", "2026-10-13", 104),
            ("2026-10-15", "2026-10-14", 103),
            ("2026-10-16", "2026-10-15", 110)
        ]:
            state, changed = process_day(self.config, state, day,
                       {"AAA": {"open": 103, "close": close},
                        "SPY": {"open": 710, "close": 705},
                        "RSP": {"open": 204, "close": 205}},
                       previous_session=prev, first_after_signal=False,
                       week_end=(day == "2026-10-16"))
            self.assertTrue(changed)
        book = state["strategies"]["lgbm_return"]
        self.assertFalse(book["positions"])
        self.assertAlmostEqual(book["cash"], book["nav"])
        self.assertEqual(len(book["trades"]), 1)
        self.assertEqual(book["trades"][0]["entry_date"], "2026-10-12")
        self.assertEqual(book["trades"][0]["exit_date"], "2026-10-16")
        self.assertEqual(len(book["equity"]), 6)
        self.assertEqual([e["date"] for e in book["equity"][-5:]],
                         ["2026-10-12","2026-10-13","2026-10-14","2026-10-15","2026-10-16"])
        state2, changed = freeze_signal(self.config, self.signal("2026-10-16"), state)
        self.assertTrue(changed)
        self.assertEqual(state2["last_signal_session"], "2026-10-16")
        self.assertEqual(state2["strategies"]["lgbm_return"]["nav"], book["nav"])

    def test_missing_open_or_missing_bar_fails_atomically(self):
        state = self.first()
        before = copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError, "Sesión perdida"):
            process_day(self.config, state, "2026-10-13", {},
                        previous_session="2026-10-12", first_after_signal=True,
                        week_end=False)
        with self.assertRaisesRegex(ValueError, "Barra OHLC ausente"):
            process_day(self.config, state, "2026-10-12",
                        {"SPY": {"open": 700, "close": 705},
                         "RSP": {"open": 200, "close": 201}},
                        previous_session="2026-10-09", first_after_signal=True,
                        week_end=False)
        self.assertEqual(state, before)

    def test_idempotence(self):
        state = self.monday()
        again, changed = process_day(self.config, state, "2026-10-12", {},
                        previous_session="2026-10-09", first_after_signal=True,
                        week_end=False)
        self.assertFalse(changed)
        self.assertEqual(again, state)

    def test_refuse_old_signal(self):
        forecast = self.signal("2026-10-02")
        result, changed = freeze_signal(self.config, forecast)
        self.assertIsNone(result)
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
