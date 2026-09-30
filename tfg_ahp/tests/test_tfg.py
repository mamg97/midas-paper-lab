import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tfg_ahp"))

import data
from paper import advance


def price_frame(dates, opens, closes):
    opens = np.asarray(opens, dtype=float)
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "open": opens,
        "high": np.maximum(opens, closes) * 1.01,
        "low": np.minimum(opens, closes) * 0.99,
        "close": closes,
        "volume": np.full(len(dates), 1_000_000.0),
    }, index=pd.to_datetime(dates))


class TfgSignalTests(unittest.TestCase):
    def test_literal_tfg_rsi_counts_up_days_not_return_magnitude(self):
        up = pd.Series(np.arange(1.0, 31.0))
        down = pd.Series(np.arange(31.0, 1.0, -1.0))
        self.assertAlmostEqual(float(data._tfg_rsi(up, 14).iloc[-1]), 100.0)
        self.assertAlmostEqual(float(data._tfg_rsi(down, 14).iloc[-1]), 0.0)

    def test_corrected_multicriteria_builds_fifteen_capped_positions(self):
        dates = pd.bdate_range("2025-06-02", periods=320)
        t = np.arange(len(dates), dtype=float)
        spy_close = 100 * np.exp(0.0003 * t + 0.003 * np.sin(t / 11))
        panel = {
            "SPY": price_frame(dates, spy_close * 0.999, spy_close),
            "RSP": price_frame(dates, spy_close * 0.998, spy_close * 1.001),
        }
        meta = {}
        tickers = []
        for i in range(20):
            ticker = f"T{i:02d}"
            tickers.append(ticker)
            drift = 0.00015 + i * 0.000015
            close = (50 + i) * np.exp(drift * t + 0.004 * np.sin(t / (8 + i / 8)))
            panel[ticker] = price_frame(dates, close * 0.999, close)
            meta[ticker] = {"security": ticker, "sector": "Test"}

        config = {
            "technical": {
                "window_days": 35, "macd_threshold": .8, "rsi_threshold": .9,
                "stochastic_threshold": .9, "bollinger_threshold": .9,
            },
            "multicriteria": {
                "return_days": 40, "risk_days": 252, "beta_days": 252,
                "top_n": 20,
                "weights": {"return": 1/3, "low_volatility": 1/3, "low_beta": 1/3},
            },
            "portfolio": {
                "top_n": 15, "risk_aversion": 1.0, "invest_fraction": .95,
                "max_position_weight": .15,
            },
        }
        technical = {
            "macd_ratio": .9, "rsi_ratio": 0.0, "stochastic_ratio": 0.0,
            "bollinger_ratio": 0.0, "macd_pass": True, "rsi_pass": False,
            "stochastic_pass": False, "bollinger_pass": False, "technical_pass": True,
        }
        with patch("data._technical_metrics", return_value=technical):
            signal = data.build_signal(
                config, panel, meta, tickers, dates[-1].date().isoformat()
            )
        self.assertEqual(signal["status"], "signal")
        self.assertEqual(len(signal["selections"]), 15)
        total = sum(row["weight"] for row in signal["selections"])
        self.assertLessEqual(total, .950001)
        self.assertTrue(all(row["weight"] <= .150001 for row in signal["selections"]))
        self.assertTrue(all(np.isfinite(row["beta_spy"]) for row in signal["selections"]))


class TfgPaperTests(unittest.TestCase):
    def config(self, stop=-.012):
        return {
            "currency": "USD",
            "portfolio": {
                "capital": 100000.0,
                "commission": .001,
                "slippage": .0005,
                "fractional_shares": True,
                "share_precision": 6,
                "min_notional": 10.0,
                "portfolio_stop_pct": stop,
            },
        }

    def signal(self, asof="2026-09-25"):
        return {
            "asof": asof,
            "status": "signal",
            "selections": [
                {"ticker": "AAA", "weight": .475},
                {"ticker": "BBB", "weight": .475},
            ],
        }

    def panel(self, monday_close=101.0, tuesday_open=102.0):
        dates = ["2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]
        aaa_open = [100, 100, tuesday_open, 103, 104, 105]
        aaa_close = [100, monday_close, 103, 104, 105, 106]
        bbb_open = [50, 50, tuesday_open / 2, 51.5, 52, 52.5]
        bbb_close = [50, monday_close / 2, 51.5, 52, 52.5, 53]
        return {
            "AAA": price_frame(dates, aaa_open, aaa_close),
            "BBB": price_frame(dates, bbb_open, bbb_close),
        }

    def test_next_week_fractional_entry_and_week_end_exit(self):
        config = self.config(stop=-.50)
        first, _ = advance(config, self.panel(), self.signal(), None)
        second_signal = {"asof": "2026-10-02", "status": "no_data", "selections": []}
        second, changed = advance(config, self.panel(), second_signal, first)
        self.assertTrue(changed)
        trade = second["trades"][0]
        self.assertEqual(trade["entry_date"], "2026-09-28")
        self.assertEqual(trade["exit_date"], "2026-10-02")
        self.assertEqual(trade["exit_reason"], "week_end")
        self.assertEqual(len(trade["positions"]), 2)
        self.assertTrue(all(isinstance(p["quantity"], float) for p in trade["positions"]))
        self.assertTrue(any(p["quantity"] != float(int(p["quantity"])) for p in trade["positions"]))
        self.assertGreater(second["nav"], 100000.0)

    def test_portfolio_stop_exits_at_next_open_not_same_close(self):
        config = self.config(stop=-.012)
        falling = self.panel(monday_close=96.0, tuesday_open=95.0)
        first, _ = advance(config, falling, self.signal(), None)
        second_signal = {"asof": "2026-10-02", "status": "no_data", "selections": []}
        second, _ = advance(config, falling, second_signal, first)
        trade = second["trades"][0]
        self.assertEqual(trade["stop_observed_date"], "2026-09-28")
        self.assertEqual(trade["exit_date"], "2026-09-29")
        self.assertEqual(trade["exit_reason"], "portfolio_stop_next_open")
        self.assertTrue(all(p["exit_mode"] == "open" for p in trade["positions"]))


if __name__ == "__main__":
    unittest.main()
