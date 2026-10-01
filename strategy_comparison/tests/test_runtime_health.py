import json
import tempfile
import unittest
from pathlib import Path

from strategy_comparison.runtime_health import atomic_write, build_record


class RuntimeHealthTests(unittest.TestCase):
    def test_build_record_is_small_and_explicit(self):
        row = build_record("tfm_es", "MIDAS TFM shadow forecasts", "failure", "123", "4", "a" * 40,
                           recorded_at="2026-10-01T00:00:00+00:00")
        self.assertEqual(row["schema_version"], 1)
        self.assertEqual(row["event"], "schedule")
        self.assertEqual(row["outcome"], "failure")
        self.assertEqual(row["run_id"], 123)
        self.assertNotIn("positions", row)

    def test_atomic_write_round_trip(self):
        row = build_record("paper_us", "MIDAS paper comparison", "success", "456", "7", "b" * 40,
                           recorded_at="2026-10-01T01:00:00+00:00")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            atomic_write(path, row)
            self.assertEqual(json.loads(path.read_text())["run_number"], 7)

    def test_rejects_unknown_outcome(self):
        with self.assertRaises(ValueError):
            build_record("x", "X", "maybe", "1", "1", "c" * 40)


if __name__ == "__main__":
    unittest.main()
