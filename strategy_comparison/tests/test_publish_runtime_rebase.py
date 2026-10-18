"""Regression tests for preserving successful MIDAS workflow retries."""
import json
import tempfile
import unittest
from pathlib import Path

from strategy_comparison.publish_state import (
    should_restore_runtime, preserve_newer_runtime, runtime_rank,
)


def record(run, attempt, outcome="success", name="buy_the_dip_strategy"):
    return {
        "schema_version": 1,
        "workflow_key": name,
        "workflow_name": "MIDAS Buy The Dip paper",
        "event": "schedule",
        "outcome": outcome,
        "run_id": 38990573157,
        "run_number": run,
        "run_attempt": attempt,
    }


class PublishRuntimeTests(unittest.TestCase):
    def test_same_run_later_success_replaces_previous_failure(self):
        self.assertTrue(should_restore_runtime(
            record(58, 2), record(58, 1, "failure")))
        self.assertEqual(runtime_rank(record(58, 2)), ("buy_the_dip_strategy", 58, 2))

    def test_newer_number_is_not_overwritten_by_older_retry(self):
        self.assertFalse(should_restore_runtime(record(58, 2), record(59, 1)))
        self.assertFalse(should_restore_runtime(record(58, 1), record(58, 2)))

    def test_same_attempt_and_other_workflow_are_not_overwritten(self):
        self.assertFalse(should_restore_runtime(record(58, 1), record(58, 1, "failure")))
        self.assertFalse(should_restore_runtime(
            record(58, 2), record(57, 1, name="classic_sp500")))
        self.assertFalse(should_restore_runtime(
            {**record(58, 2), "event": "push"}, record(58, 1)))
        self.assertIsNone(runtime_rank({"event": "schedule", "run_number": "bad"}))

    def test_rebase_restores_only_owned_newer_record(self):
        candidate = record(58, 2)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "buy_the_dip.json"
            path.write_text(json.dumps(record(58, 1, "failure")), encoding="utf-8")
            self.assertEqual(preserve_newer_runtime({str(path): candidate}), [str(path)])
            self.assertEqual(json.loads(path.read_text())["outcome"], "success")
            self.assertEqual(json.loads(path.read_text())["run_attempt"], 2)
            # Stable: no second rewrite when the already-published record wins.
            self.assertEqual(preserve_newer_runtime({str(path): candidate}), [])
            path.write_text(json.dumps(record(59, 1, "failure")), encoding="utf-8")
            self.assertEqual(preserve_newer_runtime({str(path): candidate}), [])
            self.assertEqual(json.loads(path.read_text())["run_number"], 59)


if __name__ == "__main__":
    unittest.main()
