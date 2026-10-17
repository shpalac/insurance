import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from github_ref_leases import GitHubRefLeaseStore,StateError,serialize,deserialize
from lease_state import InMemoryLeaseStore,heartbeat,checkpoint,LeaseConflict
from lease_fencing import acquire_bounded

class SharedStore(InMemoryLeaseStore):
    def read_all(self):
        return dict(self._states)

class Acceptance(unittest.TestCase):
    def test_ac_3_isolated_initialization_durable_heartbeat_and_bounded_capacity(self):
        store=GitHubRefLeaseStore("shpalac/insurance","fake")
        with self.assertRaises(StateError):
            store.initialize_isolated()
        store=GitHubRefLeaseStore("shpalac/insurance","fake",write_enabled=True)
        with self.assertRaises(StateError):
            store.initialize_isolated()
        backend=SharedStore()
        now=datetime(2026,10,18,tzinfo=timezone.utc)
        ttl=timedelta(minutes=30)
        one=acquire_bounded(backend,entity=900,owner="a",role="developer",
                            now=now,ttl=ttl,max_active=2)
        two=acquire_bounded(backend,entity=901,owner="b",role="developer",
                            now=now,ttl=ttl,max_active=2)
        with self.assertRaises(LeaseConflict):
            acquire_bounded(backend,entity=902,owner="c",role="developer",
                            now=now,ttl=ttl,max_active=2)
        next_lease=heartbeat(backend,entity=900,epoch=one.epoch,owner="a",
                             now=now+timedelta(minutes=1),ttl=ttl)
        self.assertGreater(next_lease.expires_at,one.expires_at)
        saved=checkpoint(backend,entity=901,epoch=two.epoch,owner="b",now=now,
                         branch="factory/issue-901",sha="a"*40,diff="safe small diff")
        self.assertEqual(deserialize(serialize(saved)),saved)
        self.assertEqual(backend.read(901),saved)
        script=(ROOT/".factory/scripts/github_ref_leases.py").read_text()
        self.assertIn('"parents": []',script)
        self.assertIn('"force": False',script)
