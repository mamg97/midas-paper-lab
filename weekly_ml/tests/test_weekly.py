import json
import math
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weekly_ml"))

from data import build_dataset
from paper import advance, digest
import run as weekly_runner


class WeeklyFeatureTests(unittest.TestCase):
    def test_features_never_use_future_target(self):
        dates = pd.bdate_range("2023-01-02", periods=650)
        panel = {}
        names = ["AAA", "BBB", "CCC", "SPY", "RSP"]
        for offset, ticker in enumerate(names):
            base = 80 + offset * 10
            drift = np.linspace(0, 35 + offset, len(dates))
            wave = np.sin(np.arange(len(dates)) / (12 + offset)) * 2
            close = base + drift + wave
            open_ = close * (1 + 0.001 * np.sin(np.arange(len(dates)) / 7))
            panel[ticker] = pd.DataFrame({
                "open": open_,
                "high": np.maximum(open_, close) * 1.005,
                "low": np.minimum(open_, close) * 0.995,
                "close": close,
                "volume": 1_000_000 + np.arange(len(dates)) * 100,
            }, index=dates)
        asof = dates[-1].date().isoformat()
        labelled, live, excluded = build_dataset(
            panel,
            {"AAA": "Tech", "BBB": "Health", "CCC": "Industrials"},
            ["AAA", "BBB", "CCC"],
            asof,
            minimum_live=3,
        )
        self.assertEqual(set(live["ticker"]), {"AAA", "BBB", "CCC"})
        self.assertEqual(set(live["signal_date"]), {asof})
        self.assertTrue((labelled["target_end_date"] <= asof).all())
        self.assertFalse(excluded)
        changed = {ticker: frame.copy() for ticker, frame in panel.items()}
        future = dates[-1] + pd.offsets.BDay(5)
        for frame in changed.values():
            frame.loc[future] = frame.iloc[-1] * [1.2, 1.2, 1.2, 1.2, 1.0]
        labelled2, live2, _ = build_dataset(
            changed,
            {"AAA": "Tech", "BBB": "Health", "CCC": "Industrials"},
            ["AAA", "BBB", "CCC"],
            asof,
            minimum_live=3,
        )
        pd.testing.assert_frame_equal(labelled, labelled2)
        pd.testing.assert_frame_equal(live, live2)


class WeeklyPaperTests(unittest.TestCase):
    def config(self):
        return {
            "models": ["lgbm_return"],
            "currency": "USD",
            "paper_policy": {
                "capital": 100000.0,
                "commission": 0.001,
                "slippage": 0.0005,
                "invest_fraction": 0.95,
                "max_positions": 10,
                "max_entry_weight": 0.12,
                "min_predicted_return": 0.005,
                "min_direction_probability": 0.55,
                "ensemble_min_positive_votes": 3,
                "fractional_shares": True,
                "share_precision": 6,
                "min_notional": 10.0,
            },
        }

    def frame(self, price):
        dates = pd.to_datetime(["2026-09-18", "2026-09-21", "2026-09-25"])
        return pd.DataFrame({
            "open": [price, price, price],
            "high": [price, price, price],
            "low": [price, price, price],
            "close": [price, price, price],
            "volume": [1_000_000] * 3,
        }, index=dates)

    def test_unquoted_pending_order_cannot_settle_and_keeps_original_book(self):
        config = self.config()
        original_panel = {"AAA": self.frame(100), "SPY": self.frame(500), "RSP": self.frame(180)}
        first = {"asof": "2026-09-18", "models": {
            "lgbm_return": {"AAA": {"predicted_return": 0.02}}}}
        state, _ = advance(config, original_panel, first)
        second = {"asof": "2026-09-25", "models": {"lgbm_return": {}}}
        # A diagnostic metric may skip AAA; an already committed paper order may not.
        with self.assertRaisesRegex(ValueError, "Cotización ausente para liquidar orden paper: AAA"):
            advance(config, {"SPY": self.frame(500), "RSP": self.frame(180)}, second, state)
        self.assertEqual(state["last_session"], "2026-09-18")
        self.assertEqual(state["strategies"]["lgbm_return"]["trades"], [])
        self.assertEqual(len(state["strategies"]["lgbm_return"]["pending"]), 1)

    def test_thursday_quote_cannot_replace_friday_close_for_paper_settlement(self):
        config = self.config()
        panel = {"AAA": self.frame(100), "SPY": self.frame(500), "RSP": self.frame(180)}
        first = {"asof": "2026-09-18", "models": {
            "lgbm_return": {"AAA": {"predicted_return": 0.02}}}}
        state, _ = advance(config, panel, first)
        truncated = panel["AAA"].drop(pd.Timestamp("2026-09-25"))
        truncated.loc[pd.Timestamp("2026-09-24")] = truncated.iloc[-1]
        with self.assertRaisesRegex(ValueError, "cierre semanal completo"):
            advance(config, {**panel, "AAA": truncated},
                    {"asof": "2026-09-25", "models": {"lgbm_return": {}}}, state)
        self.assertEqual(state["strategies"]["lgbm_return"]["trades"], [])

    def test_next_week_open_close_and_costs(self):
        panel = {ticker: self.frame(price) for ticker, price in {
            "AAA": 100.0, "SPY": 500.0, "RSP": 180.0}.items()}
        first = {
            "asof": "2026-09-18",
            "models": {"lgbm_return": {
                "AAA": {"score": 0.02, "predicted_return": 0.02}
            }},
        }
        state, changed = advance(self.config(), panel, first, None)
        self.assertTrue(changed)
        self.assertEqual(len(state["strategies"]["lgbm_return"]["pending"]), 1)
        second = {
            "asof": "2026-09-25",
            "models": {"lgbm_return": {
                "AAA": {"score": 0.02, "predicted_return": 0.02}
            }},
        }
        state2, changed2 = advance(self.config(), panel, second, state)
        self.assertTrue(changed2)
        trade = state2["strategies"]["lgbm_return"]["trades"][0]
        self.assertEqual(trade["first_session"], "2026-09-21")
        self.assertEqual(trade["last_session"], "2026-09-25")
        self.assertIsInstance(trade["quantity"], float)
        self.assertNotEqual(trade["quantity"], float(int(trade["quantity"])))
        self.assertLess(trade["net_pnl"], 0)
        self.assertLess(state2["strategies"]["lgbm_return"]["nav"], 100000.0)
        self.assertEqual(len(state2["strategies"]["benchmark_spy"]["trades"]), 1)





