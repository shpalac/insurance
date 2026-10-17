"""AC-3: every future Issue uses Refs-only automatically, with safe partial PRs."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from acceptance_discovery import named_path
from pr_completion_gate import CompletionError, preflight
from post_merge_closure import linked_merged_prs
from integration_policy import closure_progress

SHA = "a" * 40
MANIFEST = {
    "acceptance_criteria": [
        {"id": "AC-1", "runner_os": "ubuntu-latest"},
        {"id": "AC-2", "runner_os": "ubuntu-latest"},
    ],
    "dependencies": {"multi_pr_allowed": True}
}
SOURCE = """import unittest
class Test(unittest.TestCase):
    def test_ac_{}_works(self):
        self.assertTrue(True)
"""


def issue():
    return {"number": 984, "state": "open", "body": "untrusted manifest data"}


def full(_body, *, issue_id, head_sha, root, criteria_subset=None):
    assert issue_id == 984 and head_sha == SHA
    ids = ["AC-1", "AC-2"]
    return [
        {"id": item, "status": "PASS", "head_sha": head_sha,
         "testcases": 1, "assertions": 2}
        for item in ids if criteria_subset is None or item in criteria_subset
    ]


class PrAcceptance(unittest.TestCase):
    def setup_tests(self, root, indices):
        for index in indices:
            path = named_path(root, 984, f"AC-{index}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(SOURCE.format(index))

    def preflight(self, root, *, multi=True, run=full):
        manifest = {
            **MANIFEST,
            "dependencies": {"multi_pr_allowed": multi}
        }
        with mock.patch("pr_completion_gate.load_targets", return_value={}), \
             mock.patch("pr_completion_gate.validate_body", return_value=[]), \
             mock.patch("pr_completion_gate.extract_manifest", return_value=manifest):
            return preflight("Refs #984", head_sha=SHA, root=root,
                             fetch_issue=lambda n: issue(), run=run)

    def test_ac_3_refs_only_complete_suite_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.setup_tests(root, [1, 2])
            result = self.preflight(root)
            self.assertEqual(result[0]["criteria"], ["AC-1", "AC-2"])
            self.assertEqual(result[0]["head_sha"], SHA)

    def test_ac_3_incomplete_multi_pr_stays_partial_and_tests_shipped_slice(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.setup_tests(root, [1])
            result = self.preflight(root)
            self.assertEqual(result[0]["partial_criteria"], ["AC-1"])
            self.assertFalse(result[0]["complete"])
            def failed(*args, **kwargs):
                items = full(*args, **kwargs)
                items[0]["status"] = "FAIL"
                return items
            with self.assertRaises(CompletionError):
                self.preflight(root, run=failed)

    def test_ac_3_single_pr_without_complete_proof_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(CompletionError):
                self.preflight(Path(folder), multi=False)

    def test_ac_3_refs_only_merge_is_discoverable_and_missing_ac_does_not_close(self):
        class MockAPI:
            def get(self, endpoint):
                return {"status": "ahead", "behind_by": 0}
        refs = linked_merged_prs(984, [{
            "number": 125, "body": "Refs #984\n", "base": {"ref": "main"},
            "merged_at": "2026-10-17T00:00:00Z",
            "merge_commit_sha": "b" * 40,
        }], MockAPI(), SHA)
        self.assertEqual(len(refs), 1)
        def evidence(ac):
            return {
                "id": ac, "status": "PASS", "verified_main_sha": SHA,
                "assertions": 2, "artifact_url": "https://github.com/shpalac/insurance/actions/runs/22",
                "merge_sha": "b"*40, "pr_number": 125,
                "permanent_regression": True,
            }
        incomplete = closure_progress(criteria_ids=["AC-1", "AC-2"],
                                      evidence=[evidence("AC-1")], main_sha=SHA)
        full_result = closure_progress(criteria_ids=["AC-1", "AC-2"],
                                       evidence=[evidence("AC-1"), evidence("AC-2")],
                                       main_sha=SHA)
        self.assertFalse(incomplete["should_close"])
        self.assertTrue(full_result["should_close"])


if __name__ == "__main__":
    unittest.main()
