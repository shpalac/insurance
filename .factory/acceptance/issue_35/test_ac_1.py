"""AC-1: actual effective GitHub branch protection must be inspected."""
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from verify_branch_protection import audit,branch_protected,REQUIRED

class EffectiveEnforcementAcceptance(unittest.TestCase):
    def test_ac_1_inaccessible_or_missing_rules_never_count_as_enforcement(self):
        self.assertTrue(audit(None,None))
        self.assertTrue(audit([],None))
        self.assertFalse(branch_protected({"protected":False}))
        self.assertFalse(branch_protected(None))

    def test_ac_1_partial_required_contexts_fail_closed(self):
        names=sorted(REQUIRED)
        rules=[{"type":"required_status_checks","parameters":{"required_status_checks":[{"context":n} for n in names[:-1]]}}]
        self.assertTrue(audit(rules,None))
        rules[0]["parameters"]["required_status_checks"].append({"context":names[-1]})
        self.assertEqual(audit(rules,None),[])
