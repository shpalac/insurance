"""AC-4: manual-only criteria, repeated repair failures and expired leases fail closed."""
import sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from validate_issue_manifest import MANUAL
from lease_state import InMemoryLeaseStore,acquire,checkpoint,LeaseConflict,StaleLease
NOW=datetime(2026,10,17,tzinfo=timezone.utc)

class FaultRecoveryAcceptance(unittest.TestCase):
    def test_ac_4_manual_only_acceptance_is_rejected_by_policy(self):
        self.assertIsNotNone(MANUAL.search("manually verify the production behavior"))

    def test_ac_4_repeated_lint_failure_stops_repair_loop(self):
        store=InMemoryLeaseStore()
        lease=acquire(store,entity=8,owner="worker",role="developer",now=NOW,ttl=timedelta(minutes=5))
        lease=checkpoint(store,entity=8,epoch=lease.epoch,owner="worker",now=NOW,branch="factory/canary",sha="a"*40,diff="lint failure")
        lease=checkpoint(store,entity=8,epoch=lease.epoch,owner="worker",now=NOW+timedelta(seconds=1),branch="factory/canary",sha="b"*40,diff="lint failure")
        self.assertEqual(lease.phase,"blocked")
        with self.assertRaises(LeaseConflict):
            acquire(store,entity=8,owner="replacement",role="developer",now=NOW+timedelta(seconds=2),ttl=timedelta(minutes=5))

    def test_ac_4_expired_lease_can_be_recovered_without_old_worker_writes(self):
        store=InMemoryLeaseStore()
        old=acquire(store,entity=8,owner="old",role="developer",now=NOW,ttl=timedelta(minutes=1))
        new=acquire(store,entity=8,owner="new",role="developer",now=NOW+timedelta(minutes=2),ttl=timedelta(minutes=5))
        self.assertGreater(new.epoch,old.epoch)
        with self.assertRaises(StaleLease):
            checkpoint(store,entity=8,epoch=old.epoch,owner="old",now=NOW+timedelta(minutes=2),branch="factory/old",sha="c"*40,diff="stale")
