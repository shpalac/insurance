"""Permanent acceptance tests for Issue #37 exact-SHA admission."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from checkout_identity import verify_identity
from compute_impact import impacted
from verify_factory_gate import gate_errors

A, B, C = "a" * 40, "b" * 40, "c" * 40


def emit(n: int, name: str):
    path = ROOT / "reports" / f"ac-{n}.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", tests="1", errors="0", failures="0",
                       skipped="0", assertions="3")
    ET.SubElement(suite, "testcase", classname="Issue37Acceptance", name=name)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


class Issue37Acceptance(unittest.TestCase):
    def test_ac_1_exact_checkout_and_merge_parent_fails_on_stale_sha(self):
        self.assertEqual(verify_identity(A, A, B, "pull_request", (C, B)), [])
        self.assertTrue(verify_identity(A, C, B, "pull_request", (C, B)))
        self.assertTrue(verify_identity(A, A, "d" * 40, "pull_request", (C, B)))
        self.assertEqual(verify_identity(A, A, A, "push"), [])
        self.assertTrue(verify_identity(A, A, B, "push"))
        ci = (ROOT / ".github/workflows/ci-selective.yml").read_text()
        self.assertGreaterEqual(ci.count("checkout_identity.py --event"), 3)
        emit(1, self._testMethodName)

    def test_ac_2_diff_check_uses_committed_base_and_head(self):
        ci = (ROOT / ".github/workflows/ci-selective.yml").read_text()
        self.assertIn('git diff --check "$BASE_SHA" "$HEAD_SHA"', ci)
        self.assertNotIn("run: git diff --check\\n", ci)
        self.assertIn("github.event.pull_request.base.sha", ci)
        self.assertIn("github.event.pull_request.head.sha", ci)
        emit(2, self._testMethodName)

    def test_ac_3_pr_edit_and_main_push_check_fail_closed(self):
        ci = (ROOT / ".github/workflows/ci-selective.yml").read_text()
        self.assertIn("types: [opened, synchronize, reopened, edited, ready_for_review]", ci)
        self.assertIn("branches: [main]", ci)
        plan = impacted([".factory/scripts/checkout_identity.py"], B)
        self.assertTrue(all(plan["selected_jobs"].values()))
        statuses = {"impact": "success", "policy": "success",
                    "issue_completion": "success",
                    "acceptance_macos": "success", "acceptance_windows": "success",
                    **{name: "success" for name in plan["selected_jobs"]}}
        self.assertEqual(gate_errors(plan, B, statuses), [])
        for status in ("failure", "cancelled", "skipped", ""):
            self.assertTrue(gate_errors(plan, B,
                dict(statuses, issue_completion=status)))
        emit(3, self._testMethodName)


if __name__ == "__main__":
    unittest.main()
