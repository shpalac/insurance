"""Auto-verification must not depend on manual completion markers."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))

from pr_completion_gate import CompletionError, preflight
from post_merge_closure import linked_merged_prs

SHA = "a" * 40
BODY = (ROOT / ".factory/examples/valid-issue.md").read_text(encoding="utf-8")
MULTI = BODY.replace("multi_pr_allowed: false", "multi_pr_allowed: true")


def issue(body=MULTI):
    return {"number": 142, "state": "open", "body": body}


def registered():
    return {"142/AC-1": {"argv": ["python", "-m", "unittest"], "runner_os": "ubuntu-latest"},
            "142/AC-2": {"argv": ["python", "-m", "unittest"], "runner_os": "ubuntu-latest"}}


def passing(_body, *, issue_id, head_sha, root, criteria_subset=None):
    assert issue_id == 142 and head_sha == SHA
    return [
        {"id": n, "status": "PASS", "head_sha": SHA,
         "testcases": 1, "assertions": 2}
        for n in ("AC-1", "AC-2")
        if criteria_subset is None or n in criteria_subset
    ]


class AutomaticAcceptanceTests(unittest.TestCase):
    def test_refs_only_runs_complete_acceptance_without_completes(self):
        with mock.patch("pr_completion_gate.load_targets", return_value=registered()):
            rows = preflight("Refs #142\n", head_sha=SHA,
                             fetch_issue=lambda n: issue(), run=passing)
        self.assertEqual(rows, [{
            "issue": 142, "criteria": ["AC-1", "AC-2"], "head_sha": SHA
        }])

    def test_partial_multi_pr_can_merge_without_false_closure(self):
        with mock.patch("pr_completion_gate.load_targets",
                        return_value={"142/AC-1": registered()["142/AC-1"]}):
            rows = preflight("Refs #142", head_sha=SHA,
                             fetch_issue=lambda n: issue(),
                             run=lambda *a, **k: self.fail("partial tests should not run"))
        self.assertEqual(rows, [])

    def test_complete_targets_with_failure_block_merge(self):
        def fail(*args, **kwargs):
            rows = passing(*args, **kwargs)
            rows[1]["status"] = "FAIL"
            return rows
        with mock.patch("pr_completion_gate.load_targets", return_value=registered()):
            with self.assertRaisesRegex(CompletionError, "insufficient test evidence"):
                preflight("Refs #142", head_sha=SHA,
                          fetch_issue=lambda n: issue(), run=fail)

    def test_complete_targets_with_missing_criterion_block_merge(self):
        with mock.patch("pr_completion_gate.load_targets", return_value=registered()):
            with self.assertRaisesRegex(CompletionError, "incomplete criterion"):
                preflight("Refs #142", head_sha=SHA,
                          fetch_issue=lambda n: issue(),
                          run=lambda *a, **k: passing(*a, **k)[:1])

    def test_single_pr_partial_never_merges(self):
        with mock.patch("pr_completion_gate.load_targets", return_value={}):
            with self.assertRaisesRegex(CompletionError, "single-PR"):
                preflight("Refs #142", head_sha=SHA,
                          fetch_issue=lambda n: issue(body=BODY))

    def test_merged_refs_only_pr_is_discoverable_for_automatic_closure(self):
        class Fake:
            def get(self, endpoint):
                return {"status": "ahead", "behind_by": 0}
        prs = [{
            "number": 49, "merged_at": "2026-10-17T12:00:00Z",
            "base": {"ref": "main"}, "merge_commit_sha": "b" * 40,
            "body": "Refs #142\n\nNo manual completion marker.",
        }]
        self.assertEqual(linked_merged_prs(142, prs, Fake(), SHA), [
            {"number": 49, "merge_sha": "b" * 40}
        ])


if __name__ == "__main__":
    unittest.main()
