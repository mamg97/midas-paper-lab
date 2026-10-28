import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recovery import recover_passive_books


class PassiveRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.config = {"strategies": {"hold": {"kind": "equal_weight_hold"}}}
        self.state = {"last_session": "2026-10-28", "books": {"hold": {
            "cash": 50., "nav": 150., "positions": {"AAA": {"shares": 1., "stop": None, "target": None}},
            "pending": {"BBB": {"side": "buy", "signal_date": "2026-10-26"}},
            "trades": [], "events": [], "equity": [{"date": "2026-10-26", "nav": 150.}],
            "paused_missing_quotes": {"since": "2026-10-27", "missing_tickers": ["AAA"]}}}}
        self.days = lambda start, end: ["2026-10-27", "2026-10-28"]
        self.quotes = lambda day: ({"AAA": {"close": 101. if day.endswith("27") else 103.,
                                          "split": 0., "dividend": 0.}}, {"snapshot_sha256": day})

    def recover(self, quotes=None, days=None):
        return recover_passive_books(self.config, self.state, days or self.days,
                                     quotes or self.quotes, recorded_at="2026-10-29T01:00:00Z")

    def test_all_days_required_and_no_fills_or_existing_history_changes(self):
        before = copy.deepcopy(self.state)
        got, restored, blocked = self.recover()
        self.assertEqual(restored, ["hold"])
        self.assertEqual(blocked, {})
        book = got["books"]["hold"]
        self.assertEqual(book["equity"][0], before["books"]["hold"]["equity"][0])
        self.assertEqual(book["nav"], 153.)
        self.assertEqual(book["trades"], [])
        self.assertEqual(book["cash"], 50.)
        self.assertEqual(book["positions"], before["books"]["hold"]["positions"])
        self.assertEqual(book["pending"], {})
        self.assertEqual(book["events"][-1]["expired_unfilled_buys"], ["BBB"])
        self.assertEqual(self.state, before)
        twice, restored, _ = recover_passive_books(self.config, got, self.days, self.quotes, recorded_at="later")
        self.assertEqual(twice, got)
        self.assertEqual(restored, [])

    def test_one_missing_historical_day_cannot_be_skipped_or_partially_written(self):
        def quotes(day):
            return ({}, {}) if day.endswith("27") else self.quotes(day)
        got, restored, blocked = self.recover(quotes)
        self.assertEqual(got, self.state)
        self.assertEqual(restored, [])
        self.assertIn("missing_historical", blocked["hold"])

    def test_corporate_action_requires_review(self):
        for field in ("split", "dividend"):
            def quotes(day):
                bars, identity = self.quotes(day)
                bars["AAA"][field] = 2
                return bars, identity
            got, restored, blocked = self.recover(quotes)
            self.assertEqual(got, self.state)
            self.assertEqual(restored, [])
            self.assertEqual(blocked["hold"], "corporate_action_requires_review")

    def test_historical_sell_or_active_strategy_cannot_be_invented(self):
        for kind, side in [("equal_weight_hold", "sell"), ("turtle", "buy")]:
            self.config["strategies"]["hold"]["kind"] = kind
            self.state["books"]["hold"]["pending"]["BBB"]["side"] = side
            got, restored, blocked = self.recover()
            self.assertEqual(got, self.state)
            self.assertEqual(restored, [])
            self.assertIn("require_review", blocked["hold"])

    def test_reviewed_dividend_is_recorded_once_under_existing_paper_policy(self):
        def quotes(day):
            bars, identity = self.quotes(day)
            bars["AAA"]["dividend"] = .5 if day.endswith("27") else 0
            return bars, identity
        reviews = {"reviews": [{"ticker": "AAA", "kind": "cash_dividend", "currency": "USD",
                    "amount": .5, "vendor_ex_session": "2026-10-27",
                    "source_url": "https://issuer.example/dividend", "verified_on": "2026-10-28"}]}
        got, restored, _ = recover_passive_books(self.config, self.state, self.days, quotes,
                                                recorded_at="now", reviews=reviews)
        self.assertEqual(restored, ["hold"])
        self.assertEqual(got["books"]["hold"]["cash"], 50.5)
        self.assertEqual(got["books"]["hold"]["nav"], 153.5)
        again, restored, _ = recover_passive_books(self.config, got, self.days, quotes,
                                                  recorded_at="later", reviews=reviews)
        self.assertEqual(got, again)
        self.assertEqual(restored, [])
