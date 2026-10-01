import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from promote_candidate import promote


def write_candidate(root, manifest_count, captions, marker):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    report = {
        "manifest_count": manifest_count,
        "caption_coverage": {"available": captions, "missing": max(0, manifest_count-captions), "pct": 0},
        "caption_transport": {"status": marker},
    }
    (root/"corpus_report.json").write_text(json.dumps(report), encoding="utf-8")
    (root/"corpus_report.md").write_text(marker, encoding="utf-8")
    (root/"manifest.json").write_text(json.dumps({"marker": marker}), encoding="utf-8")
    (root/"corpus_features.json").write_text(json.dumps({"marker": marker}), encoding="utf-8")
    (root/"semantic_queue.json").write_text(json.dumps({"marker": marker}), encoding="utf-8")


class PromotionTests(unittest.TestCase):
    def test_initial_candidate_is_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate=Path(tmp)/"candidate"
            state=Path(tmp)/"state"
            write_candidate(candidate,300,0,"first")
            status=promote(candidate,state)
            self.assertTrue(status["promoted"])
            self.assertEqual((state/"corpus_report.md").read_text(),"first")

    def test_caption_regression_never_overwrites_good_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate=Path(tmp)/"candidate"
            state=Path(tmp)/"state"
            write_candidate(state,300,200,"good")
            write_candidate(candidate,300,0,"blocked")
            status=promote(candidate,state)
            self.assertFalse(status["promoted"])
            self.assertEqual(status["reason"],"candidate_caption_coverage_regressed")
            self.assertEqual((state/"corpus_report.md").read_text(),"good")
            self.assertTrue((state/"ingestion_status.json").exists())

    def test_equal_coverage_can_refresh_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate=Path(tmp)/"candidate"
            state=Path(tmp)/"state"
            write_candidate(state,300,0,"old")
            write_candidate(candidate,301,0,"new")
            status=promote(candidate,state)
            self.assertTrue(status["promoted"])
            self.assertEqual((state/"corpus_report.md").read_text(),"new")


if __name__ == "__main__":
    unittest.main()
