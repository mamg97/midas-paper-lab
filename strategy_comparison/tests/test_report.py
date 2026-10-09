import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from report import _config_hash, _activity, build, markdown


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))
        self.config = {"capital": 100000.0, "strategies": {name: {} for name in self.registry["paper_tracks"]}}
        self.now = datetime(2026, 9, 28, tzinfo=timezone.utc)

    def test_activity_uses_singular_for_one_pending_order_or_signal(self):
        order = _activity(None, [{"ticker": "ABC"}], pending_label="compras para próxima apertura")
        signal = _activity(None, [{"ticker": "XYZ"}], pending_label="señales congeladas · liquidación semanal pendiente")
        mixed = _activity({"AAA": {"shares": 10}}, [{"ticker": "BBB"}], pending_label="compras para próxima apertura")
        self.assertEqual(order["activity_label"], "1 compra para próxima apertura")
        self.assertEqual(signal["activity_label"], "1 señal congelada · liquidación semanal pendiente")
        self.assertEqual(mixed["activity_label"], "1 posición · 1 compra para próxima apertura")

    def test_missing_runs_are_explicit_and_have_no_returns(self):
        result = build(self.registry, self.config, now=self.now)
        self.assertEqual(result["counts"], {"paper_with_diary": 0, "legacy_with_diary": 0,
                                             "tfm_with_diary": 0, "weekly_ml_with_diary": 0,
                                             "tfg_with_diary": 0, "capital_cycle_with_diary": 0,
                                             "buy_the_dip_with_diary": 0,
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
                            "pending": [],
                            "equity": [{"date": "2026-10-02", "nav": 100000.0},
                                       {"date": "2026-10-09", "nav": 101000.0}]}
                      for key in keys}}
        weekly["strategies"]["ensemble_consensus"]["pending"] = [
            {"ticker": "AMD"}, {"ticker": "INTC"}
        ]
        result = build(self.registry, self.config, now=self.now,
                       weekly_config=weekly_config, weekly_state=weekly)
        self.assertEqual(result["counts"]["weekly_ml_with_diary"], 9)
        ensemble = next(row for row in result["tracks"] if row["id"] == "weekly_ml_ensemble_2026")
        self.assertEqual((ensemble["group"], ensemble["return_pct"], ensemble["day_return_pct"]),
                         ("weekly_ml_demo", 1.0, 1.0))
        self.assertEqual(ensemble["currency"], "USD")
        self.assertEqual(ensemble["equity_history"][-1], {"date": "2026-10-09", "nav": 101000.0})
        self.assertEqual(ensemble["activity_state"], "pending")
        self.assertEqual(ensemble["activity_label"], "2 señales congeladas · liquidación semanal pendiente")
        self.assertIn("NO es una compra ejecutada", ensemble["note"])
        self.assertEqual(ensemble["activity_tickers"], ["AMD", "INTC"])


    def test_weekly_daily_ledger_overrides_legacy_settlement_without_double_counting(self):
        config = {"models": ["lgbm_return", "lgbm_direction", "lgbm_ranker",
                             "mlp_return", "lstm_return", "arima_return",
                             "ensemble_consensus"],
                  "currency": "USD", "paper_policy": {"capital": 100000}}
        keys = list(self.registry["weekly_ml_tracks"])
        legacy = {"config_hash": _config_hash(config), "first_session": "2026-10-02",
                  "last_session": "2026-10-09", "strategies": {
                      key: {"nav": 105000.0, "pending": [],
                            "equity": [{"date": "2026-10-02", "nav": 100000},
                                       {"date": "2026-10-09", "nav": 105000}]}
                      for key in keys}}
        daily = {"config_hash": _config_hash(config),
                 "engine": "weekly_ml_daily_next_open_v1",
                 "first_session": "2026-10-09", "last_session": "2026-10-12",
                 "strategies": {
                     key: {"nav": 100100.0, "positions": {"AAA": {"shares": 2}},
                           "pending": [], "equity": [
                               {"date": "2026-10-09", "nav": 100000},
                               {"date": "2026-10-12", "nav": 100100}]}
                     for key in keys}}
        result = build(self.registry, self.config, now=self.now,
                       weekly_config=config, weekly_state=legacy, weekly_daily_state=daily)
        row = next(x for x in result["tracks"] if x["id"] == "weekly_ml_ensemble_2026")
        self.assertEqual(row["last_session"], "2026-10-12")
        self.assertEqual(row["return_pct"], 0.1)
        self.assertTrue(row["daily_mode"])
        self.assertEqual(row["activity_state"], "active")
        self.assertEqual(row["activity_tickers"], ["AAA"])
        self.assertEqual(row["equity_history"][-1]["date"], "2026-10-12")
        self.assertEqual(result["counts"]["weekly_ml_with_diary"], 9)

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


    def test_buy_the_dip_uses_separate_monthly_ledger_and_risk(self):
        btd_config = {
            "name": "MIDAS_buy_the_dip_corpus_v0_2026",
            "currency": "USD",
            "paper_policy": {"capital": 100000.0},
        }
        btd = {
            "config_hash": _config_hash(btd_config),
            "strategy_id": "buy_the_dip_corpus_2026_v0",
            "first_session": "2026-10-01",
            "last_session": "2026-10-05",
            "nav": 99000.0,
            "equity": [
                {"date": "2026-10-01", "nav": 100000.0},
                {"date": "2026-10-02", "nav": 102000.0},
                {"date": "2026-10-05", "nav": 99000.0},
            ],
        }
        result = build(self.registry, self.config, now=self.now,
                       btd_config=btd_config, btd_state=btd)
        self.assertEqual(result["counts"]["buy_the_dip_with_diary"], 1)
        row = next(x for x in result["tracks"] if x["id"] == "buy_the_dip_corpus_2026_v0")
        self.assertEqual(row["group"], "buy_the_dip_demo")
        self.assertEqual(row["return_pct"], -1.0)
        self.assertEqual(row["risk_observations"], 3)
        self.assertIsNone(row["annualized_volatility_pct"])
        self.assertAlmostEqual(row["max_drawdown_pct"], -2.941176, places=5)
        self.assertIsNone(row["sharpe_0rf"])
        self.assertIn("Buy The Dip", markdown(result))


    def test_risk_volatility_and_sharpe_wait_for_enough_observations(self):
        btd_config = {
            "name": "MIDAS_buy_the_dip_corpus_v0_2026",
            "currency": "USD",
            "paper_policy": {"capital": 100000.0},
        }
        equity = []
        nav = 100000.0
        for day in range(1, 12):
            nav *= 1.002 if day % 2 else 0.999
            equity.append({"date": f"2026-10-{day:02d}", "nav": nav})
        btd = {
            "config_hash": _config_hash(btd_config),
            "strategy_id": "buy_the_dip_corpus_2026_v0",
            "first_session": equity[0]["date"],
            "last_session": equity[-1]["date"],
            "nav": equity[-1]["nav"],
            "equity": equity,
        }
        result = build(self.registry, self.config, now=self.now,
                       btd_config=btd_config, btd_state=btd)
        row = next(x for x in result["tracks"] if x["id"] == "buy_the_dip_corpus_2026_v0")
        self.assertEqual(row["risk_observations"], 11)
        self.assertIsNotNone(row["annualized_volatility_pct"])
        self.assertIsNotNone(row["sharpe_0rf"])


    def test_capital_cycle_uses_separate_monthly_ledger(self):
        capital_config = {
            "name": "MIDAS_capital_cycle_inflection_2026",
            "currency": "USD",
            "paper_policy": {"capital": 100000.0},
        }
        capital = {
            "config_hash": _config_hash(capital_config),
            "strategy_id": "capital_cycle_inflection_2026",
            "first_session": "2026-09-30",
            "last_session": "2026-10-01",
            "nav": 101250.0,
            "equity": [
                {"date": "2026-09-30", "nav": 100000.0},
                {"date": "2026-10-01", "nav": 101250.0},
            ],
            "positions": {"OXY": {}, "QCOM": {}},
            "pending": None,
        }
        result = build(self.registry, self.config, now=self.now,
                       capital_config=capital_config, capital_state=capital)
        self.assertEqual(result["counts"]["capital_cycle_with_diary"], 1)
        row = next(x for x in result["tracks"] if x["id"] == "capital_cycle_inflection_2026")
        self.assertEqual(row["group"], "capital_cycle_demo")
        self.assertEqual(row["return_pct"], 1.25)
        self.assertEqual(row["day_return_pct"], 1.25)
        self.assertEqual(row["currency"], "USD")
        self.assertEqual(row["activity_label"], "2 posiciones abiertas")
        self.assertEqual(row["activity_tickers"], ["OXY", "QCOM"])
        self.assertIn("underinvestment", row["note"])


if __name__ == "__main__":
    unittest.main()
