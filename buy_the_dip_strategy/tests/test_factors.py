import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from factors import choose_portfolio, months_between


class FactorPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    def row(self, ticker, score, sector="Industrials", eligible=True, hard=False,
            rerated=False, vol=0.30):
        return {
            "ticker": ticker,
            "sector": sector,
            "composite_score": score,
            "entry_eligible": eligible,
            "hard_exit": hard,
            "rerated": rerated,
            "volatility_1y": vol,
        }

    def test_months_between(self):
        self.assertEqual(months_between("2026-01-10", "2026-04-02"), 3)

    def test_sparse_opportunities_leave_cash(self):
        scored = [
            self.row("AAA", 80, "Industrials"),
            self.row("BBB", 75, "Energy"),
            self.row("CCC", 70, "Materials"),
        ]
        targets, exits, invest_fraction = choose_portfolio(
            scored, {}, "2026-10-01", self.config
        )
        self.assertEqual(invest_fraction, 0.50)
        self.assertLessEqual(sum(targets.values()), 0.50 + 1e-9)
        self.assertEqual(exits, {})

    def test_rotation_can_replace_old_position(self):
        positions = {"OLD": {"entry_date": "2026-01-02", "sector": "Industrials"}}
        sectors = ["Energy", "Materials", "Information Technology", "Healthcare", "Consumer Staples"]
        scored = [self.row("NEW", 95, "Energy")]
        scored += [self.row(f"X{i}", 90 - i, sectors[i % len(sectors)]) for i in range(11)]
        scored += [self.row("OLD", 46, "Industrials", eligible=False)]
        targets, exits, _ = choose_portfolio(scored, positions, "2026-10-01", self.config)
        self.assertNotIn("OLD", targets)
        self.assertEqual(exits["OLD"], "rank_replaced")

    def test_hard_exit_ignores_minimum_hold(self):
        positions = {"BAD": {"entry_date": "2026-09-15", "sector": "Energy"}}
        scored = [self.row("BAD", 70, "Energy", eligible=False, hard=True)]
        targets, exits, _ = choose_portfolio(scored, positions, "2026-10-01", self.config)
        self.assertEqual(targets, {})
        self.assertEqual(exits["BAD"], "hard_quality_or_value_exit")

    def test_minimum_hold_position_is_not_rotated_or_forced_to_cash(self):
        positions = {"YOUNG": {"entry_date": "2026-09-15", "sector": "Industrials"}}
        scored = [self.row("YOUNG", 46, "Industrials", eligible=False)]
        targets, exits, invest_fraction = choose_portfolio(
            scored, positions, "2026-10-01", self.config
        )
        self.assertIn("YOUNG", targets)
        self.assertNotIn("YOUNG", exits)
        self.assertEqual(invest_fraction, 0.50)


    def test_caps_are_respected(self):
        scored = [self.row(f"E{i}", 90-i, "Energy", vol=0.15) for i in range(6)]
        scored += [self.row(f"I{i}", 80-i, "Industrials", vol=0.30) for i in range(6)]
        targets, _, _ = choose_portfolio(scored, {}, "2026-10-01", self.config)
        self.assertLessEqual(len(targets), 10)
        self.assertTrue(all(w <= 0.15 + 1e-9 for w in targets.values()))
        energy = sum(w for t, w in targets.items() if t.startswith("E"))
        self.assertLessEqual(energy, 0.30 + 1e-9)


if __name__ == "__main__":
    unittest.main()
