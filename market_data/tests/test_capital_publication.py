"""Exercise the actual workflow publication gates for coordinated calls."""
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/capital_cycle.yml"


def enabled(step, event, common=False, preflight=False):
    body = WORKFLOW.read_text().split("      - name: " + step + "\n", 1)[1]
    expression = re.search(r"if: \$\{\{ (.+?) \}\}", body).group(1)
    expression = expression.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    return eval(expression, {"__builtins__": {}}, {
        "always": lambda: True,
        "github": SimpleNamespace(event_name=event),
        "inputs": SimpleNamespace(common_capture=common, preflight_only=preflight),
    })


class CapitalPublicationTests(unittest.TestCase):
    def test_coordinated_consumer_persists_but_does_not_replace_independent_runtime(self):
        for event in ("schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                self.assertTrue(enabled("Record capital-cycle paper state", event, common=True))
                self.assertTrue(enabled("Commit capital-cycle and dashboard state", event, common=True))
                self.assertFalse(enabled("Record scheduled runtime health", event, common=True))

    def test_preflight_and_code_events_never_publish_state(self):
        for event in ("pull_request", "push", "workflow_dispatch"):
            for common in (False, True):
                with self.subTest(event=event, common=common):
                    self.assertFalse(enabled("Commit capital-cycle and dashboard state", event, common, preflight=True))
        for event in ("pull_request", "push"):
            self.assertFalse(enabled("Commit capital-cycle and dashboard state", event))

    def test_independent_schedule_still_publishes_runtime_and_ledger(self):
        self.assertTrue(enabled("Record scheduled runtime health", "schedule"))
        self.assertTrue(enabled("Commit capital-cycle and dashboard state", "schedule"))
