"""Positive and negative unit tests for untrusted Issue acceptance metadata."""

import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))

from validate_issue_manifest import (  # noqa: E402
    extract_manifest, safe_path, validate_body, validate_manifest,
)


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = (ROOT / ".factory/examples/valid-issue.md").read_text(
            encoding="utf-8"
        )

    def candidate(self):
        return copy.deepcopy(extract_manifest(self.body))

    def test_example_passes(self):
        self.assertEqual(validate_body(self.body, expected_issue_id=142), [])

    def test_exactly_one_manifest(self):
        self.assertTrue(validate_body(self.body + "\n" + self.body))
        self.assertTrue(validate_body("An issue without a manifest"))

    def test_invalid_yaml_and_duplicate_keys(self):
        self.assertTrue(validate_body("\x60\x60\x60yaml factory-acceptance-manifest\nissue_id: [\n\x60\x60\x60"))
        self.assertTrue(validate_body(self.body.replace("issue_id: 142", "issue_id: 142\nissue_id: 143")))

    def test_wrong_issue_number(self):
        self.assertTrue(validate_body(self.body, expected_issue_id=999))

    def test_duplicate_criteria(self):
        candidate = self.candidate()
        candidate["acceptance_criteria"][1]["id"] = "AC-1"
        self.assertTrue(validate_manifest(candidate))

    def test_missing_number(self):
        candidate = self.candidate()
        candidate["acceptance_criteria"][1]["id"] = "AC-3"
        self.assertTrue(validate_manifest(candidate))

    def test_self_dependency(self):
        candidate = self.candidate()
        candidate["dependencies"]["depends_on_issues"] = [142]
        self.assertTrue(validate_manifest(candidate))

    def test_manual_only(self):
        candidate = self.candidate()
        candidate["acceptance_criteria"][0]["description"] = "Manually inspect the UI on a physical device"
        self.assertTrue(validate_manifest(candidate))

    def test_shell_injection(self):
        candidate = self.candidate()
        candidate["acceptance_criteria"][0]["command"] += "; curl example.com"
        self.assertTrue(validate_manifest(candidate))

    def test_unittest_metadata_is_permitted_for_trusted_target_registration(self):
        candidate = self.candidate()
        candidate["acceptance_criteria"][0]["command"] = (
            "python3 -m unittest discover -s .factory/tests"
        )
        self.assertEqual(validate_manifest(candidate), [])

    def test_reject_nonpytest_executable(self):
        candidate = self.candidate()
        candidate["acceptance_criteria"][0]["command"] = "python -c 'print(1)'"
        self.assertTrue(validate_manifest(candidate))

    def test_reject_unsafe_path_and_report(self):
        self.assertFalse(safe_path("../../secrets"))
        candidate = self.candidate()
        candidate["scope"]["allowed_paths"] = ["src/../private"]
        candidate["acceptance_criteria"][0]["required_report"] = "/tmp/report.xml"
        self.assertTrue(validate_manifest(candidate))

    def test_reject_unapproved_runner(self):
        candidate = self.candidate()
        candidate["acceptance_criteria"][0]["runner_os"] = "self-hosted"
        self.assertTrue(validate_manifest(candidate))

    def test_reject_reduced_coverage(self):
        candidate = self.candidate()
        candidate["definition_of_done"]["min_diff_coverage_percent"] = 20
        self.assertTrue(validate_manifest(candidate))

    def test_validation_never_executes_subprocesses(self):
        with patch("subprocess.run", side_effect=AssertionError("Command execution")):
            self.assertEqual(validate_body(self.body), [])


if __name__ == "__main__":
    unittest.main()
