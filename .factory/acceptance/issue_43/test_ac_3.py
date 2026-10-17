import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/".factory/scripts"))
from agent_identity_policy import authorize,ROLE_PERMISSIONS
class SeparationAcceptance(unittest.TestCase):
    def test_ac_3_developer_cannot_self_authorize_protected_paths(self):
        kw=dict(enabled=True,actor="factory-bot",approved_logins={"factory-bot"},trusted_workflow=True,owner_approved=True,protected_paths=True)
        self.assertFalse(authorize(role="developer",permissions=set(ROLE_PERMISSIONS["developer"]),**kw).allowed)
        self.assertTrue(authorize(role="integrator",permissions=set(ROLE_PERMISSIONS["integrator"]),**kw).allowed)
        self.assertFalse(authorize(role="integrator",permissions=set(ROLE_PERMISSIONS["integrator"]),**dict(kw,owner_approved=False)).allowed)
