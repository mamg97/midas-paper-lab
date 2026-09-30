import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weekly_ml"))

from bootstrap import _portfolio_snapshot


class BootstrapSnapshotTests(unittest.TestCase):
    def test_replay_enters_on_first_session_after_signal_and_marks_requested_close(self):
        frame = pd.DataFrame(
            {
                "open": [100.0, 101.0, 103.0],
                "high": [101.0, 104.0, 105.0],
                "low": [99.0, 100.0, 102.0],
                "close": [100.0, 103.0, 104.0],
                "volume": [1_000_000, 1_100_000, 1_200_000],
            },
            index=pd.to_datetime(["2026-09-25", "2026-09-28", "2026-09-29"]),
        )
        policy = {
            "capital": 100000.0,
            "commission": 0.001,
            "slippage": 0.0005,
            "invest_fraction": 0.95,
            "max_entry_weight": 0.12,
            "fractional_shares": True,
            "share_precision": 6,
            "min_notional": 10.0,
        }
        book = {"pending": [{"ticker": "AAA", "signal_date": "2026-09-25", "score": 1.0}]}
        result = _portfolio_snapshot(
            "lgbm_return", book, {"AAA": frame}, policy, "2026-09-25", "2026-09-28"
        )
        self.assertEqual(len(result["positions"]), 1)
        position = result["positions"][0]
        self.assertEqual(position["entry_date"], "2026-09-28")
        self.assertEqual(position["mark_date"], "2026-09-28")
        self.assertAlmostEqual(position["raw_open"], 101.0)
        self.assertAlmostEqual(position["mark_close"], 103.0)
        self.assertIsInstance(position["quantity"], float)
        self.assertNotEqual(position["quantity"], float(int(position["quantity"])))
        self.assertGreater(result["mark_to_market_nav"], 100000.0)


if __name__ == "__main__":
    unittest.main()