class WeeklyDiagnosticMissingQuoteTests(unittest.TestCase):
    def frame(self, through_friday=True):
        dates = pd.to_datetime(["2026-10-02", "2026-10-05", "2026-10-08", "2026-10-09"])
        if not through_friday:
            dates = dates[:-1]
        return pd.DataFrame({
            "open": [100.0] * len(dates),
            "high": [101.0] * len(dates),
            "low": [99.0] * len(dates),
            "close": [100.0, 101.0, 102.0, 103.0][:len(dates)],
            "volume": [100000] * len(dates),
        }, index=dates)

    def test_missing_ticker_and_incomplete_last_close_are_reported_not_invented(self):
        previous = {
            "asof": "2026-10-02", "live_tickers": ["AAA", "BBB", "WBD"],
            "models": {"lgbm_return": {
                "AAA": {"predicted_return": 0.01},
                "WBD": {"predicted_return": 0.02},
                "BBB": {"predicted_return": 0.02}
            }}
        }
        evaluated = weekly_runner.evaluate(previous, {
            "AAA": self.frame(), "BBB": self.frame(through_friday=False)
        }, "2026-10-09")
        self.assertEqual(evaluated["actual_tickers"], 1)
        self.assertEqual(evaluated["expected_tickers"], 3)
        self.assertEqual(evaluated["missing_tickers"], {
            "BBB": "weekly_final_close_unavailable",
            "WBD": "vendor_history_unavailable"})
        self.assertAlmostEqual(evaluated["metrics"]["lgbm_return"]["mae"],
                               abs(.01 - .03))
        self.assertEqual(evaluated["forecast_asof"], "2026-10-02")

    def test_completely_missing_evaluation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Sin precios observados"):
            weekly_runner.evaluate({
                "asof": "2026-10-02",
                "live_tickers": ["WBD"],
                "models": {"lgbm_return": {"WBD": {"predicted_return": 0.01}}}
            }, {}, "2026-10-09")

    def test_widespread_vendor_data_loss_fails_closed(self):
        previous = {"asof": "2026-10-02",
                    "live_tickers": [f"ASSET{i:03}" for i in range(100)],
                    "models": {}}
        panel = {f"ASSET{i:03}": self.frame() for i in range(80)}
        with self.assertRaisesRegex(ValueError, "Cobertura de evaluación semanal insuficiente"):
            weekly_runner.evaluate(previous, panel, "2026-10-09")


class WeeklyRunnerIdempotencyTests(unittest.TestCase):
    def test_backup_does_not_recompute_a_frozen_weekly_forecast(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = {
                "schema_version": 1,
                "calendar": "XNYS",
                "currency": "USD",
                "universe_file": "weekly_ml/universe.json",
                "models": ["lgbm_return"],
                "paper_policy": {}
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            output = root / "state"
            (output / "forecasts").mkdir(parents=True)
            asof = "2026-10-02"
            forecast = {"schema_version": 1, "asof": asof, "config_hash": digest(config)}
            (output / "forecasts" / (asof + ".json")).write_text(json.dumps(forecast), encoding="utf-8")
            ledger = {
                "config_hash": digest(config),
                "last_session": asof,
                "forecast_hash": digest(forecast)
            }
            (output / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

            snapshot = ({}, {}, [], [], asof)
            with patch.object(weekly_runner, "live_panel", return_value=snapshot), \
                    patch.object(weekly_runner, "build_dataset", side_effect=AssertionError("must not recompute")):
                result = weekly_runner.run(config_path, output)
            self.assertEqual(result["status"], "already_recorded")
            self.assertFalse(result["changed"])


if __name__ == "__main__":
    unittest.main()
