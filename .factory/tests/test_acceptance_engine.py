"""Acceptance runner never executes Issue-authored shell; report parsing proofs."""

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from run_acceptance_manifest import (  # noqa: E402
    AcceptanceError, run_criteria, traceability_table, verify_report,
)

HEAD = "a" * 40


class AcceptanceEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = (ROOT / ".factory/examples/valid-issue.md").read_text(
            encoding="utf-8"
        )

    def test_missing_registered_target_fails_closed(self):
        with self.assertRaises(AcceptanceError):
            run_criteria(self.body, issue_id=142, head_sha=HEAD, targets={})

    def test_wrong_sha_fails_closed(self):
        with self.assertRaises(AcceptanceError):
            run_criteria(self.body, issue_id=142, head_sha="main", targets={})

    def test_wrong_issue_fails_closed(self):
        with self.assertRaises(AcceptanceError):
            run_criteria(self.body, issue_id=143, head_sha=HEAD, targets={})

    def test_invalid_subset_fails_closed(self):
        with self.assertRaises(AcceptanceError):
            run_criteria(
                self.body, issue_id=142, head_sha=HEAD, targets={},
                criteria_subset={"AC-999"},
            )

    def test_untrusted_shell_target_rejected_without_execution(self):
        with patch("subprocess.run", side_effect=AssertionError("Executed!")):
            with self.assertRaises(AcceptanceError):
                run_criteria(
                    self.body, issue_id=142, head_sha=HEAD,
                    targets={"142/AC-1": {
                        "argv": ["sh", "-c", "echo bypass"], "runner_os": "ubuntu-latest"
                    }},
                    criteria_subset={"AC-1"},
                )

    def test_runner_mismatch_blocks_execution(self):
        with patch("subprocess.run", side_effect=AssertionError("Executed!")):
            with self.assertRaises(AcceptanceError):
                run_criteria(
                    self.body, issue_id=142, head_sha=HEAD,
                    targets={"142/AC-1": {
                        "argv": ["python3", "-m", "unittest", "tests"],
                        "runner_os": "windows-latest",
                    }},
                    criteria_subset={"AC-1"},
                )

    def test_missing_junit_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(AcceptanceError):
                verify_report(Path(folder) / "missing.xml")

    def test_zero_testcase_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "empty.xml"
            path.write_text('<testsuite tests="0" assertions="0" />')
            with self.assertRaises(AcceptanceError):
                verify_report(path)

    def test_skipped_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "skip.xml"
            path.write_text(
                '<testsuite tests="1" assertions="2">'
                '<testcase name="x"><skipped /></testcase></testsuite>'
            )
            with self.assertRaises(AcceptanceError):
                verify_report(path)

    def test_failed_test_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fail.xml"
            path.write_text(
                '<testsuite tests="1" assertions="1">'
                '<testcase name="x"><failure /></testcase></testsuite>'
            )
            with self.assertRaises(AcceptanceError):
                verify_report(path)

    def test_passing_report_has_assertions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ok.xml"
            path.write_text(
                '<testsuite tests="1" assertions="2">'
                '<testcase name="x"/></testsuite>'
            )
            self.assertEqual(
                verify_report(path), {"testcases": 1, "assertions": 2}
            )

    def test_traceability_contains_report_and_sha_evidence(self):
        value = traceability_table([{
            "id": "AC-1", "target": "142/AC-1",
            "runner": "ubuntu-latest", "status": "PASS",
            "artifact": "reports/ac-1.xml", "assertions": 2,
        }])
        self.assertIn("FACTORY_ACCEPTANCE_REPORT", value)
        self.assertIn("reports/ac-1.xml", value)


if __name__ == "__main__":
    unittest.main()
