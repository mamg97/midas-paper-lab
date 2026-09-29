import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weekly_ml"))

from report import build


class WeeklyDashboardTests(unittest.TestCase):
    def test_bootstrap_dashboard_separates_non_forward_results(self):
        bootstrap = {
            "signal_asof": "2026-09-25",
            "entry_date": "2026-09-28",
            "mark_date": "2026-09-28",
            "validation": {"lgbm_direction": {"accuracy": 0.54}},
            "ensemble_top20": [{
                "ticker": "AAA", "score": 0.9, "predicted_return": 0.01,
                "positive_votes": 5, "rank_dispersion": 0.1
            }],
            "strategies": {}
        }
        for key in ["lgbm_return","lgbm_direction","lgbm_ranker","mlp_return",
                    "lstm_return","arima_return","ensemble_consensus","benchmark_spy","benchmark_rsp"]:
            bootstrap["strategies"][key] = {
                "mark_to_market_nav": 100000.0,
                "mark_to_market_return_pct": 0.0,
                "positions": []
            }
        text = build(bootstrap=bootstrap)
        self.assertIn("Aún sin señal forward oficial", text)
        self.assertIn("No cuenta como forward", text)
        self.assertIn("LightGBM Direction", text)
        self.assertIn("AAA", text)

    def test_forward_dashboard_prefers_official_forecast_and_ledger(self):
        models = {
            "lgbm_return": {"AAA": {"predicted_return": 0.02, "score": 0.02}},
            "lgbm_direction": {"AAA": {"direction_probability": 0.60, "score": 0.60}},
            "lgbm_ranker": {"AAA": {"rank_score": 1.2, "score": 1.2}},
            "mlp_return": {"AAA": {"predicted_return": 0.01, "score": 0.01}},
            "lstm_return": {"AAA": {"predicted_return": 0.015, "score": 0.015}},
            "arima_return": {"AAA": {"predicted_return": 0.005, "score": 0.005}},
            "ensemble_consensus": {"AAA": {"score": 0.91, "predicted_return": 0.012,
                                                   "positive_votes": 5, "rank_dispersion": 0.08}},
        }
        forecast = {"asof": "2026-10-02", "models": models, "validation": {}}
        ledger = {"strategies": {}}
        for key in ["lgbm_return","lgbm_direction","lgbm_ranker","mlp_return",
                    "lstm_return","arima_return","ensemble_consensus","benchmark_spy","benchmark_rsp"]:
            ledger["strategies"][key] = {
                "nav": 100500.0,
                "pending": [],
                "trades": [],
                "equity": [{"date": "2026-10-02", "nav": 100000.0},
                           {"date": "2026-10-09", "nav": 100500.0}],
            }
        text = build(forecast=forecast, ledger=ledger)
        self.assertIn("Forward activo", text)
        self.assertIn("2026-10-02", text)
        self.assertIn("100,500.00 USD", text)
        self.assertIn("AAA", text)


if __name__ == "__main__":
    unittest.main()
