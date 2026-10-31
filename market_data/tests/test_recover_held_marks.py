"""Regression tests: historical missing held bars are never fabricated or traded."""
import json
import tempfile
import unittest
from pathlib import Path

from market_data import recover_held_marks as recovery
from market_data.revisions import load_effective
from market_data.snapshot import make_snapshot, write_immutable

DAYS = ("2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30")
UNIVERSE = ["HUBB"] + [f"S{i:03d}" for i in range(502)]
TIMESTAMP = "2026-10-31T10:30:00+00:00"


def bar(day):
    return {"date": day, "open": 430., "high": 440., "low": 420.,
            "close": 435., "volume": 100000, "dividend": 0., "split": 0.}


def state():
    return {"last_session": "2026-10-30",
            "books": {
                "buy_hold_equal_weight": {
                    "positions": {"HUBB": {"shares": 10}},
                    "pending": {},
                    "paused_missing_quotes": {
                        "since": "2026-10-28",
                        "last_valued_session": "2026-10-27",
                        "missing_tickers": ["HUBB"]}},
                "macd": {"positions": {}, "pending": {}}}}


class HistoricalHeldRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "snapshots"
        self.ledger = self.base / "ledger.json"
        self.ledger.write_text(json.dumps(state()))
        for day in DAYS:
            observations = {"SPY": bar(day)}
            if day == DAYS[0]:
                observations["HUBB"] = bar(day)
            original = make_snapshot(
                day, UNIVERSE, observations,
                captured_at_utc=f"{day}T23:30:00+00:00")
            write_immutable(self.root, original)

    def test_only_paused_held_symbol_and_true_gap_dates(self):
        self.assertEqual(recovery.eligible_targets(
            self.root, state(), "2026-10-30"),
            [(x, ["HUBB"]) for x in DAYS[1:]])

    def test_verified_revision_appended_without_touching_original_or_ledger(self):
        day = DAYS[1]
        base = self.root / "XNYS" / (day + ".json")
        prior, ledger = base.read_bytes(), self.ledger.read_bytes()
        out = recovery.recover_one(
            self.root, day, ["HUBB"],
            download=lambda _d, names, **_kw: ({"HUBB": bar(day)}, {}),
            timestamp=TIMESTAMP)
        self.assertEqual(out["status"], "revision_written")
        self.assertEqual(base.read_bytes(), prior)
        self.assertEqual(self.ledger.read_bytes(), ledger)
        effective = load_effective(self.root, day)
        self.assertEqual(effective["bars"]["HUBB"]["close"], 435)
        self.assertEqual(effective["revision_hashes"], [out["sha256"]])
        self.assertEqual(recovery.recover_one(
            self.root, day, ["HUBB"],
            download=lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("No provider call when recovered"))["status"],
            "already_complete")

    def test_missing_vendor_data_no_revision(self):
        result = recovery.recover_one(
            self.root, DAYS[1], ["HUBB"],
            download=lambda *_a, **_kw: ({}, {"HUBB": "missing_asof"}))
        self.assertEqual(result["status"], "still_missing")
        self.assertEqual(load_effective(self.root, DAYS[1])["revision_hashes"], [])

    def test_corporate_action_requires_manual_review(self):
        with_actions = {**bar(DAYS[2]), "split": 2}
        result = recovery.recover_one(
            self.root, DAYS[2], ["HUBB"],
            download=lambda *_a, **_kw: ({"HUBB": with_actions}, {}))
        self.assertEqual(result["corporate_action_review"], ["HUBB"])
        self.assertFalse(load_effective(self.root, DAYS[2])["revision_hashes"])

    def test_injected_symbol_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexpected"):
            recovery.recover_one(
                self.root, DAYS[2], ["HUBB"],
                download=lambda *_a, **_kw: ({"MSFT": bar(DAYS[2])}, {}))

    def test_refuses_future_price_and_bad_paused_state(self):
        with self.assertRaisesRegex(ValueError, "older than ledger"):
            recovery.eligible_targets(self.root, state(), "2026-10-29")
        wrong = state()
        wrong["books"]["buy_hold_equal_weight"]["paused_missing_quotes"]["missing_tickers"] = ["SPY"]
        with self.assertRaisesRegex(ValueError, "genuinely held"):
            recovery.paused_requirements(wrong)

    def test_preflight_does_not_call_yahoo_or_mutate_snapshots(self):
        result = recovery.execute(
            root=self.root, ledger_path=self.ledger,
            when=("2026-10-30", "2026-10-29", "2026-11-02", False),
            dry_run=True)
        self.assertEqual([x["session"] for x in result["candidates"]], list(DAYS[1:]))
        self.assertEqual(list((self.root / "XNYS").glob("*.revisions")), [])


if __name__ == "__main__":
    unittest.main()
