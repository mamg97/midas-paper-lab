import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import STRATEGY_ID, advance, digest


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    def bars(self, px):
        return {
            "AAA": {"open": px, "high": px, "low": px, "close": px,
                    "volume": 1000.0, "dividend": 0.0, "split": 0.0},
            "SPY": {"open": 500.0, "high": 500.0, "low": 500.0, "close": 500.0,
                    "volume": 1000.0, "dividend": 0.0, "split": 0.0},
        }

    def test_signal_then_next_open_fill(self):
        decision = {
            "signal_date": "2026-10-01",
            "expected_fill_session": "2026-10-02",
            "target_weights": {"AAA": 0.50},
            "sectors": {"AAA": "Industrials"},
            "selected": [],
            "invest_fraction": 0.50,
            "coverage": {},
            "exit_reasons": {},
        }
        state, changed = advance(
            self.config, self.bars(100.0), "2026-10-01", 500.0,
            decision=decision, state=None,
        )
        self.assertTrue(changed)
        self.assertEqual(state["strategy_id"], STRATEGY_ID)
        self.assertEqual(state["positions"], {})
        self.assertIsNotNone(state["pending"])

        state2, changed2 = advance(
            self.config, self.bars(101.0), "2026-10-02", 500.0,
            state=state,
        )
        self.assertTrue(changed2)
        self.assertIn("AAA", state2["positions"])
        self.assertIsNone(state2["pending"])
        self.assertLess(state2["cash"], self.config["paper_policy"]["capital"])

    def test_foreign_or_modified_config_is_rejected(self):
        state, _ = advance(self.config, self.bars(100.0), "2026-10-01", 500.0)
        bad = copy.deepcopy(self.config)
        bad["paper_policy"]["commission"] = 0.0
        with self.assertRaisesRegex(ValueError, "campaña nueva"):
            advance(bad, self.bars(100.0), "2026-10-02", 500.0, state=state)
        state["strategy_id"] = "other"
        state["config_hash"] = digest(self.config)
        with self.assertRaisesRegex(ValueError, "no reconocido"):
            advance(self.config, self.bars(100.0), "2026-10-02", 500.0, state=state)


if __name__ == "__main__":
    unittest.main()
