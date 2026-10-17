"""Issue #35: truthful GitHub main-branch enforcement audit."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from verify_branch_protection import (
    REQUIRED, audit, branch_protected, remediation, validated_rules,
)


def emit(n: int, name: str):
    path = ROOT / "reports" / f"ac-{n}.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", tests="1", errors="0", failures="0",
                       skipped="0", assertions="4")
    ET.SubElement(suite, "testcase", classname="Issue35Acceptance", name=name)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


class Issue35Acceptance(unittest.TestCase):
    def test_ac_1_ineffective_and_partial_branch_rules_fail_closed(self):
        self.assertFalse(branch_protected({"protected": False}))
        self.assertFalse(branch_protected(None))
        self.assertTrue(branch_protected({"protected": True}))
        self.assertTrue(audit(None, None))
        self.assertTrue(audit([], {"required_status_checks": {}}))
        rules = [{"type": "required_status_checks",
                  "parameters": {"required_status_checks": [
                      {"context": name} for name in sorted(REQUIRED)]}}]
        self.assertEqual(validated_rules(rules), [])
        self.assertEqual(audit(rules, None), [])
        emit(1, self._testMethodName)

    def test_ac_3_missing_owner_settings_never_claim_active_protection(self):
        message = remediation("shpalac/insurance",
                              ["missing enforced required context"],
                              protected=False)
        self.assertIn("BLOCKED: OWNER ACTION REQUIRED", message)
        self.assertIn("settings/rules", message)
        self.assertIn("Independent reviewer approval remains optional", message)
        ok = remediation("shpalac/insurance", [], protected=True)
        self.assertIn("PASS", ok)
        self.assertNotIn("BLOCKED", ok)
        workflow = (ROOT / ".github/workflows/factory-branch-protection-audit.yml").read_text()
        self.assertIn("python3 .factory/scripts/verify_branch_protection.py", workflow)
        self.assertIn("main-branch-enforcement.json", workflow)
        emit(3, self._testMethodName)


if __name__ == "__main__":
    unittest.main()
