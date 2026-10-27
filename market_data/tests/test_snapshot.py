"""Offline regression tests: no live Yahoo calls, trading or historical edits."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_data import collect, snapshot


DAY = "2026-10-27"
UTC = "2026-10-27T22:40:00+00:00"
NAMES = [f"S{i:03d}" for i in range(503)]


def bar(day=DAY, close=100.0):
    return {"date": day, "open": 100.0, "high": 105.0,
            "low": 95.0, "close": close, "volume": 1000,
            "dividend": 0.0, "split": 0.0}


def complete(*, missing=()):
    skip = set(missing)
    return {x: bar() for x in NAMES + ["SPY"] if x not in skip}


class SnapshotContractTests(unittest.TestCase):
    def test_one_and_thirteen_missing_are_isolated_without_fake_prices(self):
        for absent in ([NAMES[1]], NAMES[1:14]):
            record = snapshot.make_snapshot(DAY, NAMES, complete(missing=absent),
                                            captured_at_utc=UTC)
            self.assertEqual(record["coverage"]["missing"], len(absent))
            self.assertEqual(record["coverage"]["requested"], 504)
            self.assertEqual(record["coverage"]["frozen_constituents_observed"],
                             503 - len(absent))
            self.assertEqual(set(record["missing"]), set(absent))
            self.assertTrue(all(x not in record["bars"] for x in absent))
            snapshot.validate_snapshot(record, session=DAY)

    def test_no_stale_date_or_nonsense_ohlc(self):
        for invalid in (bar("2026-10-26"), {**bar(), "low": 110},
                        {**bar(), "close": float("nan")},
                        {**bar(), "open": 0}, {**bar(), "volume": -2}):
            with self.assertRaises(ValueError):
                snapshot.normalize_bar(invalid, DAY, "AAPL")
        self.assertEqual(snapshot.normalize_bar(bar(), DAY, "AAPL")["close"], 100)

    def test_rename_keeps_canonical_position_id(self):
        self.assertEqual(snapshot.provider_symbol("PSKY", "2026-10-05"), "PSKY")
        self.assertEqual(snapshot.provider_symbol("PSKY", "2026-10-06"), "SKYD")
        self.assertEqual(snapshot.provider_symbol("BRK.B", DAY), "BRK-B")
        universe = ["PSKY"] + NAMES[1:]
        record = snapshot.make_snapshot(DAY, universe,
                                        {"PSKY": bar(), "SPY": bar()},
                                        captured_at_utc=UTC)
        self.assertEqual(record["bars"]["PSKY"]["provider_symbol"], "SKYD")
        self.assertNotIn("SKYD", record["requested_symbols"])
        self.assertEqual(record["frozen_universe_size"], 503)

    def test_tampering_wrong_day_and_universe_rejected(self):
        record = snapshot.make_snapshot(DAY, NAMES, complete(), captured_at_utc=UTC)
        altered = copy.deepcopy(record)
        altered["bars"][NAMES[0]]["close"] = 101.0
        with self.assertRaisesRegex(ValueError, "checksum"):
            snapshot.validate_snapshot(altered)
        with self.assertRaisesRegex(ValueError, "Wrong XNYS session"):
            snapshot.validate_snapshot(record, session="2026-10-26")
        with self.assertRaises(ValueError):
            snapshot.make_snapshot(DAY, NAMES[:-1], complete(), captured_at_utc=UTC)

    def test_atomic_immutable_and_retries_without_timestamp_churn(self):
        record = snapshot.make_snapshot(DAY, NAMES, complete(), captured_at_utc=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, created = snapshot.write_immutable(root, record)
            self.assertTrue(created)
            prior = path.read_bytes()
            retry = snapshot.make_snapshot(DAY, NAMES, complete(),
                                           captured_at_utc="2026-10-27T23:00:00+00:00")
            path2, created = snapshot.write_immutable(root, retry)
            self.assertEqual(path, path2)
            self.assertFalse(created)
            self.assertEqual(path.read_bytes(), prior)
            changed_prices = complete()
            changed_prices[NAMES[0]]["close"] = 101
            revision = snapshot.make_snapshot(DAY, NAMES, changed_prices,
                                              captured_at_utc=UTC)
            with self.assertRaisesRegex(ValueError, "Immutable"):
                snapshot.write_immutable(root, revision)
            self.assertEqual(path.read_bytes(), prior)
            self.assertEqual(snapshot.load_snapshot(path, session=DAY)["sha256"],
                             record["sha256"])


class ProspectiveCollectorTests(unittest.TestCase):
    def test_partial_vendor_batch_and_bounded_single_symbol_recovery(self):
        requested = [NAMES[0], NAMES[1]]
        calls = []

        def mock_download(names, start, end, allow_missing=False):
            calls.append(list(names))
            if len(names) > 1:
                return {NAMES[0]: NAMES[0], "SPY": "SPY"}
            return {names[0]: names[0]}

        with patch.object(collect, "extract", side_effect=lambda _frame, day, _ticker: bar(day)):
            found, missing = collect.collect(DAY, requested, downloader=mock_download,
                                             attempts=2)
        self.assertEqual(set(found), set(requested) | {"SPY"})
        self.assertFalse(missing)
        self.assertEqual(calls, [[NAMES[0], NAMES[1], "SPY"], [NAMES[1]]])

    def test_missing_price_stays_missing_when_budget_exhausted(self):
        def mock_download(names, start, end, allow_missing=False):
            return {"SPY": "SPY"} if len(names) > 1 else {}

        with patch.object(collect, "extract", side_effect=lambda _frame, day, _ticker: bar(day)):
            found, missing = collect.collect(DAY, NAMES[:2], downloader=mock_download,
                                             attempts=1)
        self.assertEqual(list(found), ["SPY"])
        self.assertEqual(set(missing), set(NAMES[:2]))
        self.assertNotIn(NAMES[0], found)


if __name__ == "__main__":
    unittest.main()
