import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import advance
from run import _replay_nondecision_gap


class GapRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "schema_version": 1,
            "name": "MIDAS_capital_cycle_inflection_2026",
            "calendar": "XNYS",
            "currency": "USD",
            "paper_policy": {
                "capital": 100000.0,
                "commission": .001,
                "slippage": .0005,
                "invest_fraction": .95,
                "fractional_shares": True,
                "share_precision": 6,
                "min_notional": 10.0,
            },
        }

    def bars(self, a=100.0, spy=500.0):
        def one(px):
            return {"open": px, "high": px * 1.02, "low": px * .98, "close": px * 1.01,
                    "volume": 1000000.0, "dividend": 0.0, "split": 0.0}
        return {"AAA": one(a), "SPY": one(spy)}

    def frame(self, values):
        index = pd.to_datetime([day for day, _ in values])
        rows = []
        for _, px in values:
            rows.append({"open": px, "high": px * 1.02, "low": px * .98, "close": px * 1.01,
                         "adj_close": px * 1.01, "volume": 1000000.0, "dividend": 0.0, "split": 0.0})
        return pd.DataFrame(rows, index=index)

    def test_replays_missing_nondecision_mark_before_current_session(self):
        decision = {
            "signal_date": "2026-09-30",
            "expected_fill_session": "2026-10-01",
            "target_weights": {"AAA": .50},
            "sectors": {"AAA": "Energy"},
            "selected": [], "sector_scores": {}, "coverage": {},
        }
        state, _ = advance(self.config, self.bars(), "2026-09-30", 505.0, decision=decision, state=None)
        state, _ = advance(self.config, self.bars(a=101, spy=501), "2026-10-01", 506.01, state=state)
        state, _ = advance(self.config, self.bars(a=102, spy=502), "2026-10-02", 507.02, state=state)

        panel = {
            "AAA": self.frame([("2026-10-05", 103.0), ("2026-10-06", 104.0)]),
            "SPY": self.frame([("2026-10-05", 503.0), ("2026-10-06", 504.0)]),
        }
        recovered, count = _replay_nondecision_gap(self.config, panel, "SPY", state, "2026-10-06")
        self.assertEqual(count, 1)
        self.assertEqual(recovered["last_session"], "2026-10-05")
        self.assertEqual(recovered["equity"][-1]["date"], "2026-10-05")
        self.assertEqual(len(recovered["equity"]), len(state["equity"]) + 1)


if __name__ == "__main__":
    unittest.main()
