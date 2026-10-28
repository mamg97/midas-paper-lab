"""Source availability cannot stand in for engine or accounting success."""
import json
import tempfile
import unittest
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from market_data.health import inspect_source
from market_data.snapshot import make_snapshot, write_immutable

DAY = "2026-10-27"
NOW = datetime(2026, 10, 27, 23, tzinfo=timezone.utc)


class SourceHealthTests(unittest.TestCase):
    def test_public_snapshot_is_publishable_but_other_snapshot_trees_stay_ignored(self):
        root = Path(__file__).resolve().parents[2]
        for path, ignored in [
            ("market_data/snapshots/XNYS/2026-10-27.json", False),
            ("market_data/snapshots/XNYS/debug.txt", True),
            ("market_data/snapshots/private/secrets.json", True),
            ("other/snapshots/XNYS/2026-10-27.json", True),
        ]:
            with self.subTest(path=path):
                result = subprocess.run(["git", "check-ignore", "--no-index", "-q", path],
                                        cwd=root, capture_output=True)
                self.assertEqual(result.returncode, 0 if ignored else 1)

    def test_verified_partial_source_reports_age_hash_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = [f"S{i:03d}" for i in range(503)]
            row = {"date": DAY, "open": 100, "high": 103, "low": 99,
                   "close": 102, "volume": 500, "dividend": 0, "split": 0}
            record = make_snapshot(DAY, names, {"SPY": row},
                                   captured_at_utc="2026-10-27T22:00:00+00:00")
            path, _ = write_immutable(root, record)
            prior = path.read_bytes()
            result = inspect_source(root, DAY, now=NOW)
            self.assertEqual(result["status"], "snapshot_verified")
            self.assertEqual(result["sha256"], record["sha256"])
            self.assertEqual(result["age_seconds"], 3600)
            self.assertEqual(len(result["missing_symbols"]), 503)
            self.assertEqual(result["engine_health"], "not_assessed")
            self.assertEqual(path.read_bytes(), prior)
            self.assertEqual(inspect_source(root, "2026-10-28", now=NOW)["status"],
                             "snapshot_absent")
            self.assertEqual(inspect_source(root, DAY, now=NOW.replace(hour=21))["status"],
                             "snapshot_rejected")
            broken = json.loads(path.read_text())
            broken["sha256"] = "bad"
            path.write_text(json.dumps(broken))
            rejected = inspect_source(root, DAY, now=NOW)
            self.assertEqual(rejected["status"], "snapshot_rejected")
            self.assertIsNone(rejected["coverage"])

    def test_absent_source_never_claims_empty_missing_list_or_engine_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_source(Path(tmp), DAY, now=NOW)
        self.assertEqual(result["status"], "snapshot_absent")
        self.assertIsNone(result["missing_symbols"])
        self.assertIsNone(result["sha256"])
        self.assertEqual(result["engine_health"], "not_assessed")
