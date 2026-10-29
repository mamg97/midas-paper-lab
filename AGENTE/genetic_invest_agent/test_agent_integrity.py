"""Safety checks for the legacy demo ledger; never touch its real diary."""

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE = Path(__file__).with_name("sp500_portfolio_agent.py")


def load_agent():
    spec = importlib.util.spec_from_file_location("midas_legacy_agent_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"dotenv": types.SimpleNamespace(load_dotenv=lambda: None)}):
        spec.loader.exec_module(module)
    return module


class LedgerIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = load_agent()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original_dir = self.agent.HISTORICO_DIR
        self.agent.HISTORICO_DIR = self.temp.name
        self.addCleanup(setattr, self.agent, "HISTORICO_DIR", self.original_dir)

    def test_corrupt_diary_does_not_reset_capital(self):
        diary = Path(self.temp.name) / "diario_portfolio.json"
        diary.write_text("{truncated", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            self.agent.PortfolioTracker()
        self.assertEqual(diary.read_text(encoding="utf-8"), "{truncated")

    def test_missing_diary_does_not_start_a_new_campaign(self):
        with self.assertRaisesRegex(FileNotFoundError, "Diario ausente"):
            self.agent.PortfolioTracker()
        self.assertEqual(os.listdir(self.temp.name), [])

    def test_missing_open_position_quote_keeps_diary_unchanged(self):
        tracker = self.agent.PortfolioTracker(allow_new=True)
        tracker.state["positions"] = {"TEST": {"shares": 1, "avg_price": 100, "sl": 90, "tp": 120}}
        tracker.save()
        diary = Path(tracker.path)
        before = diary.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "sin cotización"):
            tracker.process_today([], [], [], None)
        self.assertEqual(diary.read_bytes(), before)

    def test_save_replaces_complete_json_without_temporary_file(self):
        tracker = self.agent.PortfolioTracker(allow_new=True)
        tracker.state["cash"] = 87432.10
        tracker.save()
        self.assertEqual(json.loads(Path(tracker.path).read_text(encoding="utf-8"))["cash"], 87432.10)
        self.assertEqual([name for name in os.listdir(self.temp.name) if name.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
