import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from report import _config_hash, build, markdown


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))
        self.config = {"capital": 100000.0, "strategies": {name: {} for name in self.registry["paper_tracks"]}}
        self.now = datetime(2026, 9, 28, tzinfo=timezone.utc)

    def test_missing_runs_are_explicit_and_have_no_returns(self):
        result = build(self.registry, self.config, now=self.now)
        self.assertEqual(result["counts"], {"paper_with_diary": 0, "legacy_with_diary": 0,
                                             "tfm_with_diary": 0, "weekly_ml_with_diary": 0,
                                             "tfg_with_diary": 0,
                                             "historical_pending": len(self.registry["historical_ideas"])})
        self.assertTrue(all(item["return_pct"] is None for item in result["tracks"]))
        self.assertTrue(all(item["day_return_pct"] is None for item in result["tracks"]))
        self.assertEqual({item["id"]: item["provenance"] for item in result["tracks"]},
                         self.registry["provenance"])
        self.assertIn("TFM: red LSTM", markdown(result))
        self.assertIn("| Procedencia |", markdown(result))

    def test_paper_and_legacy_are_separate_groups(self):
        paper = {"config_hash": _config_hash(self.config), "first_session": "2026-09-28",
                 "last_session": "2026-09-29", "strategies": {
                     name: {"status": "active", "equity": [{"date": "2026-09-29", "nav": 101000.0}]}
                     for name in self.registry["paper_tracks"]}}
        legacy = {"initial_capital": 100000.0,
                  "equity_history": {"2026-02-27": 99638.0, "2026-09-25": 104382.0}}
        result = build(self.registry, self.config, paper, legacy, self.now)
        self.assertEqual(result["counts"]["paper_with_diary"], 9)
        self.assertEqual(result["counts"]["legacy_with_diary"], 1)
        old = next(x for x in result["tracks"] if x["id"] == "genetic_sp500_legacy")
        new = next(x for x in result["tracks"] if x["id"] == "genetic_frozen")
        self.assertEqual((old["first_session"], old["last_session"], old["return_pct"]),
                         ("2026-02-27", "2026-09-25", 4.382))
        self.assertEqual((new["first_session"], new["last_session"], new["return_pct"]),
                         ("2026-09-28", "2026-09-29", 1.0))
        self.assertIn("no forman una clasificación común", markdown(result))

    def test_daily_change_uses_previous_valuation_and_preserves_first_day_unknown(self):
        paper = {"config_hash": _config_hash(self.config), "first_session": "2026-09-28",
                 "last_session": "2026-09-29", "strategies": {
                     name: {"status": "active", "equity": [
                         {"date": "2026-09-28", "nav": 100000.0},
                         {"date": "2026-09-29", "nav": 101000.0}]}
                     for name in self.registry["paper_tracks"]}}
        result = build(self.registry, self.config, paper, now=self.now)
        row = next(x for x in result["tracks"] if x["id"] == "benchmark_spy")
        self.assertEqual((row["day_return_pct"], row["return_pct"], row["currency"]), (1.0, 1.0, "USD"))
        self.assertEqual(row["equity_history"], [
            {"date": "2026-09-28", "nav": 100000.0},
            {"date": "2026-09-29", "nav": 101000.0}
        ])
        paper["strategies"]["benchmark_spy"]["equity"] = [{"date": "2026-09-29", "nav": 101000.0}]
        result = build(self.registry, self.config, paper, now=self.now)
        row = next(x for x in result["tracks"] if x["id"] == "benchmark_spy")
        self.assertIsNone(row["day_return_pct"])

    def test_foreign_paper_state_is_rejected(self):
        paper = {"config_hash": "invalid", "strategies": {name: {} for name in self.registry["paper_tracks"]}}
        with self.assertRaisesRegex(ValueError, "otra configuración"):
            build(self.registry, self.config, paper, now=self.now)
        bad = copy.deepcopy(self.registry)
        bad["historical_ideas"].append(copy.deepcopy(bad["historical_ideas"][0]))
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            build(bad, self.config, now=self.now)
        bad = copy.deepcopy(self.registry)
        del bad["provenance"]["genetic_sp500_legacy"]
        with self.assertRaisesRegex(ValueError, "Procedencia incompleta"):
            build(bad, self.config, now=self.now)

    def test_tfm_adaptation_is_labelled_and_uses_separate_eur_ledger(self):
        tfm_config = {"models": ["lgbm", "mlp", "lstm", "arima"],
                      "paper_policy": {"capital": 100000.0}}
        tfm = {"config_hash": _config_hash(tfm_config), "first_session": "2026-09-28",
               "last_session": "2026-09-29", "models": {
                   name: {"nav": 100250.0, "equity": [{"date": "2026-09-29", "nav": 100250.0}]}
                   for name in tfm_config["models"]}}
        result = build(self.registry, self.config, now=self.now,
                       tfm_config=tfm_config, tfm_state=tfm)
        self.assertEqual(result["counts"]["tfm_with_diary"], 4)
        self.assertEqual(result["counts"]["paper_with_diary"], 0)
        self.assertEqual(result["counts"]["historical_pending"], 17)
        self.assertIn("TimesFM: predictor zero-shot", markdown(result))
        lstm = next(row for row in result["tracks"] if row["id"] == "tfm_lstm_2023")
        self.assertEqual((lstm["group"], lstm["return_pct"]), ("tfm_demo_adaptado", .25))
        self.assertIn("versión corregida 2026", lstm["label"])
        tfm["config_hash"] = "invalid"
        with self.assertRaisesRegex(ValueError, "otra configuración"):
            build(self.registry, self.config, now=self.now,
                  tfm_config=tfm_config, tfm_state=tfm)


    def test_weekly_ml_adaptation_uses_separate_usd_ledger(self):
        weekly_config = {"models": ["lgbm_return", "lgbm_direction", "lgbm_ranker",
                                     "mlp_return", "lstm_return", "arima_return",
                                     "ensemble_consensus"],
                         "currency": "USD", "paper_policy": {"capital": 100000.0}}
        keys = list(self.registry["weekly_ml_tracks"])
        weekly = {"config_hash": _config_hash(weekly_config), "first_session": "2026-10-02",
                  "last_session": "2026-10-09", "strategies": {
                      key: {"nav": 101000.0,
                            "equity": [{"date": "2026-10-02", "nav": 100000.0},
                                       {"date": "2026-10-09", "nav": 101000.0}]}
                      for key in keys}}
        result = build(self.registry, self.config, now=self.now,
                       weekly_config=weekly_config, weekly_state=weekly)
        self.assertEqual(result["counts"]["weekly_ml_with_diary"], 9)
        ensemble = next(row for row in result["tracks"] if row["id"] == "weekly_ml_ensemble_2026")
        self.assertEqual((ensemble["group"], ensemble["return_pct"], ensemble["day_return_pct"]),
                         ("weekly_ml_demo", 1.0, 1.0))
        self.assertEqual(ensemble["currency"], "USD")
        self.assertEqual(ensemble["equity_history"][-1], {"date": "2026-10-09", "nav": 101000.0})


    def test_tfg_corrected_uses_separate_weekly_ledger(self):
        tfg_config = {
            "name": "TFG_2021_corrected_2026",
            "currency": "USD",
            "portfolio": {"capital": 100000.0}
        }
        tfg = {
            "config_hash": _config_hash(tfg_config),
            "first_signal_session": "2026-10-02",
            "last_signal_session": "2026-10-09",
            "nav": 101500.0,
            "equity": [
                {"date": "2026-10-02", "nav": 100000.0},
                {"date": "2026-10-09", "nav": 101500.0}
            ]
        }
        result = build(self.registry, self.config, now=self.now,
                       tfg_config=tfg_config, tfg_state=tfg)
        self.assertEqual(result["counts"]["tfg_with_diary"], 1)
        row = next(x for x in result["tracks"] if x["id"] == "tfg_corrected_2026")
        self.assertEqual(row["group"], "tfg_demo_adaptado")
        self.assertEqual(row["return_pct"], 1.5)
        self.assertEqual(row["day_return_pct"], 1.5)
        self.assertEqual(row["currency"], "USD")
        self.assertEqual(row["equity_history"][-1], {"date": "2026-10-09", "nav": 101500.0})
        self.assertIn("TFG corregido 2026", markdown(result))


if __name__ == "__main__":
    unittest.main()
