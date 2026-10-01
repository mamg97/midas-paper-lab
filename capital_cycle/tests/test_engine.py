import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import advance


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "schema_version": 1,
            "name": "MIDAS_capital_cycle_inflection_2026",
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

    def bars(self, a=100.0, b=50.0, spy=500.0):
        def one(px):
            return {"open": px, "high": px * 1.02, "low": px * .98, "close": px * 1.01,
                    "volume": 1000000.0, "dividend": 0.0, "split": 0.0}
        return {"AAA": one(a), "BBB": one(b), "SPY": one(spy)}

    def test_signal_at_close_does_not_fill_until_next_open(self):
        decision = {
            "signal_date": "2026-09-30",
            "expected_fill_session": "2026-10-01",
            "target_weights": {"AAA": .10, "BBB": .10},
            "sectors": {"AAA": "Energy", "BBB": "Materials"},
            "selected": [], "sector_scores": {}, "coverage": {},
        }
        state, changed = advance(self.config, self.bars(), "2026-09-30", 505.0,
                                 decision=decision, state=None)
        self.assertTrue(changed)
        self.assertEqual(state["positions"], {})
        self.assertEqual(len(state["pending"]["target_weights"]), 2)
        self.assertEqual(state["equity"][-1]["nav"], 100000.0)

        state2, changed2 = advance(self.config, self.bars(a=101,b=51,spy=506), "2026-10-01",
                                   511.06, decision=None, state=state)
        self.assertTrue(changed2)
        self.assertIsNone(state2["pending"])
        self.assertEqual(set(state2["positions"]), {"AAA","BBB"})
        self.assertLess(state2["cash"], state["cash"])
        self.assertEqual(state2["last_session"], "2026-10-01")

    def test_missed_expected_fill_is_rejected(self):
        decision = {
            "signal_date": "2026-09-30", "expected_fill_session": "2026-10-01",
            "target_weights": {"AAA": .10}, "sectors": {"AAA": "Energy"},
        }
        state, _ = advance(self.config, self.bars(), "2026-09-30", 505.0,
                           decision=decision, state=None)
        with self.assertRaisesRegex(ValueError, "apertura prevista"):
            advance(self.config, self.bars(), "2026-10-02", 505.0, state=state)

    def test_same_session_is_idempotent(self):
        state, _ = advance(self.config, self.bars(), "2026-09-30", 505.0, state=None)
        same, changed = advance(self.config, self.bars(), "2026-09-30", 505.0, state=state)
        self.assertFalse(changed)
        self.assertEqual(same["nav"], state["nav"])

    def test_same_session_ignores_provider_revision_after_freeze(self):
        state, _ = advance(self.config, self.bars(), "2026-09-30", 505.0, state=None)
        revised = self.bars(a=101.0, b=49.0, spy=501.0)
        same, changed = advance(self.config, revised, "2026-09-30", 506.01, state=state)
        self.assertFalse(changed)
        self.assertEqual(same, state)


if __name__ == "__main__":
    unittest.main()
