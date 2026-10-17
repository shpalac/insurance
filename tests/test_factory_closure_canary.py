"""A safe, deterministic live-closure canary with real JUnit evidence."""

import sys
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from integration_policy import closure_progress  # noqa: E402


class FactoryClosureCanary(unittest.TestCase):
    def test_complete_evidence_is_sufficient_but_incomplete_is_not(self):
        main_sha = "a" * 40
        proof = {
            "id": "AC-1", "verified_main_sha": main_sha,
            "status": "PASS", "assertions": 2, "permanent_regression": True,
            "artifact_url": "https://github.com/shpalac/insurance/actions/runs/1",
            "merge_sha": "b" * 40, "pr_number": 19,
        }
        complete = closure_progress(
            criteria_ids=["AC-1"], evidence=[proof], main_sha=main_sha
        )
        incomplete = closure_progress(
            criteria_ids=["AC-1", "AC-2"], evidence=[proof], main_sha=main_sha
        )
        self.assertTrue(complete["should_close"])
        self.assertFalse(incomplete["should_close"])

        # Emit JUnit only AFTER the actual assertions pass. Acceptance executor
        # additionally verifies that this report has cases and positive assertions.
        reports = ROOT / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        suite = ET.Element("testsuite", tests="1", failures="0", errors="0",
                           skipped="0", assertions="2")
        ET.SubElement(suite, "testcase", name=self._testMethodName,
                      classname="FactoryClosureCanary")
        ET.ElementTree(suite).write(
            reports / "factory-closure-canary.xml",
            encoding="utf-8", xml_declaration=True,
        )


if __name__ == "__main__":
    unittest.main()
