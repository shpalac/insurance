"""AC-2: interrupted work resumes from the durable checkpoint."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from lease_state import InMemoryLeaseStore, acquire, checkpoint
NOW=datetime(2026,10,17,tzinfo=timezone.utc)

class ResumeAcceptance(unittest.TestCase):
    def test_ac_2_expired_worker_resumes_saved_branch_and_commit_without_duplicate_attempt(self):
        store=InMemoryLeaseStore()
        first=acquire(store,entity=7,owner="worker-a",role="developer",now=NOW,ttl=timedelta(minutes=1))
        saved=checkpoint(store,entity=7,epoch=first.epoch,owner="worker-a",now=NOW,branch="factory/issue7",sha="a"*40,diff="initial patch")
        resumed=acquire(store,entity=7,owner="worker-b",role="developer",now=NOW+timedelta(minutes=2),ttl=timedelta(minutes=5))
        self.assertEqual(resumed.branch,saved.branch)
        self.assertEqual(resumed.commit_sha,saved.commit_sha)
        self.assertEqual(resumed.epoch,first.epoch+1)
        self.assertEqual(resumed.attempts,saved.attempts)
