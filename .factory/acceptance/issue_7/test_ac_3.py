"""AC-3: deterministic repairs are bounded and repeated diffs stop."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from lease_state import InMemoryLeaseStore, acquire, checkpoint
NOW=datetime(2026,10,17,tzinfo=timezone.utc)

class BoundedRepairAcceptance(unittest.TestCase):
    def test_ac_3_third_repair_attempt_blocks_worker(self):
        store=InMemoryLeaseStore()
        lease=acquire(store,entity=7,owner="worker",role="developer",now=NOW,ttl=timedelta(minutes=20))
        for index in range(3):
            lease=checkpoint(store,entity=7,epoch=lease.epoch,owner="worker",now=NOW+timedelta(seconds=index),branch="factory/issue7",sha=f"{index+1:040x}",diff=f"unique diff {index}",max_repairs=3)
        self.assertEqual(lease.attempts,3)
        self.assertEqual(lease.phase,"blocked")

    def test_ac_3_repeated_normalized_diff_blocks_before_attempt_limit(self):
        store=InMemoryLeaseStore()
        lease=acquire(store,entity=7,owner="worker",role="developer",now=NOW,ttl=timedelta(minutes=20))
        lease=checkpoint(store,entity=7,epoch=lease.epoch,owner="worker",now=NOW,branch="factory/issue7",sha="a"*40,diff="same diff")
        lease=checkpoint(store,entity=7,epoch=lease.epoch,owner="worker",now=NOW+timedelta(seconds=1),branch="factory/issue7",sha="b"*40,diff=" same diff ")
        self.assertEqual(lease.phase,"blocked")
        self.assertEqual(lease.attempts,2)
