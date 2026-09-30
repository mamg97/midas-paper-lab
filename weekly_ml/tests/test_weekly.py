import math
import unittest
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weekly_ml"))

from data import build_dataset
from paper import advance


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


if __name__ == "__main__":
    unittest.main()
