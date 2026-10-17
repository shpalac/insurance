"""AC-1: atomic concurrent claims and stale fencing."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from threading import Barrier, Thread
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from lease_state import InMemoryLeaseStore, acquire, LeaseConflict, checkpoint, StaleLease
NOW=datetime(2026,10,17,tzinfo=timezone.utc)

class LeaseRaceAcceptance(unittest.TestCase):
    def test_ac_1_two_simultaneous_claims_yield_exactly_one_active_lease(self):
        store=InMemoryLeaseStore()
        barrier=Barrier(2)
        outcomes=[]
        def claim(owner):
            barrier.wait()
            try:
                outcomes.append(("ok",acquire(store,entity=7,owner=owner,role="developer",now=NOW,ttl=timedelta(minutes=5)).owner))
            except LeaseConflict:
                outcomes.append(("conflict",owner))
        threads=[Thread(target=claim,args=(name,)) for name in ("worker-a","worker-b")]
        [thread.start() for thread in threads]
        [thread.join(timeout=2) for thread in threads]
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sum(result[0]=="ok" for result in outcomes),1)
        self.assertEqual(sum(result[0]=="conflict" for result in outcomes),1)

    def test_ac_1_old_epoch_cannot_checkpoint_after_takeover(self):
        store=InMemoryLeaseStore()
        old=acquire(store,entity=7,owner="old",role="developer",now=NOW,ttl=timedelta(minutes=1))
        new=acquire(store,entity=7,owner="new",role="developer",now=NOW+timedelta(minutes=2),ttl=timedelta(minutes=5))
        with self.assertRaises(StaleLease):
            checkpoint(store,entity=7,epoch=old.epoch,owner="old",now=NOW+timedelta(minutes=2),branch="factory/old",sha="a"*40,diff="first")
        self.assertEqual(store.read(7).epoch,new.epoch)
