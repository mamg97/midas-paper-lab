"""The scheduled TimesFM action and published health must use one identity."""
import unittest
from pathlib import Path


class OneDayWorkflowTelemetryContract(unittest.TestCase):
    def test_canonical_workflow_identity_matches_published_telemetry(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/timesfm_one_day.yml").read_text(encoding="utf-8")
        canonical = "MIDAS TimesFM 2.5 EUR daily 1-session signal"
        self.assertIn("name: " + canonical, workflow)
        self.assertIn('--workflow-name "' + canonical + '"', workflow)
        self.assertNotIn('--workflow-name "MIDAS TimesFM EUR one-day signal"', workflow)
        self.assertIn("--workflow-key timesfm_one_day", workflow)


if __name__ == "__main__":
    unittest.main()
