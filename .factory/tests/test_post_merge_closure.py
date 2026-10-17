"""Post-merge closure must be SHA-pinned, evidence-driven and idempotent."""

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))

from post_merge_closure import (  # noqa: E402
    ReconcileError, apply, audit_marker, linked_merged_prs, prepare,
    require_main_checks, STATUS_MARKER,
)

SHA = "a" * 40
PR_SHA = "b" * 40
BODY = (ROOT / ".factory/examples/valid-issue.md").read_text(encoding="utf-8")


class FakeGitHub:
    repo = "shpalac/insurance"

    def __init__(self):
        self.head = SHA
        self.good_checks = True
        self.issues = {
            142: {"number": 142, "state": "open", "body": BODY},
        }
        self.prs = [{
            "number": 21, "base": {"ref": "main"}, "state": "closed",
            "merged_at": "2026-10-17T12:00:00Z",
            "merge_commit_sha": PR_SHA, "body": "Refs #142\n\nTests included.",
        }]
        self.comments = {142: []}
        self.posts = []
        self.patches = []
        self.fail_ancestry = False

    def get(self, endpoint):
        if endpoint == "/git/ref/heads/main":
            return {"object": {"sha": self.head}}
        if endpoint.startswith("/commits/") and endpoint.endswith("/check-runs?per_page=100"):
            checks = [{
                "name": name, "head_sha": SHA, "status": "completed",
                "conclusion": "success", "app": {"slug": "github-actions"},
            } for name in ("unit-tests", "factory-bootstrap-gate",
                           "factory-gate-preflight")]
            if not self.good_checks:
                checks[-1]["conclusion"] = "failure"
            return {"total_count": len(checks), "check_runs": checks}
        if endpoint.startswith("/compare/"):
            return {
                "status": "diverged" if self.fail_ancestry else "ahead",
                "behind_by": 1 if self.fail_ancestry else 0,
            }
        if endpoint.startswith("/issues/") and endpoint.count("/") == 2:
            return self.issues[int(endpoint.rsplit("/", 1)[1])]
        if endpoint.startswith("/pulls/") and endpoint.count("/") == 2:
            number = int(endpoint.rsplit("/", 1)[1])
            return next(pr for pr in self.prs if pr["number"] == number)
        raise AssertionError("Unexpected GET: " + endpoint)

    def pages(self, endpoint, *, limit=1000):
        if endpoint.startswith("/issues?"):
            return list(self.issues.values())
        if endpoint.startswith("/pulls?"):
            return list(self.prs)
        if endpoint.endswith("/comments"):
            number = int(endpoint.split("/")[2])
            return list(self.comments.get(number, []))
        raise AssertionError("Unexpected pages: " + endpoint)

    def post(self, endpoint, data):
        self.posts.append((endpoint, copy.deepcopy(data)))
        if endpoint.endswith("/comments"):
            number = int(endpoint.split("/")[2])
            self.comments.setdefault(number, []).append({
                "id": len(self.posts), "body": data["body"],
            })
            return {}
        raise AssertionError("Unexpected POST: " + endpoint)

    def patch(self, endpoint, data):
        self.patches.append((endpoint, copy.deepcopy(data)))
        if endpoint.startswith("/issues/comments/"):
            comment_id = int(endpoint.rsplit("/", 1)[1])
            for entries in self.comments.values():
                for entry in entries:
                    if entry["id"] == comment_id:
                        entry["body"] = data["body"]
                        return {}
        elif endpoint.startswith("/issues/"):
            number = int(endpoint.rsplit("/", 1)[1])
            self.issues[number]["state"] = data["state"]
            return {}
        raise AssertionError("Unexpected PATCH: " + endpoint)


def passing_run(body, *, issue_id, head_sha, root, criteria_subset=None):
    assert issue_id == 142 and head_sha == SHA
    assert "factory-acceptance-manifest" in body
    return [r for r in [
        {"id": "AC-1", "status": "PASS", "assertions": 3,
         "testcases": 2, "head_sha": SHA},
        {"id": "AC-2", "status": "PASS", "assertions": 1,
         "testcases": 1, "head_sha": SHA},
    ] if criteria_subset is None or r["id"] in criteria_subset]


class ClosureTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()

    def test_complete_merged_issue_audits_and_closes(self):
        plan = prepare(self.api, SHA, 12345, run=passing_run)
        self.assertEqual(plan["items"][0]["status"], "ready")
        result = apply(self.api, SHA, plan)
        self.assertEqual(result["closed"], [142])
        self.assertEqual(self.api.issues[142]["state"], "closed")
        body = self.api.comments[142][0]["body"]
        self.assertIn(audit_marker(142, SHA), body)
        self.assertIn("AC-2", body)
        self.assertIn("12345", body)

    def test_repeated_apply_does_not_duplicate_audit_or_close(self):
        plan = prepare(self.api, SHA, 12345, run=passing_run)
        apply(self.api, SHA, plan)
        self.assertEqual(apply(self.api, SHA, plan)["closed"], [])
        self.assertEqual(len(self.api.comments[142]), 1)
        self.assertEqual(len(self.api.patches), 1)

    def test_crash_between_audit_and_close_is_replay_safe(self):
        plan = prepare(self.api, SHA, 12345, run=passing_run)
        self.api.comments[142] = [{"id": 1, "body": audit_marker(142, SHA)}]
        result = apply(self.api, SHA, plan)
        self.assertEqual(result["closed"], [142])
        self.assertEqual(len(self.api.comments[142]), 1)

    def test_issue_with_no_manifest_stays_open_and_comment_idempotent(self):
        self.api.issues[142]["body"] = "An issue with no executable manifest"
        plan = prepare(self.api, SHA, 5)
        self.assertEqual(plan["items"][0]["status"], "blocked")
        self.assertEqual(apply(self.api, SHA, plan)["closed"], [])
        self.assertEqual(apply(self.api, SHA, plan)["closed"], [])
        self.assertEqual(self.api.issues[142]["state"], "open")
        self.assertEqual(len(self.api.comments[142]), 1)
        self.assertIn(STATUS_MARKER, self.api.comments[142][0]["body"])

    def test_failed_required_check_blocks_all_mutations(self):
        self.api.good_checks = False
        with self.assertRaises(ReconcileError):
            prepare(self.api, SHA, 9, run=passing_run)
        self.assertFalse(self.api.posts)
        self.assertFalse(self.api.patches)

    def test_changed_head_between_proof_and_apply_fails_closed(self):
        plan = prepare(self.api, SHA, 9, run=passing_run)
        self.api.head = "c" * 40
        with self.assertRaises(ReconcileError):
            apply(self.api, SHA, plan)
        self.assertEqual(self.api.issues[142]["state"], "open")

    def test_changed_issue_body_never_closes(self):
        plan = prepare(self.api, SHA, 9, run=passing_run)
        self.api.issues[142]["body"] += "\nImportant new acceptance criteria."
        result = apply(self.api, SHA, plan)
        self.assertFalse(result["closed"])
        self.assertEqual(self.api.issues[142]["state"], "open")

    def test_unmerged_or_unrelated_pr_does_not_complete_issue(self):
        self.api.prs[0]["merged_at"] = None
        self.assertFalse(prepare(self.api, SHA, 9, run=passing_run)["items"])
        self.api.prs[0]["merged_at"] = "2026-10-17T12:00:00Z"
        self.api.prs[0]["body"] = "Refs #1429"
        self.assertFalse(linked_merged_prs(142, self.api.prs, self.api, SHA))

    def test_unmerged_ancestry_rejected(self):
        self.api.fail_ancestry = True
        self.assertFalse(prepare(self.api, SHA, 9, run=passing_run)["items"])

    def test_partial_acceptance_does_not_close(self):
        def incomplete(*args, **kwargs):
            return passing_run(*args, **kwargs)[:1]
        plan = prepare(self.api, SHA, 9, run=incomplete)
        self.assertEqual(plan["items"][0]["status"], "blocked")
        self.assertEqual(apply(self.api, SHA, plan)["closed"], [])

    def test_zero_assertions_does_not_close(self):
        def empty(*args, **kwargs):
            rows = passing_run(*args, **kwargs)
            rows[1]["assertions"] = 0
            return rows
        plan = prepare(self.api, SHA, 9, run=empty)
        self.assertEqual(plan["items"][0]["status"], "blocked")

    def test_unsupported_runner_stays_open(self):
        self.api.issues[142]["body"] = BODY.replace(
            "runner_os: ubuntu-latest", "runner_os: macos-latest", 1
        )
        plan = prepare(self.api, SHA, 9, run=passing_run)
        self.assertEqual(plan["items"][0]["reason"],
                         "unsupported_runner_pending_hosted_verification")
        self.assertEqual(apply(self.api, SHA, plan)["closed"], [])

    def test_tampered_evidence_does_not_close(self):
        plan = prepare(self.api, SHA, 9, run=passing_run)
        plan["items"][0]["evidence"][0]["verified_main_sha"] = "c" * 40
        result = apply(self.api, SHA, plan)
        self.assertFalse(result["closed"])
        self.assertEqual(self.api.issues[142]["state"], "open")

    def test_linked_pr_mutation_between_stages_blocks(self):
        plan = prepare(self.api, SHA, 9, run=passing_run)
        self.api.prs[0]["merged_at"] = None
        with self.assertRaises(ReconcileError):
            apply(self.api, SHA, plan)


if __name__ == "__main__":
    unittest.main()
