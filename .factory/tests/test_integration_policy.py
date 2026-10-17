"""Pure integration-state guardrail tests including multi-PR closure."""

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from integration_policy import assess_merge, closure_progress  # noqa: E402

HEAD = "a" * 40


def approved_pr():
    return {
        "head_sha": HEAD,
        "base_branch": "main",
        "draft": False,
        "conflicted": False,
        "hold": False,
        "labels": [],
        "integrity_sha": HEAD,
        "checks": {
            name: {"head_sha": HEAD, "conclusion": "success"}
            for name in ("factory-gate", "acceptance-gate")
        },
        "author": "dev-agent",
        "reviews": [{
            "verdict": "APPROVE", "head_sha": HEAD,
            "reviewer": "independent-reviewer", "trusted_identity": True,
        }],
        "unresolved_threads": 0,
        "changed_paths": ["src/insurance/core.py"],
        "maintainer_authorized": False,
        "scope_compliant": True,
        "validated_issue": True,
    }


class IntegrationTests(unittest.TestCase):
    def test_approved_green_pr_may_enter_queue(self):
        self.assertEqual(assess_merge(approved_pr()), [])

    def test_no_reviews_needed_for_ci_green_pr(self):
        pr = approved_pr()
        pr["reviews"] = []
        self.assertEqual(assess_merge(pr), [])

    def test_self_or_stale_reviews_do_not_gate_merges(self):
        pr = approved_pr()
        pr["reviews"][0]["reviewer"] = "dev-agent"
        pr["reviews"][0]["head_sha"] = "b" * 40
        self.assertEqual(assess_merge(pr), [])

    def test_failed_acceptance_blocks(self):
        pr = approved_pr()
        pr["checks"]["acceptance-gate"]["conclusion"] = "failure"
        self.assertTrue(assess_merge(pr))

    def test_unresolved_review_threads_are_not_required_for_ci_only_policy(self):
        pr = approved_pr()
        pr["unresolved_threads"] = 1
        self.assertEqual(assess_merge(pr), [])

    def test_protected_paths_require_maintainer(self):
        pr = approved_pr()
        pr["changed_paths"] = [".github/workflows/prod.yml"]
        self.assertTrue(assess_merge(pr))
        pr["maintainer_authorized"] = True
        self.assertEqual(assess_merge(pr), [])

    def test_unknown_mergeability_blocks(self):
        pr = approved_pr()
        pr["conflicted"] = None
        self.assertTrue(assess_merge(pr))

    def test_unverified_sha_blocks(self):
        pr = approved_pr()
        pr["integrity_sha"] = "b" * 40
        self.assertTrue(assess_merge(pr))

    def record(self, ac, pr_number):
        return {
            "id": ac, "verified_main_sha": HEAD, "status": "PASS",
            "assertions": 2, "permanent_regression": True,
            "artifact_url": f"https://example.com/report/{pr_number}",
            "merge_sha": "b" * 40, "pr_number": pr_number,
        }

    def test_partial_multipr_issue_stays_open(self):
        result = closure_progress(
            criteria_ids=["AC-1", "AC-2", "AC-3"],
            evidence=[self.record("AC-1", 21), self.record("AC-2", 22)],
            main_sha=HEAD,
        )
        self.assertFalse(result["should_close"])
        self.assertEqual(result["missing_criteria"], ["AC-3"])

    def test_all_criteria_close_once(self):
        evidence = [self.record("AC-1", 21), self.record("AC-2", 22)]
        result = closure_progress(
            criteria_ids=["AC-1", "AC-2"], evidence=evidence, main_sha=HEAD
        )
        self.assertTrue(result["should_close"])
        self.assertEqual(result["merged_prs"], [21, 22])
        again = closure_progress(
            criteria_ids=["AC-1", "AC-2"], evidence=evidence, main_sha=HEAD,
            issue_closed=True,
        )
        self.assertFalse(again["should_close"])

    def test_main_sha_mismatch_blocks_closure(self):
        record = self.record("AC-1", 21)
        record["verified_main_sha"] = "c" * 40
        result = closure_progress(
            criteria_ids=["AC-1"], evidence=[record], main_sha=HEAD
        )
        self.assertFalse(result["should_close"])

    def test_no_regression_registration_blocks_closure(self):
        record = self.record("AC-1", 21)
        record["permanent_regression"] = False
        result = closure_progress(
            criteria_ids=["AC-1"], evidence=[record], main_sha=HEAD
        )
        self.assertFalse(result["should_close"])


if __name__ == "__main__":
    unittest.main()
