"""AC-3: owner-facing blocked state is explicit and not based on fixtures."""
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from verify_branch_protection import remediation

class OwnerBlockAcceptance(unittest.TestCase):
    def test_ac_3_missing_owner_rules_produce_actionable_block(self):
        result=remediation("shpalac/insurance",["main does not independently enforce all required CI checks"],protected=False)
        self.assertIn("BLOCKED: OWNER ACTION REQUIRED",result)
        self.assertIn("settings/rules",result)
        self.assertIn("NOT protected",result)
        self.assertNotIn("PASS",result)

    def test_ac_3_verified_rules_only_can_report_pass(self):
        result=remediation("shpalac/insurance",[],protected=True)
        self.assertIn("enforcement: PASS",result)
        self.assertNotIn("BLOCKED",result)
