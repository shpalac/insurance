"""AC-2: incomplete multi-PR work stays open with explicit progress."""
import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from integration_policy import closure_progress
SHA = "a" * 40

def evidence(ac):
    return {"id":ac,"verified_main_sha":SHA,"status":"PASS","assertions":2,
            "permanent_regression":True,"artifact_url":"https://example.invalid/run/1",
            "merge_sha":"b"*40,"pr_number":50}

class PartialProgressAcceptance(unittest.TestCase):
    def test_ac_2_partial_evidence_keeps_issue_open_and_names_missing_criteria(self):
        result = closure_progress(criteria_ids=["AC-1","AC-2","AC-3"],
                                  evidence=[evidence("AC-1")], main_sha=SHA)
        self.assertFalse(result["should_close"])
        self.assertEqual(result["missing_criteria"], ["AC-2","AC-3"])
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["total"], 3)
