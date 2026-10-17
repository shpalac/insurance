"""AC-3: complete main evidence yields one auditable closure plan."""
import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from integration_policy import closure_progress
SHA = "a" * 40

def evidence(ac, pr):
    return {"id":ac,"verified_main_sha":SHA,"status":"PASS","assertions":3,
            "permanent_regression":True,"artifact_url":f"https://example.invalid/run/{pr}",
            "merge_sha":f"{pr:040x}","pr_number":pr}

class CompleteClosureAcceptance(unittest.TestCase):
    def test_ac_3_all_criteria_produce_sha_bound_audit_evidence(self):
        result = closure_progress(criteria_ids=["AC-1","AC-2"],
                                  evidence=[evidence("AC-1",49),evidence("AC-2",53)],
                                  main_sha=SHA)
        self.assertTrue(result["should_close"])
        self.assertEqual(result["main_sha"], SHA)
        self.assertEqual(result["verified_criteria"], ["AC-1","AC-2"])
        self.assertEqual([row["pr_number"] for row in result["evidence"]], [49,53])
        self.assertTrue(all(row["artifact_url"] and row["merge_sha"] for row in result["evidence"]))

    def test_ac_3_closure_plan_is_idempotent_after_issue_is_closed(self):
        result = closure_progress(criteria_ids=["AC-1"],
                                  evidence=[evidence("AC-1",49)],
                                  main_sha=SHA, issue_closed=True)
        self.assertFalse(result["should_close"])
        self.assertTrue(result["already_closed"])
