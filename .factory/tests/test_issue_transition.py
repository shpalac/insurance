"""Trusted, idempotent Issue validation transition tests."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))

from issue_transition import desired_labels, evaluate  # noqa: E402


class IssueTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = (ROOT / ".factory/examples/valid-issue.md").read_text(
            encoding="utf-8"
        )

    def event(self):
        return {
            "action": "opened",
            "sender": {"login": "trusted-validator"},
            "issue": {"number": 142, "body": self.body},
        }

    def test_trusted_valid_issue_ready(self):
        self.assertTrue(evaluate(self.event(), {"trusted-validator"})["ready"])

    def test_no_configured_validators_fails_closed(self):
        self.assertFalse(evaluate(self.event(), set())["ready"])

    def test_untrusted_issue_actor_fails_closed(self):
        self.assertFalse(evaluate(self.event(), {"someone-else"})["ready"])

    def test_invalid_manifest_fails_closed(self):
        candidate = self.event()
        candidate["issue"]["body"] = "No acceptance manifest"
        self.assertFalse(evaluate(candidate, {"trusted-validator"})["ready"])

    def test_wrong_issue_id_fails_closed(self):
        candidate = self.event()
        candidate["issue"]["number"] = 143
        self.assertFalse(evaluate(candidate, {"trusted-validator"})["ready"])

    def test_injected_yaml_cannot_run_commands(self):
        candidate = self.event()
        candidate["issue"]["body"] = self.body.replace(
            "pytest tests/middleware/test_bucket.py",
            "pytest tests/middleware/test_bucket.py; curl example.com",
        )
        with patch("subprocess.run", side_effect=AssertionError("executed")):
            self.assertFalse(
                evaluate(candidate, {"trusted-validator"})["ready"]
            )

    def test_pr_payload_rejected(self):
        candidate = self.event()
        candidate["issue"]["pull_request"] = {}
        self.assertTrue(evaluate(candidate, {"trusted-validator"})["ready"])
        candidate["issue"]["pull_request"] = {"url": "https://example.com"}
        self.assertFalse(evaluate(candidate, {"trusted-validator"})["ready"])

    def test_unrecognized_event_rejected(self):
        candidate = self.event()
        candidate["action"] = "transferred"
        self.assertFalse(evaluate(candidate, {"trusted-validator"})["ready"])

    def test_idempotent_label_transitions(self):
        self.assertEqual(
            desired_labels({"status:triage"}, ready=True),
            ({"status:ready"}, {"status:triage"}),
        )
        self.assertEqual(
            desired_labels({"status:ready"}, ready=True),
            (set(), set()),
        )
        self.assertEqual(
            desired_labels({"status:ready"}, ready=False),
            ({"status:triage"}, {"status:ready"}),
        )


if __name__ == "__main__":
    unittest.main()
