"""AC-4: worker roles cannot bypass policy or protected-path authorization."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from lease_state import InMemoryLeaseStore, acquire
from agent_dispatch_contract import build_envelope, DispatchDenied
from trusted_admission import admission_blockers
NOW=datetime(2026,10,17,tzinfo=timezone.utc)
SHA="a"*40

class AuthorizationAcceptance(unittest.TestCase):
    def test_ac_4_unapproved_identity_cannot_build_dispatch_envelope(self):
        store=InMemoryLeaseStore()
        lease=acquire(store,entity=7,owner="approved",role="developer",now=NOW,ttl=timedelta(minutes=5))
        with self.assertRaises(DispatchDenied):
            build_envelope(lease=lease,authenticated_login="attacker",expected_role="developer",approved_logins={"approved"},now=NOW)

    def test_ac_4_worker_cannot_self_authorize_protected_workflow_change(self):
        pr={"head":{"sha":SHA},"state":"open","draft":False,"base":{"ref":"main"},"mergeable":True}
        run={"head_sha":SHA,"event":"pull_request","conclusion":"success"}
        jobs=[{"name":n,"status":"completed","conclusion":"success"} for n in ("issue-completion","factory-gate-preflight")]
        errors=admission_blockers(pr,run,jobs,[".github/workflows/ci.yml"],[],"shpalac")
        self.assertIn("Protected paths need owner-authored, exact-head approval",errors)
