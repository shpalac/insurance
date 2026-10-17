import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from lease_state import Lease
from repair_recovery import record_failure,normalized_diff_hash,MAX_REPAIRS,MAX_CONFLICT_REBASES

class Acceptance(unittest.TestCase):
    def test_ac_2_three_failures_repeat_diff_or_two_conflicts_block(self):
        now=datetime(2026,10,18,tzinfo=timezone.utc)
        diff=normalized_diff_hash(" a = 1 \n\n b = 2 \n")
        self.assertEqual(diff,normalized_diff_hash("a = 1\nb = 2"))
        lease=Lease(entity=9,epoch=1,revision=2,owner="bot",role="ci-engineer",
                    phase="repairing",expires_at=now+timedelta(minutes=30),
                    heartbeat_at=now,diff_hashes=(diff,))
        self.assertEqual(record_failure(lease,normalized_hash=diff,attempts=1,
                                        conflict_rebases=0),
                         ("blocked","repeated_normalized_diff"))
        distinct=normalized_diff_hash("distinct patch")
        self.assertEqual(record_failure(lease,normalized_hash=distinct,attempts=MAX_REPAIRS,
                                        conflict_rebases=0),
                         ("blocked","three_unsuccessful_repairs"))
        self.assertEqual(record_failure(lease,normalized_hash=distinct,attempts=1,
                                        conflict_rebases=MAX_CONFLICT_REBASES),
                         ("blocked","conflict_rebase_budget_exhausted"))
        self.assertEqual(record_failure(lease,normalized_hash=distinct,attempts=1,
                                        conflict_rebases=1),
                         ("repairing","bounded_retry_remaining"))
        source=(ROOT/".factory/scripts/repair_recovery.py").read_text()
        self.assertIn("MAX_REPAIRS = 3",source)
        self.assertIn("MAX_CONFLICT_REBASES = 2",source)
