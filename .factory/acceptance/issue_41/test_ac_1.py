import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from post_merge_closure import reconciliation_window, ReconcileError, MAX_ISSUES, MAX_ISSUES_FETCH, MAX_PRS

class ScalableReconciliation(unittest.TestCase):
    def test_ac_1_large_backlog_is_sharded_without_dropping_issues(self):
        issues = [{"number": i, "state": "open"} for i in range(1, 1202)]
        covered = set()
        total = (len(issues) + MAX_ISSUES - 1) // MAX_ISSUES
        for cursor in range(total):
            chunk = reconciliation_window(issues, cursor)
            self.assertLessEqual(len(chunk), MAX_ISSUES)
            covered.update(x["number"] for x in chunk)
        self.assertEqual(covered, set(range(1, 1202)))
        self.assertGreaterEqual(MAX_ISSUES_FETCH, 1201)
        self.assertGreater(MAX_PRS, 1000)
        self.assertEqual(reconciliation_window(issues, total), issues[:MAX_ISSUES])
        with self.assertRaises(ReconcileError):
            reconciliation_window(issues, 1, batch_size=1000)
