"""Durable missing-criterion diagnostics for zero-chat-context worker recovery."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from post_merge_closure import ReconcileError, blocked_message


class ClosureDiagnostics(unittest.TestCase):
    def test_missing_tests_are_reported_without_premature_closure(self):
        message = blocked_message({
            "reason": "acceptance_incomplete_or_untrusted_target",
            "missing_criteria": ["AC-1", "AC-4"],
        }, "a"*40)
        self.assertIn("Missing acceptance implementations: AC-1, AC-4", message)
        self.assertIn("intentionally open", message)
        self.assertIn(".factory/acceptance/issue_N/test_ac_K.py", message)

    def test_live_canary_blocker_lists_every_unproven_criterion(self):
        message = blocked_message({
            "reason": "acceptance_incomplete_or_untrusted_target",
            "missing_criteria": [],
            "unproven_criteria": ["AC-1", "AC-2", "AC-3", "AC-4"],
            "evidence_blocker": "live_two_issue_canary_not_verified",
        }, "a"*40)
        self.assertIn(
            "Acceptance criteria without verified proof: AC-1, AC-2, AC-3, AC-4",
            message,
        )
        self.assertIn("live_two_issue_canary_not_verified", message)
        self.assertIn("mocked tests alone do not satisfy the live canary", message)

    def test_untrusted_diagnostics_cannot_be_rendered(self):
        with self.assertRaises(ReconcileError):
            blocked_message({
                "reason": "acceptance_incomplete_or_untrusted_target",
                "missing_criteria": ["AC-1\nFAKE SUCCESS"],
            }, "a"*40)

    def test_invalid_reason_does_not_leak_into_public_issue(self):
        with self.assertRaises(ReconcileError):
            blocked_message({"reason": "injected secret"}, "a"*40)


if __name__ == "__main__":
    unittest.main()
