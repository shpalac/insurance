"""AC-5: stale lease epochs and unauthorized agent identities block privileged actions."""
import sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from lease_state import InMemoryLeaseStore,acquire,StaleLease
from agent_dispatch_contract import build_envelope,DispatchDenied
from trusted_admission import admission_blockers
NOW=datetime(2026,10,17,tzinfo=timezone.utc)
SHA="a"*40

class StaleAndUnauthorizedAcceptance(unittest.TestCase):
    def test_ac_5_unapproved_identity_cannot_get_dispatch_envelope(self):
        store=InMemoryLeaseStore()
        lease=acquire(store,entity=8,owner="approved",role="developer",now=NOW,ttl=timedelta(minutes=5))
        with self.assertRaises(DispatchDenied):
            build_envelope(lease=lease,authenticated_login="unapproved",expected_role="developer",approved_logins={"approved"},now=NOW)

    def test_ac_5_stale_revision_cannot_mutate_worker_state(self):
        store=InMemoryLeaseStore()
        old=acquire(store,entity=8,owner="old",role="developer",now=NOW,ttl=timedelta(minutes=1))
        acquire(store,entity=8,owner="new",role="developer",now=NOW+timedelta(minutes=2),ttl=timedelta(minutes=5))
        from lease_state import heartbeat
        with self.assertRaises(StaleLease):
            heartbeat(store,entity=8,epoch=old.epoch,owner="old",now=NOW+timedelta(minutes=2),ttl=timedelta(minutes=5))

    def test_ac_5_unauthorized_protected_change_blocks_merge(self):
        pr={"head":{"sha":SHA},"state":"open","draft":False,"base":{"ref":"main"},"mergeable":True}
        run={"head_sha":SHA,"event":"pull_request","conclusion":"success"}
        jobs=[{"name":n,"status":"completed","conclusion":"success"} for n in ("issue-completion","factory-gate-preflight")]
        errors=admission_blockers(pr,run,jobs,[".factory/config.yaml"],[],"shpalac")
        self.assertIn("Protected paths need owner-authored, exact-head approval",errors)
