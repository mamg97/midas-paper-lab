import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
import sys
import types
from unittest.mock import patch
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import advance, leaderboard
from run import run
from market import live_snapshot


def config(stop=None, target=None):
    return {"schema_version": 1, "currency": "USD", "tickers": ["AAPL"], "capital": 1000.0,
            "commission": 0.001, "slippage": 0.0, "invest_fraction": 1.0,
            "max_positions": 1, "max_entry_weight": 1.0,
            "strategies": {"hold": {"kind": "equal_weight_hold", "stop_loss": stop, "take_profit": target}}}


def bars(count=83):
    output = []
    day = date(2025, 1, 1)
    while len(output) < count:
        if day.weekday() < 5:
            output.append({"date": day.isoformat(), "open": 100.0, "high": 100.0,
                           "low": 100.0, "close": 100.0, "volume": 1000.0,
                           "dividend": 0.0, "split": 0.0})
        day += timedelta(days=1)
    return output


def snapshot(rows):
    return {"schema_version": 1, "asof": rows[-1]["date"], "currency": "USD",
            "source": "test", "synthetic": True, "bars": {"AAPL": rows}}


class PaperTests(unittest.TestCase):
    def test_first_close_only_queues_then_next_open_fills(self):
        cfg, rows = config(), bars()
        first, changed = advance(cfg, snapshot(rows[:80]))
        self.assertTrue(changed)
        book = first["strategies"]["hold"]
        self.assertEqual(book["cash"], 1000)
        self.assertEqual(book["positions"], {})
        self.assertEqual(book["pending"]["AAPL"]["signal_date"], rows[79]["date"])
        rows[80].update(open=105.0, high=110.0, low=104.0, close=108.0)
        second, _ = advance(cfg, snapshot(rows[:81]), first)
        fill = next(e for e in second["strategies"]["hold"]["events"] if e["type"] == "fill")
        self.assertEqual(fill["date"], rows[80]["date"])
        self.assertEqual(fill["signal_date"], rows[79]["date"])
        self.assertEqual(fill["price"], 105.0)
        self.assertAlmostEqual(second["strategies"]["hold"]["cash"], 0)

    def test_idempotence_and_missing_session_fail_closed(self):
        cfg, rows = config(), bars()
        first, _ = advance(cfg, snapshot(rows[:80]))
        duplicate, changed = advance(cfg, snapshot(rows[:80]), first)
        self.assertFalse(changed)
        self.assertEqual(duplicate, first)
        with self.assertRaisesRegex(ValueError, "Demasiadas sesiones"):
            advance(cfg, snapshot(rows[:82]), first)
        revised = [dict(row) for row in rows[:80]]
        revised[-1]["close"] = 99.0
        revised[-1]["low"] = 99.0
        with self.assertRaisesRegex(ValueError, "revisados"):
            advance(cfg, snapshot(revised), first)
        changed_source = snapshot(rows[:81])
        changed_source["source"] = "different"
        with self.assertRaisesRegex(ValueError, "Proveedor"):
            advance(cfg, changed_source, first)

    def test_stop_first_when_daily_bar_hits_both(self):
        cfg, rows = config(.1, .1), bars()
        first, _ = advance(cfg, snapshot(rows[:80]))
        rows[80].update(high=115.0, low=85.0)
        second, _ = advance(cfg, snapshot(rows[:81]), first)
        fills = [e for e in second["strategies"]["hold"]["events"] if e["type"] == "fill"]
        self.assertEqual([(x["side"], x["reason"], x["price"]) for x in fills],
                         [("buy", "close_signal", 100.0), ("sell", "stop_intraday", 90.0)])
        self.assertLess(leaderboard(cfg, second)[0]["return_pct"], -10)

    def test_split_and_dividend_adjust_holdings(self):
        cfg, rows = config(), bars()
        first, _ = advance(cfg, snapshot(rows[:80]))
        second, _ = advance(cfg, snapshot(rows[:81]), first)
        old_qty = second["strategies"]["hold"]["positions"]["AAPL"]["quantity"]
        rows[81].update(open=50.0, high=50.0, low=50.0, close=50.0, split=2.0, dividend=1.0)
        third, _ = advance(cfg, snapshot(rows[:82]), second)
        book = third["strategies"]["hold"]
        self.assertAlmostEqual(book["positions"]["AAPL"]["quantity"], old_qty * 2)
        self.assertAlmostEqual(book["equity"][-1]["nav"], old_qty * 102)
        self.assertEqual([e["type"] for e in book["events"] if e["type"] in ("split", "dividend")],
                         ["split", "dividend"])

    def test_corrupt_state_is_not_overwritten_and_config_locked(self):
        cfg, rows = config(), bars()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            c, s = root / "config.json", root / "snapshot.json"
            c.write_text(json.dumps(cfg), encoding="utf-8")
            s.write_text(json.dumps(snapshot(rows[:80])), encoding="utf-8")
            run(c, root / "campaign", s)
            state_path = root / "campaign" / "state.json"
            state_path.write_text("{bad json", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                run(c, root / "campaign", s)
            self.assertEqual(state_path.read_text(encoding="utf-8"), "{bad json")
        first, _ = advance(cfg, snapshot(rows[:80]))
        altered = config()
        altered["commission"] = .002
        with self.assertRaisesRegex(ValueError, "Configuración modificada"):
            advance(altered, snapshot(rows[:81]), first)

    def test_waiting_model_cannot_borrow_another_strategy_cash(self):
        cfg, rows = config(), bars()
        cfg["strategies"]["genetic"] = {"kind": "genetic_frozen", "params": None,
                                         "stop_loss": None, "take_profit": None}
        first, _ = advance(cfg, snapshot(rows[:80]))
        second, _ = advance(cfg, snapshot(rows[:81]), first)
        self.assertEqual(second["strategies"]["genetic"]["status"], "waiting_for_model")
        self.assertEqual(second["strategies"]["genetic"]["cash"], 1000)
        self.assertEqual(second["strategies"]["genetic"]["events"], [])
        self.assertLess(second["strategies"]["hold"]["cash"], 1)

    def test_spy_benchmark_is_separate_from_common_stock_universe(self):
        cfg, rows = config(), bars()
        cfg["benchmark_tickers"] = ["SPY"]
        cfg["strategies"]["spy"] = {"kind": "equal_weight_hold", "universe": ["SPY"],
                                      "entry_weight": 1.0, "stop_loss": None, "take_profit": None}
        first_snapshot = snapshot(rows[:80])
        first_snapshot["bars"]["SPY"] = [dict(bar) for bar in rows[:80]]
        first, _ = advance(cfg, first_snapshot)
        next_snapshot = snapshot(rows[:81])
        next_snapshot["bars"]["SPY"] = [dict(bar) for bar in rows[:81]]
        second, _ = advance(cfg, next_snapshot, first)
        self.assertEqual(set(second["strategies"]["hold"]["positions"]), {"AAPL"})
        self.assertEqual(set(second["strategies"]["spy"]["positions"]), {"SPY"})

    def test_one_missed_decision_recovers_only_precommitted_order(self):
        cfg, rows = config(), bars()
        cfg["max_missed_sessions"] = 1
        first, _ = advance(cfg, snapshot(rows[:80]))
        rows[80].update(open=110.0, high=111.0, low=109.0, close=110.0)
        rows[81].update(open=120.0, high=121.0, low=119.0, close=120.0)
        recovered, _ = advance(cfg, snapshot(rows[:82]), first)
        book = recovered["strategies"]["hold"]
        fills = [e for e in book["events"] if e["type"] == "fill"]
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0]["date"], rows[80]["date"])
        self.assertEqual(fills[0]["signal_date"], rows[79]["date"])
        self.assertEqual(recovered["missed_decision_sessions"], [rows[80]["date"]])
        self.assertFalse(book["equity"][-2]["decision_recorded"])
        self.assertTrue(book["equity"][-1]["decision_recorded"])
        self.assertEqual([e["date"] for e in book["events"] if e["type"] == "signal"],
                         [rows[79]["date"], rows[81]["date"]])

    def test_market_holiday_does_not_download_or_change_state(self):
        fake_calendar = types.SimpleNamespace(schedule=lambda **kwargs: types.SimpleNamespace(empty=True))
        fake_module = types.SimpleNamespace(get_calendar=lambda name: fake_calendar)
        with patch.dict(sys.modules, {"pandas_market_calendars": fake_module,
                                      "yfinance": types.SimpleNamespace(Ticker=lambda x: self.fail("download on holiday"))}):
            self.assertIsNone(live_snapshot(config(), datetime(2026, 12, 25, 23, 0, tzinfo=timezone.utc)))


if __name__ == "__main__":
    unittest.main()
