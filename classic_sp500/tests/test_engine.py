import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run as classic


class SAndP500ClassicTests(unittest.TestCase):
    def setUp(self):
        self.config = classic.market.read(Path(__file__).resolve().parents[1] / "config.json")
        self.symbols = classic.verify_config(self.config)
        self.day = "2026-10-13"
        self.fake = {"buy_hold_equal_weight": [
            ("AAPL", "buy", .05), ("MSFT", "buy", .03)
        ]}
        self.diagnostic = {"eligible": 503, "total": 503, "missing": {}, "ticker_coverage_pct": 100}
        self.book = classic.initialize(self.config, self.day, self.fake, self.diagnostic)

    def test_universe_matches_existing_canonical_503(self):
        self.assertEqual(len(self.symbols), 503)
        self.assertIn("AAPL", self.symbols)
        self.assertIn("BRK-B", self.symbols)
        self.assertEqual(set(self.book["books"]), set(self.config["strategies"]) | {"benchmark_spy"})
        self.assertEqual(self.book["first_session"], self.day)
        self.assertTrue(all(b["trades"] == [] for b in self.book["books"].values()))

    def test_universe_cannot_be_reduced(self):
        c = copy.deepcopy(self.config)
        c["universe_file"] = "paper_demo/universe_eight.csv"
        with self.assertRaises(ValueError):
            classic.verify_config(c)
        c = copy.deepcopy(self.config)
        c["initial_capital"] = 80000
        with self.assertRaises(ValueError):
            classic.verify_config(c)

    def test_next_open_503_equal_weight_benchmark_and_positions(self):
        prices = {"AAPL": {"open": 100, "low": 99, "high": 105, "close": 104},
                  "MSFT": {"open": 200, "low": 200, "high": 203, "close": 202},
                  "SPY": {"open": 400, "low": 398, "high": 406, "close": 405}}
        updated, changed = classic.settle(self.config, self.book, "2026-10-14",
                                          self.day, prices)
        self.assertTrue(changed)
        self.assertIn("AAPL", updated["books"]["buy_hold_equal_weight"]["positions"])
        self.assertIn("MSFT", updated["books"]["buy_hold_equal_weight"]["positions"])
        self.assertIn("SPY", updated["books"]["benchmark_spy"]["positions"])
        self.assertGreater(updated["books"]["buy_hold_equal_weight"]["nav"], 100000)
        self.assertEqual(self.book["last_session"], self.day)
        self.assertEqual(updated["last_session"], "2026-10-14")
        self.assertEqual(len(updated["books"]["macd_12_26_9"]["equity"]), 2)

    def test_missing_buy_bar_stays_unfilled_without_blocking_other_fills(self):
        original = copy.deepcopy(self.book)
        today = {"AAPL": {"open": 100, "high": 105, "low": 99, "close": 103},
                 "SPY": {"open": 400, "high": 405, "low": 399, "close": 404}}
        result, changed = classic.settle(
            self.config, self.book, "2026-10-14", self.day, today)
        self.assertTrue(changed)
        holdings = result["books"]["buy_hold_equal_weight"]
        self.assertIn("AAPL", holdings["positions"])
        self.assertNotIn("MSFT", holdings["positions"])
        self.assertEqual(holdings["pending"], {})
        unfilled = [e for e in holdings["events"]
                    if e["type"] == "unfilled_missing_dated_bar"]
        self.assertEqual([e["ticker"] for e in unfilled], ["MSFT"])
        self.assertEqual(unfilled[0]["date"], "2026-10-14")
        self.assertIn("SPY", result["books"]["benchmark_spy"]["positions"])
        self.assertEqual(original, self.book)
        # A missing buy cannot increase any other weight.
        budget = self.config["initial_capital"] * self.config["execution"]["capital_fraction"] / 503
        self.assertLessEqual(holdings["positions"]["AAPL"]["cost"], budget + 1e-7)

    def test_missing_benchmark_buy_never_fabricates_a_fill(self):
        today = {"AAPL": {"open": 100, "high": 105, "low": 99, "close": 103},
                 "MSFT": {"open": 200, "high": 204, "low": 197, "close": 202}}
        result, changed = classic.settle(
            self.config, self.book, "2026-10-14", self.day, today)
        self.assertTrue(changed)
        benchmark = result["books"]["benchmark_spy"]
        self.assertEqual(benchmark["positions"], {})
        self.assertEqual(benchmark["nav"], 100000)
        self.assertEqual(benchmark["events"][0]["type"], "unfilled_missing_dated_bar")
        self.assertEqual(benchmark["events"][0]["ticker"], "SPY")

    def test_missing_existing_holding_is_still_fatal(self):
        today = {"AAPL": {"open": 100, "high": 105, "low": 99, "close": 103},
                 "MSFT": {"open": 200, "high": 204, "low": 197, "close": 202},
                 "SPY": {"open": 400, "high": 405, "low": 399, "close": 404}}
        invested, _ = classic.settle(
            self.config, self.book, "2026-10-14", self.day, today)
        original = copy.deepcopy(invested)
        with self.assertRaisesRegex(ValueError, "Missing dated bar for held position"):
            classic.settle(self.config, invested, "2026-10-15", "2026-10-14",
                           {"SPY": today["SPY"], "MSFT": today["MSFT"]})
        self.assertEqual(invested, original)

    def test_daily_runner_publishes_explicit_missing_buy_diagnostic(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        import json
        today = {"AAPL": {"open": 100, "high": 105, "low": 99, "close": 103},
                 "SPY": {"open": 400, "high": 405, "low": 399, "close": 404}}
        with TemporaryDirectory() as td:
            path = Path(td) / "ledger.json"
            path.write_text(json.dumps(self.book), encoding="utf-8")
            with (patch.object(classic.market, "calendar",
                               return_value=("2026-10-14", "2026-10-13",
                                             "2026-10-15", False)),
                  patch.object(classic, "fetch_live", return_value=({}, today)),
                  patch.object(classic, "rank_signals",
                               return_value=(self.fake, self.diagnostic))):
                result = classic.run(
                    Path(__file__).resolve().parents[1] / "config.json", path)
            self.assertEqual(result["status"], "paper_recorded")
            self.assertEqual(result["unfilled_pending_buys_missing_bar"], ["MSFT"])
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["last_session"], "2026-10-14")
            self.assertEqual(persisted["coverage"][-1]
                             ["unfilled_pending_buys_missing_bar"], ["MSFT"])
            self.assertNotIn("MSFT",
                             persisted["books"]["buy_hold_equal_weight"]["positions"])

    def test_no_retroactive_reconstruction(self):
        with self.assertRaisesRegex(ValueError, "Missing market session"):
            classic.settle(self.config, self.book, "2026-10-15", "2026-10-14", {})
        same, changed = classic.settle(self.config, self.book, self.day, "2026-10-12", {})
        self.assertFalse(changed)
        self.assertEqual(same, self.book)

    def test_full_coverage_is_requested_not_faked(self):
        with self.assertRaisesRegex(ValueError, "insufficient dated data"):
            classic.rank_signals(self.config, {}, self.day)
        self.assertEqual(self.book["coverage"][0]["total"], 503)

    def test_sp500_new_diary_differs_from_legacy_book(self):
        legacy = classic.market.read(Path(__file__).resolve().parents[2] / "paper_demo/config.json")
        self.assertEqual(len(legacy["tickers"]), 8)
        self.assertNotEqual(classic.market.digest(legacy), self.book["config_hash"])
        self.assertEqual(self.book["currency"], "USD")


    def test_missing_mandatory_close_gets_isolated_same_session_retry(self):
        from unittest.mock import patch
        synthetic = object()
        quoted = {"Open": 101.0, "High": 103.0, "Low": 99.0, "Close": 102.0}
        calls = []

        def download(symbols, start, end, allow_missing=False):
            calls.append(list(symbols))
            if len(calls) == 1:
                return {"SPY": synthetic}
            self.assertEqual(symbols, ["SYNTH"])
            return {"SYNTH": synthetic}

        with (patch.object(classic.market, "_download", side_effect=download),
              patch.object(classic.market, "_last_row", return_value=quoted)):
            frames, bars = classic.fetch_live(
                self.config, "2026-10-14", "2026-10-13", ["AAPL"], required={"SYNTH"})
        self.assertEqual(len(calls), 2)
        self.assertIn("SYNTH", frames)
        self.assertEqual(bars["SYNTH"]["close"], 102.0)

    def test_issuer_confirmed_rename_only_after_effective_session(self):
        self.assertIsNone(classic.verified_price_symbol("PSKY", "2026-10-05"))
        self.assertEqual(classic.verified_price_symbol("PSKY", "2026-10-06"), "SKYD")
        self.assertEqual(classic.verified_price_symbol("PSKY", "2026-10-19"), "SKYD")
        self.assertIsNone(classic.verified_price_symbol("SPY", "2026-10-19"))

    def test_renamed_held_security_reads_skyd_but_preserves_psky_key(self):
        from unittest.mock import patch
        synthetic = object()
        quotes = {"Open": 6.89, "High": 6.96, "Low": 6.61, "Close": 6.80}
        calls = []

        def download(symbols, start, end, allow_missing=False):
            calls.append(tuple(symbols))
            return {"SKYD": synthetic} if symbols == ["SKYD"] else {}

        with (patch.object(classic.market, "_download", side_effect=download),
              patch.object(classic.market, "_last_row", return_value=quotes)):
            frames, bars = classic.fetch_live(
                self.config, "2026-10-19", "2026-10-16",
                ["PSKY"], required={"PSKY"})
        self.assertEqual(calls[-2:], [("PSKY",), ("SKYD",)])
        self.assertEqual(list(frames), ["PSKY"])
        self.assertEqual(bars["PSKY"]["close"], 6.80)
        self.assertEqual(bars["PSKY"]["verified_price_source_symbol"], "SKYD")
        self.assertNotIn("SKYD", bars)

    def test_renamed_symbol_never_supplies_prior_or_missing_dated_prices(self):
        from unittest.mock import patch
        with (patch.object(classic.market, "_download",
                           side_effect=[{}, {}, {"SKYD": object()}]) as download,
              patch.object(classic.market, "_last_row",
                           side_effect=ValueError("not the requested session"))):
            frames, bars = classic.fetch_live(
                self.config, "2026-10-19", "2026-10-16",
                ["PSKY"], required={"PSKY"})
        self.assertEqual((frames, bars), ({}, {}))
        self.assertEqual(download.call_count, 3)

    def test_isolated_retry_never_fabricates_missing_mandatory_close(self):
        from unittest.mock import patch
        with patch.object(classic.market, "_download", side_effect=[
            {}, {"SYNTH": object()}
        ]) as download, patch.object(
            classic.market, "_last_row", side_effect=ValueError("Missing exact dated OHLC")
        ):
            frames, bars = classic.fetch_live(
                self.config, "2026-10-14", "2026-10-13", ["AAPL"], required={"SYNTH"})
        self.assertNotIn("SYNTH", bars)
        self.assertEqual(download.call_count, 2)
        self.assertEqual(frames, {})

    def test_flat_gap_recovery_marks_missing_session_without_backdating_trades(self):
        state = classic.initialize(
            self.config, "2026-10-12", self.fake, self.diagnostic)
        frozen = copy.deepcopy(state)
        resumed, missed, expired = classic.recover_flat_gap(
            self.config, state, "2026-10-14", "2026-10-13",
            self.fake, self.diagnostic)
        self.assertEqual(state, frozen)
        self.assertEqual(missed, ["2026-10-13"])
        self.assertEqual(resumed["missed_sessions"], ["2026-10-13"])
        self.assertGreater(expired, 0)
        self.assertEqual(resumed["last_session"], "2026-10-14")
        for book in resumed["books"].values():
            self.assertEqual(book["positions"], {})
            self.assertEqual(book["trades"], [])
            self.assertEqual(book["nav"], 100000)
            self.assertEqual([v["date"] for v in book["equity"]],
                             ["2026-10-12", "2026-10-14"])
            self.assertEqual(book["events"][-1]["type"], "missed_session_unfilled")
            self.assertTrue(all(order["signal_date"] == "2026-10-14"
                                for order in book["pending"].values()))
        self.assertEqual(
            resumed["books"]["benchmark_spy"]["pending"]["SPY"]["signal_date"],
            "2026-10-14")

    def test_gap_with_any_live_position_fails_closed(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        import json
        state = classic.initialize(
            self.config, "2026-10-12", self.fake, self.diagnostic)
        state["books"]["benchmark_spy"]["positions"]["SPY"] = {"shares": 2}
        with TemporaryDirectory() as td:
            path = Path(td) / "ledger.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            with (patch.object(classic.market, "calendar",
                               return_value=("2026-10-14", "2026-10-13",
                                             "2026-10-15", False)),
                  patch.object(classic, "fetch_live", return_value=({}, {}))):
                with self.assertRaisesRegex(
                        ValueError, "Gap reconciliation requires real same-session OHLC"):
                    classic.run(
                        Path(__file__).resolve().parents[1] / "config.json", path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), state)

    def _invested_state_oct16(self):
        orders = self.fake
        base = classic.initialize(self.config, "2026-10-15", orders, self.diagnostic)
        bars = {
            "AAPL": {"open": 100, "low": 99, "high": 104, "close": 101},
            "MSFT": {"open": 200, "low": 198, "high": 205, "close": 203},
            "SPY": {"open": 400, "low": 399, "high": 404, "close": 402},
        }
        state, _ = classic.settle(self.config, base, "2026-10-16", "2026-10-15", bars)
        return classic.freeze(self.config, state, "2026-10-16",
                              orders, self.diagnostic)

    def test_invested_gap_replays_both_dated_sessions_and_freezes_new_signals(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        import json
        initial = self._invested_state_oct16()
        self.assertIn("AAPL", initial["books"]["buy_hold_equal_weight"]["positions"])
        original = copy.deepcopy(initial)
        calls = []
        priced = {
            "AAPL": {"open": 102, "low": 101, "high": 106, "close": 104},
            "MSFT": {"open": 204, "low": 203, "high": 210, "close": 208},
            "SPY": {"open": 405, "low": 404, "high": 408, "close": 406},
        }

        def prices(_config, session, previous, symbols, *, required=()):
            calls.append(("prices", session, previous, tuple(sorted(required))))
            self.assertEqual(previous, "2026-10-16" if session == "2026-10-19"
                             else "2026-10-19")
            self.assertTrue({"AAPL", "MSFT", "SPY"} <= set(required))
            return {}, priced

        def signals(_config, panel, session):
            calls.append(("signals", session))
            return self.fake, self.diagnostic

        with TemporaryDirectory() as td:
            path = Path(td) / "ledger.json"
            path.write_text(json.dumps(initial), encoding="utf-8")
            with (patch.object(classic.market, "calendar",
                               return_value=("2026-10-20", "2026-10-19",
                                             "2026-10-21", False)),
                  patch.object(classic, "fetch_live", side_effect=prices),
                  patch.object(classic, "rank_signals", side_effect=signals)):
                out = classic.run(Path(__file__).resolve().parents[1] / "config.json", path)
                self.assertEqual(out["status"], "dated_paper_sessions_reconciled")
                self.assertEqual(out["late_recorded_sessions"],
                                 ["2026-10-19", "2026-10-20"])
                ledger_text = path.read_text(encoding="utf-8")
                repeat = classic.run(Path(__file__).resolve().parents[1] / "config.json", path)
                self.assertEqual(repeat["status"], "already_recorded")
                self.assertEqual(ledger_text, path.read_text(encoding="utf-8"))
        updated = json.loads(ledger_text)
        self.assertEqual(initial, original)
        self.assertEqual(updated["last_session"], "2026-10-20")
        self.assertEqual(
            [point["date"] for point in updated["books"]["benchmark_spy"]["equity"]],
            ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"])
        self.assertEqual(updated["late_recorded_sessions"], ["2026-10-19", "2026-10-20"])
        self.assertTrue(all(x.get("late_recorded_verified_date")
                            for x in updated["coverage"][-2:]))
        self.assertEqual([x[:2] for x in calls],
                         [("prices", "2026-10-19"), ("signals", "2026-10-19"),
                          ("prices", "2026-10-20"), ("signals", "2026-10-20")])

    def test_invested_gap_is_atomic_if_second_day_lacks_held_prices(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        import json
        state = self._invested_state_oct16()
        bars = {
            "AAPL": {"open": 102, "low": 101, "high": 106, "close": 104},
            "MSFT": {"open": 204, "low": 203, "high": 210, "close": 208},
            "SPY": {"open": 405, "low": 404, "high": 408, "close": 406},
        }

        def prices(_config, session, previous, symbols, *, required=()):
            return {}, bars if session == "2026-10-19" else {"SPY": bars["SPY"]}

        with TemporaryDirectory() as td:
            path = Path(td) / "ledger.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            before = path.read_bytes()
            with (patch.object(classic.market, "calendar",
                               return_value=("2026-10-20", "2026-10-19",
                                             "2026-10-21", False)),
                  patch.object(classic, "fetch_live", side_effect=prices),
                  patch.object(classic, "rank_signals",
                               return_value=(self.fake, self.diagnostic))):
                with self.assertRaisesRegex(ValueError, "2026-10-20 AAPL,MSFT"):
                    classic.run(
                        Path(__file__).resolve().parents[1] / "config.json", path)
            self.assertEqual(path.read_bytes(), before)

    def test_invested_gap_older_than_three_sessions_requires_review(self):
        state = self._invested_state_oct16()
        with self.assertRaisesRegex(ValueError, "bounded reconciliation"):
            classic.market_sessions_after(
                state["last_session"], "2026-10-23", "2026-10-22")

    def test_daily_run_recovers_cash_only_gap_then_is_idempotent(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        import json
        state = classic.initialize(
            self.config, "2026-10-12", self.fake, self.diagnostic)
        with TemporaryDirectory() as td:
            path = Path(td) / "ledger.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            with (patch.object(classic.market, "calendar",
                               return_value=("2026-10-14", "2026-10-13",
                                             "2026-10-15", False)),
                  patch.object(classic, "fetch_live", return_value=({}, {})) as fetch,
                  patch.object(classic, "rank_signals",
                               return_value=(self.fake, self.diagnostic))):
                outcome = classic.run(
                    Path(__file__).resolve().parents[1] / "config.json", path)
                self.assertEqual(outcome["status"], "flat_gap_recovered_no_backfill")
                self.assertEqual(outcome["missed_sessions"], ["2026-10-13"])
                self.assertEqual(fetch.call_args.kwargs["required"], set())
                unchanged = path.read_text(encoding="utf-8")
                second = classic.run(
                    Path(__file__).resolve().parents[1] / "config.json", path)
                self.assertEqual(second["status"], "already_recorded")
                self.assertEqual(path.read_text(encoding="utf-8"), unchanged)

    def test_non_held_missing_symbols_are_not_individually_refetched(self):
        from unittest.mock import patch
        with patch.object(classic.market, "_download", return_value={}) as download:
            frames, bars = classic.fetch_live(
                self.config, "2026-10-14", "2026-10-13", ["AAPL"], required=set())
        self.assertEqual((frames, bars), ({}, {}))
        self.assertEqual(download.call_count, 1)


if __name__ == "__main__":
    unittest.main()
