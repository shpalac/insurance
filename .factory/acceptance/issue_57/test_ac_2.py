"""AC-2: real assertions and fail-closed executable JUnit proof."""
import os
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from acceptance_discovery import named_path, DiscoveryError
from run_named_acceptance import execute, TOKEN_ENV
from run_acceptance_manifest import verify_report, AcceptanceError


class ExecutionAcceptance(unittest.TestCase):
    def fixture(self, root, statement, *, decorator=""):
        path = named_path(root, 984, "AC-1")
        path.parent.mkdir(parents=True)
        path.write_text(
            "import unittest\n"
            "class Example(unittest.TestCase):\n"
            + (f"    {decorator}\n" if decorator else "")
            + "    def test_ac_1_sample(self):\n"
            + "        " + statement + "\n",
            encoding="utf-8",
        )
        return root / "reports" / "sample.xml"

    def run_case(self, root, report):
        with mock.patch.dict(os.environ, {key: "" for key in TOKEN_ENV}):
            return execute(root=root, issue=984, criterion="AC-1", report=report)

    def test_ac_2_passing_case_has_measured_assertions_and_junit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = self.fixture(root, "self.assertEqual(3 * 7, 21)")
            result = self.run_case(root, report)
            self.assertTrue(result["passed"])
            self.assertGreaterEqual(result["assertions"], 1)
            self.assertEqual(verify_report(report)["testcases"], 1)

    def test_ac_2_runtime_no_assertions_rejected_even_if_ast_mentions_one(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = self.fixture(root, "if False: self.assertTrue(True)")
            result = self.run_case(root, report)
            self.assertFalse(result["passed"])
            with self.assertRaises(AcceptanceError):
                verify_report(report)

    def test_ac_2_failed_and_skipped_cases_rejected(self):
        for statement, decorator in [
            ("self.assertEqual(1, 2)", ""),
            ("self.assertTrue(True)", "@unittest.skip('test skipped')"),
        ]:
            with self.subTest(statement=statement, decorator=decorator):
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    report = self.fixture(root, statement, decorator=decorator)
                    result = self.run_case(root, report)
                    self.assertFalse(result["passed"])
                    with self.assertRaises(AcceptanceError):
                        verify_report(report)

    def test_ac_2_executor_refuses_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = self.fixture(root, "self.assertTrue(True)")
            with mock.patch.dict(os.environ, {"GH_TOKEN": "do-not-use"}):
                with self.assertRaises(DiscoveryError):
                    execute(root=root, issue=984, criterion="AC-1", report=report)
            self.assertFalse(report.exists())

    def test_ac_2_report_symlink_cannot_write_outside_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "checkout"
            root.mkdir()
            report = self.fixture(root, "self.assertTrue(True)")
            outside = Path(folder) / "outside"
            outside.mkdir()
            (root / "reports").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(DiscoveryError):
                self.run_case(root, report)


if __name__ == "__main__":
    unittest.main()
