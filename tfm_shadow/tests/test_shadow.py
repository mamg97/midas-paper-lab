import csv
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forecast import make_samples, validate_panel
from market import eligible_session, contiguous_complete_panel
from run import evaluate, run
from paper import advance


def panel(length=140):
    first = date(2025, 1, 1)
    dates = [(first + timedelta(days=i)).isoformat() for i in range(length)]
    return {ticker: [{"date": day, "open": 100 + index * (1 + number / 10),
                     "close": 100 + index * (1 + number / 10)}
                     for index, day in enumerate(dates)]
            for number, ticker in enumerate(("AAA.MC", "BBB.MC"))}


class ForecastContractTests(unittest.TestCase):
    def test_old_bad_provider_bar_truncates_history_without_inventing_price(self):
        data = panel(150)
        dates = [bar["date"] for bar in data["AAA.MC"]]
        data["BBB.MC"][4]["close"] = float("nan")
        clean = contiguous_complete_panel(data, dates, dates[-1], minimum=130)
        self.assertEqual(len(clean["AAA.MC"]), 145)
        self.assertEqual(clean["AAA.MC"][0]["date"], dates[5])
        self.assertEqual(clean["BBB.MC"][-1]["close"], data["BBB.MC"][-1]["close"])

    def test_recent_or_current_bad_bar_stops_the_forecast(self):
        data = panel(150)
        dates = [bar["date"] for bar in data["AAA.MC"]]
        data["BBB.MC"][100]["close"] = float("nan")
        with self.assertRaisesRegex(ValueError, "Historial continuo insuficiente"):
            contiguous_complete_panel(data, dates, dates[-1], minimum=130)
        data["BBB.MC"][100]["close"] = 100.0
        data["BBB.MC"][-1]["close"] = float("nan")
        with self.assertRaisesRegex(ValueError, "Última sesión incompleta"):
            contiguous_complete_panel(data, dates, dates[-1], minimum=130)

    def test_delayed_workflow_stays_before_next_market_open(self):
        madrid = timezone(timedelta(hours=2))
        self.assertEqual(eligible_session(datetime(2026, 9, 28, 21, 0, tzinfo=madrid)),
                         "2026-09-28")
        self.assertEqual(eligible_session(datetime(2026, 9, 29, 1, 0, tzinfo=madrid)),
                         "2026-09-28")
        with self.assertRaisesRegex(ValueError, "apertura ya ocurrió"):
            eligible_session(datetime(2026, 9, 29, 11, 0, tzinfo=madrid))

    def test_last_training_target_is_known_at_asof(self):
        data = panel()
        asof = data["AAA.MC"][-1]["date"]
        x, y, latest, info = make_samples(data, asof)
        self.assertEqual(len(y), 2 * (140 - 1 - 50))
        self.assertEqual(x.shape[1], 50)
        self.assertEqual(info["last_target"], asof)
        self.assertEqual(set(latest), set(data))
        extended = panel(141)
        with self.assertRaisesRegex(ValueError, "Fechas inválidas"):
            make_samples(extended, asof)

    def test_missing_bar_is_rejected_instead_of_filled(self):
        data = panel()
        data["BBB.MC"].pop(100)
        with self.assertRaisesRegex(ValueError, "Calendarios incompletos"):
            validate_panel(data, data["AAA.MC"][-1]["date"])

    def test_previous_forecast_is_scored_on_next_session_only(self):
        data = {ticker: [{"date": day, "open": value, "close": value} for day, value in
                         (("2026-09-24", 100), ("2026-09-25", 101), ("2026-09-28", 90))]
                for ticker in ("AAA.MC", "BBB.MC")}
        previous = {"asof": "2026-09-24", "models": {"lgbm": {
            ticker: {"last_close": 100, "next_close_predicted": 102}
            for ticker in data}}}
        result = evaluate(previous, data, "2026-09-28")
        self.assertEqual(result["outcome_session"], "2026-09-25")
        self.assertTrue(result["recorded_after_gap"])
        self.assertEqual(len(result["rows"]), 2)
        self.assertTrue(all(row["direction_correct"] for row in result["rows"]))

    def test_paper_decision_is_committed_before_next_open(self):
        config = {"tickers": ["AAA.MC"], "models": ["lgbm"], "paper_policy": {
            "capital": 1000.0, "commission": .001, "slippage": .0005,
            "invest_fraction": .95, "max_entry_weight": .15,
            "max_positions": 1, "min_predicted_return": .003,
            "fractional_shares": True, "share_precision": 6, "min_notional": 10.0}}
        bars = {"AAA.MC": [{"date": "2026-09-24", "open": 100.0, "close": 100.0},
                           {"date": "2026-09-25", "open": 100.0, "close": 110.0}]}
        first = {"asof": "2026-09-24", "models": {"lgbm": {"AAA.MC": {
            "return_predicted_pct": 1.0}}}}
        second = {"asof": "2026-09-25", "models": {"lgbm": {"AAA.MC": {
            "return_predicted_pct": 0.0}}}}
        initial, _ = advance(config, {"AAA.MC": bars["AAA.MC"][:1]}, first)
        self.assertEqual(initial["models"]["lgbm"]["nav"], 1000)
        self.assertEqual(initial["models"]["lgbm"]["trades"], [])
        settled, _ = advance(config, bars, second, initial)
        book = settled["models"]["lgbm"]
        self.assertEqual(book["trades"][0]["signal_date"], "2026-09-24")
        self.assertEqual(book["trades"][0]["date"], "2026-09-25")
        self.assertIsInstance(book["trades"][0]["quantity"], float)
        self.assertGreater(book["trades"][0]["quantity"], 1.0)
        self.assertLess(book["trades"][0]["quantity"], 2.0)
        self.assertGreater(book["nav"], 1000)
        self.assertEqual(book["pending"], [])
        duplicate, changed = advance(config, bars, second, settled)
        self.assertFalse(changed)
        self.assertEqual(duplicate, settled)

    def test_daily_run_is_idempotent_and_recovers_a_missing_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tickers = [f"T{number:02d}.MC" for number in range(31)]
            config = {"schema_version": 1, "calendar": "XMAD", "currency": "EUR",
                      "tickers": tickers, "models": ["lgbm", "mlp", "lstm", "arima"],
                      "paper_policy": {"capital": 100000.0, "commission": .001,
                                       "slippage": .0005, "invest_fraction": .95,
                                       "max_positions": 10, "min_predicted_return": .003,
                                       "max_entry_weight": .15,
                                       "fractional_shares": True, "share_precision": 6,
                                       "min_notional": 10.0}}
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            snapshot = root / "market.csv"
            dates = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(141)]

            def write_market(length):
                with snapshot.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=["date", "ticker", "open", "close"])
                    writer.writeheader()
                    for ticker in tickers:
                        for index, day in enumerate(dates[:length]):
                            writer.writerow({"date": day, "ticker": ticker,
                                             "open": 100 + index, "close": 100 + index + .2})

            def fake_forecast(data, asof, models):
                return {"schema_version": 1, "asof": asof,
                        "models": {name: {ticker: {"last_close": data[ticker][-1]["close"],
                                                  "next_close_predicted": data[ticker][-1]["close"] * 1.01,
                                                  "return_predicted_pct": 1.0}
                                          for ticker in tickers} for name in models}}

            output = root / "state"
            with patch("run.forecast", side_effect=fake_forecast), \
                    patch("run._installed_version", return_value="test"):
                write_market(140)
                self.assertEqual(run(config_path, output, snapshot)["status"], "forecast_recorded")
                self.assertEqual(run(config_path, output, snapshot)["status"], "already_recorded")
                (output / "ledger.json").unlink()
                self.assertEqual(run(config_path, output, snapshot)["status"], "already_recorded")
                write_market(141)
                self.assertEqual(run(config_path, output, snapshot)["status"], "forecast_recorded")
            ledger = json.loads((output / "ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["last_session"], dates[140])
            self.assertEqual(len(ledger["models"]["lgbm"]["trades"]), 10)
            scored = json.loads((output / "evaluations" / f"{dates[139]}.json").read_text())
            self.assertEqual(len(scored["rows"]), 124)

    def test_expensive_share_is_filled_fractionally(self):
        config = {"tickers": ["AAA.MC"], "models": ["lgbm"], "paper_policy": {
            "capital": 1000.0, "commission": .001, "slippage": .0005,
            "invest_fraction": .95, "max_entry_weight": .15,
            "max_positions": 1, "min_predicted_return": .003,
            "fractional_shares": True, "share_precision": 6, "min_notional": 10.0}}
        bars = {"AAA.MC": [{"date": "2026-09-24", "open": 1000., "close": 1000.},
                           {"date": "2026-09-25", "open": 1000., "close": 1100.}]}
        def prediction(day):
            return {"asof": day, "models": {"lgbm": {"AAA.MC": {
                "return_predicted_pct": 1.0}}}}
        first, _ = advance(config, {"AAA.MC": bars["AAA.MC"][:1]}, prediction("2026-09-24"))
        second, _ = advance(config, bars, prediction("2026-09-25"), first)
        trade = second["models"]["lgbm"]["trades"][0]
        self.assertGreater(trade["quantity"], 0.1)
        self.assertLess(trade["quantity"], 0.2)
        self.assertGreater(second["models"]["lgbm"]["nav"], 1000.)
        self.assertEqual(second["models"]["lgbm"]["unfilled"], [])


if __name__ == "__main__":
    unittest.main()
