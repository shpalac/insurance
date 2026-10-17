"""Permanent acceptance tests for Issue #5: isolated CI and PR traceability."""

from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))

from integration_policy import closure_progress
from pr_traceability import publish, render, MARKER
from run_acceptance_manifest import AcceptanceError, load_targets, verify_report
from validate_issue_manifest import validate_body

HEAD = "a" * 40
BODY = (ROOT / ".factory/examples/valid-issue.md").read_text(encoding="utf-8")


def emit(n, name):
    path = ROOT / "reports" / f"issue-5-ac-{n}.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", tests="1", errors="0", failures="0",
                       skipped="0", assertions="2")
    ET.SubElement(suite, "testcase", classname="Issue5Acceptance", name=name)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


class FakeAPI:
    repo = "shpalac/insurance"
    def __init__(self):
        self.saved = []
        self.posts = 0
        self.pr = {
            "head": {"sha": HEAD}, "body": "Refs #142\nCompletes #142",
        }
    def call(self, method, path, data=None):
        if method == "GET":
            if path == "/pulls/19":
                return self.pr
            if path == "/actions/runs/123/jobs?per_page=100":
                return {"total_count": 2, "jobs": [
                    {"name": "issue-completion", "conclusion": "success"},
                    {"name": "factory-gate-preflight", "conclusion": "success"},
                ]}
            if path == "/issues/142":
                return {"number": 142, "body": BODY}
        if method == "POST" and path == "/issues/19/comments":
            self.saved.append({
                "id": 1, "body": data["body"], "user": {"type": "Bot"},
            })
            self.posts += 1
            return {}
        if method == "PATCH" and path == "/issues/comments/1":
            self.saved[0]["body"] = data["body"]
            return {}
        raise AssertionError((method, path))
    def comments(self, number):
        if number != 19:
            raise AssertionError(number)
        return list(self.saved)


def event():
    return {"workflow_run": {
        "name": "Factory selective CI", "event": "pull_request",
        "conclusion": "success", "head_sha": HEAD, "id": 123,
        "pull_requests": [{"number": 19}],
    }}


class Issue5Acceptance(unittest.TestCase):
    def test_ac_1_allowlisted_targets_never_execute_issue_shell_commands(self):
        self.assertEqual(validate_body(BODY, expected_issue_id=142), [])
        targets = load_targets(ROOT)
        self.assertTrue(targets)
        for target in targets.values():
            argv = target["argv"]
            self.assertEqual(argv[:3], ["python", "-m", "unittest"])
            self.assertNotIn("-c", argv)
        self.assertNotIn("shell=True", (
            ROOT / ".factory/scripts/run_acceptance_manifest.py"
        ).read_text(encoding="utf-8"))
        emit(1, self._testMethodName)

    def test_ac_2_nonempty_junit_assertions_and_skips_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d) / "evidence.xml"
            file.write_text(
                "<testsuite tests='1' assertions='3'>"
                "<testcase name='real'/></testsuite>"
            )
            self.assertEqual(verify_report(file), {"testcases": 1, "assertions": 3})
            file.write_text(
                "<testsuite assertions='3'><testcase name='unused'>"
                "<skipped/></testcase></testsuite>"
            )
            with self.assertRaises(AcceptanceError):
                verify_report(file)
            file.write_text("<testsuite assertions='0'></testsuite>")
            with self.assertRaises(AcceptanceError):
                verify_report(file)
        emit(2, self._testMethodName)

    def test_ac_3_successful_ci_publishes_one_idempotent_pr_traceability(self):
        api = FakeAPI()
        self.assertEqual(publish(event(), api), "created")
        self.assertEqual(publish(event(), api), "updated")
        self.assertEqual(api.posts, 1)
        self.assertEqual(len(api.saved), 1)
        message = api.saved[0]["body"]
        self.assertIn(MARKER, message)
        self.assertIn("142/AC-1", message)
        self.assertIn("ubuntu-latest", message)
        self.assertIn("https://github.com/shpalac/insurance/actions/runs/123", message)
        self.assertIn(HEAD, message)
        emit(3, self._testMethodName)

    def test_ac_4_partial_multi_pr_remains_open_until_full_default_branch(self):
        def proof(n, pr):
            return {
                "id": n, "status": "PASS", "verified_main_sha": HEAD,
                "assertions": 2, "permanent_regression": True,
                "artifact_url": f"https://github.com/shpalac/insurance/actions/runs/{pr}",
                "pr_number": pr, "merge_sha": "b" * 40,
            }
        a = closure_progress(
            criteria_ids=["AC-1", "AC-2"],
            evidence=[proof("AC-1", 11)], main_sha=HEAD,
        )
        b = closure_progress(
            criteria_ids=["AC-1", "AC-2"],
            evidence=[proof("AC-1", 11), proof("AC-2", 12)],
            main_sha=HEAD,
        )
        self.assertFalse(a["should_close"])
        self.assertEqual(a["missing_criteria"], ["AC-2"])
        self.assertTrue(b["should_close"])
        self.assertEqual(b["merged_prs"], [11, 12])
        emit(4, self._testMethodName)

    def test_ac_5_untrusted_fork_never_runs_with_write_token(self):
        isolated = (ROOT / ".github/workflows/issue-acceptance.yml").read_text()
        pub = (ROOT / ".github/workflows/factory-pr-traceability.yml").read_text()
        selective = (ROOT / ".github/workflows/ci-selective.yml").read_text()
        self.assertIn("permissions:\n  contents: read\njobs:", isolated)
        self.assertIn("permissions:\n  contents: read\nconcurrency:", pub)
        self.assertIn("pull-requests: write", pub)
        self.assertIn("ref: main", pub)
        self.assertNotIn("pull_request_target", pub)
        self.assertIn("types: [opened, synchronize, reopened, edited", selective)
        self.assertNotIn("pull_request_target", selective)
        self.assertIn("persist-credentials: false", pub)
        emit(5, self._testMethodName)


if __name__ == "__main__":
    unittest.main()
