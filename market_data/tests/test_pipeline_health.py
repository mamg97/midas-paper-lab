import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from market_data.publish_health import summarize
from market_data.snapshot import make_snapshot, write_immutable


class PipelineHealthTests(unittest.TestCase):
    def test_source_validity_does_not_hide_failed_or_paused_consumers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = "2026-10-27"
            row = {"date": day, "open": 100., "high": 102., "low": 99., "close": 101., "volume": 1.}
            record = make_snapshot(day, [f"S{i:03d}" for i in range(503)], {"SPY": row},
                                   captured_at_utc=day + "T23:00:00Z")
            write_immutable(root / "market_data/snapshots", record)
            path = root / "classic_sp500_state/ledger.json"
            path.parent.mkdir()
            path.write_text(json.dumps({"last_session": day, "books": {
                "one": {"equity": [{"date": day}]},
                "two": {"equity": [{"date": "2026-10-26"}], "paused_missing_quotes": {"since": day}}
            }}))
            result = summarize(root, day, {"consume-classic_sp500": {"result": "failure"}},
                               now=datetime(2026, 10, 28, tzinfo=timezone.utc))
            self.assertEqual(result["status"], "snapshot_verified")
            classic = result["consumers"]["classic_sp500"]
            self.assertEqual(classic["workflow_outcome"], "failure")
            self.assertEqual(classic["updated_books"], 1)
            self.assertEqual(classic["paused_books"], 1)
            self.assertEqual(classic["paused_book_ids"], ["two"])
            self.assertIsNone(result["consumers"]["weekly_ml_daily"]["updated_books"])

    def test_pipeline_calls_are_gated_by_publication_and_pr_never_captures(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/market_data_xnys.yml").read_text()
        self.assertIn("steps.capture.outputs.captured == 'true'", workflow)
        self.assertIn("needs.capture.outputs.published == 'success'", workflow)
        for name in ["classic_sp500", "buy_the_dip_strategy", "capital_cycle", "weekly_ml_daily", "timesfm_daily", "timesfm_one_day"]:
            target = (root / (".github/workflows/" + name + ".yml")).read_text()
            self.assertIn("workflow_call:", target)
            self.assertIn("python market_data/health.py --eligible", target)
            self.assertIn("inputs.common_capture && 'main' || github.ref", target)
            self.assertIn("uses: ./.github/workflows/" + name + ".yml", workflow)
