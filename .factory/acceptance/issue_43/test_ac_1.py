import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/".factory/scripts"))
from agent_identity_policy import authorize,ROLE_PERMISSIONS
class IdentityAcceptance(unittest.TestCase):
    def test_ac_1_approved_trusted_validator_requires_explicit_activation(self):
        kw=dict(actor="github-actions[bot]",role="validator",permissions=set(ROLE_PERMISSIONS["validator"]),approved_logins={"github-actions[bot]"},trusted_workflow=True,owner_approved=True)
        self.assertFalse(authorize(enabled=False,**kw).allowed)
        self.assertTrue(authorize(enabled=True,**kw).allowed)
