import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factors import fundamental_features, price_features, score_universe, choose_portfolio


def prices(start, drift, n=900):
    out = [float(start)]
    for _ in range(1, n):
        out.append(max(1.0, out[-1] * (1.0 + drift)))
    return out


def fundamental(asset_growth=0.0, capex_latest=25, capex_prior=60, ocf=120, debt=100, cash=30,
                operating=100, market_cap=1000, equity=500):
    rows = []
    assets = [1000, 1000 / (1 + asset_growth), 950, 900]
    capex = [capex_latest, capex_prior, capex_prior, capex_prior]
    for i in range(4):
        rows.append({
            "date": f"{2025-i}-12-31",
            "assets": assets[i],
            "equity": equity,
            "debt": debt,
            "cash": cash,
            "revenue": 1000,
            "operating_income": operating,
            "interest_expense": 20,
            "ocf": ocf,
            "capex": capex[i],
        })
    return {"market_cap": market_cap, "periods": rows}


class FactorTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "cycle_model": {
                "minimum_capex_to_revenue": .02,
                "entry_score": 55.0,
                "retention_score": 45.0,
                "hard_exit_score": 30.0,
                "minimum_quality_score": 35.0,
                "minimum_sector_scarcity_score": 20.0,
                "inflection_min_votes": 2,
                "hard_exit_inflection_votes": 0,
                "minimum_positive_fcf_years": 2,
                "maximum_net_debt_to_ocf": 6.0,
                "minimum_interest_coverage": 1.0,
                "minimum_hold_months": 3,
                "weights": {"capital_scarcity": .45, "survivor_quality": .30,
                            "valuation": .15, "inflection": .10},
            },
            "paper_policy": {
                "max_positions": 3, "max_sector_positions": 2,
                "max_position_weight": .10, "invest_fraction": .95,
            },
        }

    def test_price_features_require_recovery_not_falling_knife(self):
        benchmark = prices(100, .00015)
        falling = prices(200, -.00025)
        rising = prices(100, .00035)
        self.assertEqual(price_features(falling, benchmark)["inflection_votes"], 0)
        self.assertEqual(price_features(rising, benchmark)["inflection_votes"], 3)

    def test_fundamental_features_detect_capital_withdrawal(self):
        row = fundamental_features(fundamental(capex_latest=20, capex_prior=60))
        self.assertLess(row["capex_contraction"], 0)
        self.assertGreaterEqual(row["positive_fcf_years"], 2)
        self.assertGreater(row["normalized_fcf_yield"], 0)

    def test_distress_without_quality_is_not_an_entry(self):
        benchmark = prices(100, .00015)
        weak_then_recover = [200 * (0.9995 ** i) for i in range(550)]
        last = weak_then_recover[-1]
        weak_then_recover += [last * (1.0012 ** i) for i in range(1, 351)]
        candidates = []
        for i in range(8):
            sector = "Energy" if i < 4 else "Materials"
            f = fundamental(asset_growth=-.03 + i * .005, capex_latest=20 + i,
                            capex_prior=60, ocf=130 - i * 2, debt=100, market_cap=900 + i * 20)
            candidates.append({"ticker": f"Q{i}", "sector": sector,
                               "close": [x * (1 + i * .00001) for x in weak_then_recover],
                               "benchmark_close": benchmark, "fundamental": f})
        junk = fundamental(asset_growth=-.10, capex_latest=10, capex_prior=80,
                           ocf=-20, debt=1000, cash=0, operating=-50, market_cap=300)
        candidates.append({"ticker": "JUNK", "sector": "Energy",
                           "close": weak_then_recover, "benchmark_close": benchmark,
                           "fundamental": junk})
        scored = score_universe(candidates, self.config)
        bad = next(x for x in scored if x["ticker"] == "JUNK")
        self.assertFalse(bad["entry_eligible"])
        self.assertTrue(bad["hard_exit"])

    def test_choose_portfolio_respects_sector_cap_and_hysteresis(self):
        rows = []
        for ticker, sector, score in [
            ("A","Energy",90),("B","Energy",85),("C","Energy",80),
            ("D","Materials",79),("E","Materials",75)
        ]:
            rows.append({"ticker": ticker, "sector": sector, "composite_score": score,
                         "entry_eligible": True, "hard_exit": False})
        targets, exits = choose_portfolio(rows, {}, "2026-09-30", self.config)
        self.assertEqual(len(targets), 3)
        self.assertLessEqual(sum(1 for t in targets if t in {"A","B","C"}), 2)
        self.assertAlmostEqual(sum(targets.values()), .30, places=8)


if __name__ == "__main__":
    unittest.main()
