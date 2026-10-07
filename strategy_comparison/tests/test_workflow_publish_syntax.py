import unittest
from pathlib import Path


class PublishWorkflowSyntaxTests(unittest.TestCase):
    def test_all_state_writers_use_shared_publish_helper(self):
        root = Path(__file__).resolve().parents[2]
        workflows = [
            root / ".github/workflows/paper_us.yml",
            root / ".github/workflows/capital_cycle.yml",
            root / ".github/workflows/tfm_es.yml",
            root / ".github/workflows/buy_the_dip_strategy.yml",
            root / ".github/workflows/weekly_ml.yml",
            root / ".github/workflows/tfg_ahp.yml",
        ]
        for path in workflows:
            text = path.read_text(encoding="utf-8")
            self.assertIn("strategy_comparison/publish_state.py", text, str(path))
            self.assertNotIn("\n            git push", text, str(path))

    def test_publish_state_shell_continuations_are_single_backslashes(self):
        root = Path(__file__).resolve().parents[2]
        workflows = [
            root / ".github/workflows/paper_us.yml",
            root / ".github/workflows/capital_cycle.yml",
            root / ".github/workflows/tfm_es.yml",
        ]
        for path in workflows:
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            for index, line in enumerate(lines):
                if "publish_state.py" not in line:
                    continue
                block = lines[index:index + 6]
                self.assertTrue(block, str(path))
                for continuation in block[:-1]:
                    if continuation.strip():
                        self.assertFalse(
                            continuation.rstrip().endswith("\\\\"),
                            f"{path}: double shell escape in {continuation!r}",
                        )


if __name__ == "__main__":
    unittest.main()
