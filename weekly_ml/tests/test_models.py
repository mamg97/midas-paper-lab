import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "weekly_ml"))

from data import FEATURES
from models import fit_predict


class WeeklyModelSmokeTests(unittest.TestCase):
    def test_all_experts_and_ensemble_fit_on_chronological_fixture(self):
        rng = np.random.default_rng(42)
        tickers = [f"T{i:02d}" for i in range(24)]
        sectors = ["Technology", "Health Care", "Industrials", "Financials"]
        dates = pd.date_range("2024-01-05", periods=82, freq="W-FRI")
        rows = []
        for w, signal in enumerate(dates[:-1]):
            for i, ticker in enumerate(tickers):
                values = rng.normal(0, 0.08, size=len(FEATURES))
                feature = dict(zip(FEATURES, values))
                target = (
                    0.035 * feature["ret_21d"]
                    + 0.020 * feature["relative_63d"]
                    - 0.010 * feature["vol_20d"]
                    + rng.normal(0, 0.012)
                )
                rows.append({
                    "ticker": ticker,
                    "sector": sectors[i % len(sectors)],
                    "signal_date": signal.date().isoformat(),
                    "target_end_date": dates[w + 1].date().isoformat(),
                    "target_return": float(target),
                    "target_positive": int(target > 0),
                    **feature,
                })
        labelled = pd.DataFrame(rows)
        live_rows = []
        live_date = dates[-1]
        for i, ticker in enumerate(tickers):
            values = rng.normal(0, 0.08, size=len(FEATURES))
            live_rows.append({
                "ticker": ticker,
                "sector": sectors[i % len(sectors)],
                "signal_date": live_date.date().isoformat(),
                **dict(zip(FEATURES, values)),
            })
        live = pd.DataFrame(live_rows)
        config = {
            "validation_weeks": 10,
            "models": ["lgbm_return", "lgbm_direction", "lgbm_ranker",
                       "mlp_return", "lstm_return", "arima_return",
                       "ensemble_consensus"],
            "training": {
                "seed": 42,
                "lgbm_estimators": 30,
                "lgbm_learning_rate": 0.05,
                "mlp_hidden": [16],
                "mlp_max_iter": 40,
                "lstm_units": 8,
                "lstm_epochs": 1,
                "lstm_batch_size": 256,
                "arima_order": [1, 0, 0],
            },
        }
        predictions, validation, training = fit_predict(config, labelled, live)
        self.assertEqual(set(predictions), set(config["models"]))
        self.assertEqual(set(validation), set(config["models"]))
        for model in config["models"]:
            self.assertEqual(set(predictions[model]), set(tickers))
        self.assertLess(training["train_last_target"], training["validation_first_signal"])
        for ticker, values in predictions["ensemble_consensus"].items():
            self.assertTrue(0 <= values["score"] <= 1)
            self.assertTrue(0 <= values["positive_votes"] <= 5)
            self.assertTrue(np.isfinite(values["predicted_return"]))


if __name__ == "__main__":
    unittest.main()
