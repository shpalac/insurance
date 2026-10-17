import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/".factory/scripts"))
from agent_identity_policy import authorize,ROLE_PERMISSIONS
class DenialAcceptance(unittest.TestCase):
    def test_ac_2_unapproved_forged_or_missing_auth_denied(self):
        base=dict(enabled=True,role="validator",permissions=set(ROLE_PERMISSIONS["validator"]),approved_logins={"github-actions[bot]"},trusted_workflow=True,owner_approved=False)
        self.assertFalse(authorize(actor="attacker",**base).allowed)
        self.assertFalse(authorize(actor="github-actions[bot]",**dict(base,role="forged")).allowed)
        self.assertFalse(authorize(actor="github-actions[bot]",**dict(base,trusted_workflow=False)).allowed)
