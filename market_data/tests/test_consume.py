"""Offline read-only consumer regression tests for immutable XNYS source."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from market_data.consume import overlay
from market_data.snapshot import make_snapshot, write_immutable


DAY = "2026-10-27"
UNIVERSE = [f"S{i:03d}" for i in range(503)]


def row():
    return {"date": DAY, "open": 100, "high": 102, "low": 99,
            "close": 101, "volume": 500, "split": 0, "dividend": 0}


def prepared(root, observations):
    record = make_snapshot(DAY, UNIVERSE, observations,
                           captured_at_utc="2026-10-27T22:30:00+00:00")
    write_immutable(root, record)
    return record


class CommonConsumerTests(unittest.TestCase):
    def test_snapshot_absent_does_not_alter_vendor(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = {"AAPL": {"open": 10, "close": 11}}
            got, info = overlay(DAY, old, Path(tmp))
            self.assertEqual(got, old)
            self.assertIsNot(got, old)
            self.assertEqual(info["status"], "snapshot_absent")

    def test_reuse_only_absent_symbols_keep_other_direct_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = prepared(root, {UNIVERSE[0]: row(), "SPY": row()})
            old = {"SPY": {"open": 100., "high": 102., "low": 99.,
                            "close": 101., "dividend": 0., "split": 0.}}
            original = copy.deepcopy(old)
            got, info = overlay(DAY, old, root)
            self.assertEqual(got["SPY"], old["SPY"])
            self.assertEqual(got[UNIVERSE[0]]["close"], 101)
            self.assertNotIn(UNIVERSE[1], got)
            self.assertEqual(info["reused"], [UNIVERSE[0]])
            self.assertIn("SPY", info["verified"])
            self.assertEqual(info["hash"], record["sha256"])
            self.assertEqual(old, original)

    def test_disagreements_never_overwrite_established_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared(root, {"SPY": row()})
            old = {"SPY": {"open": 100., "high": 103., "low": 99.,
                            "close": 101., "dividend": 0., "split": 0.}}
            got, info = overlay(DAY, old, root)
            self.assertEqual(got["SPY"]["high"], 103)
            self.assertEqual(info["conflicts"], ["SPY"])
            self.assertEqual(info["reused"], [])

    def test_tampered_source_rejected_without_fake_marks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared(root, {"SPY": row()})
            target = root / "XNYS" / (DAY + ".json")
            value = json.loads(target.read_text())
            value["bars"]["SPY"]["close"] = 999
            target.write_text(json.dumps(value))
            got, info = overlay(DAY, {}, root)
            self.assertEqual(got, {})
            self.assertEqual(info["status"], "snapshot_rejected")


if __name__ == "__main__":
    unittest.main()
