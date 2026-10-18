"""AC-2: exact-head authorization and all five required checks."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from pr_merge_coordinator import REQUIRED, approved, check_gate

class Issue47AC2(unittest.TestCase):
    def test_ac_2_authorized_owner_cannot_bypass_required_checks(self):
        sha="a"*40
        comments=[{"user":{"login":"shpalac"},"body":"FACTORY-OWNER-AUTH sha="+sha+" reason=Approved protected path change"}]
        checks=[{"name":name,"head_sha":sha,"status":"completed","conclusion":"success"} for name in REQUIRED]
        self.assertTrue(approved(comments,"shpalac",sha))
        self.assertTrue(check_gate(checks,sha))
        self.assertFalse(check_gate(checks[:-1],sha))
        self.assertFalse(approved(comments,"shpalac","b"*40))
