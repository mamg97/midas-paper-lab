import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from session_gate import session_due
from forward_portfolio import _new_state


class SessionGateTests(unittest.TestCase):
    def test_existing_session_skips_even_after_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diary.json"
            state = _new_state()
            state.update(last_session="2026-10-28", equity_history={"2026-10-28": 100000})
            path.write_text(json.dumps(state))
            check = Mock(side_effect=RuntimeError("late"))
            self.assertFalse(session_due(path, "2026-10-28", check))
            check.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "late"):
                session_due(path, "2026-10-29", check)

    def test_missing_diary_never_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "missing"):
                session_due(Path(directory) / "absent.json", "2026-10-29")
