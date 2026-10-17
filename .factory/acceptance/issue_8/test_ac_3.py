"""AC-3: closure audit requires exactly one bot audit and permanent evidence."""
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from live_closure_canary import prove_closure
SHA="a"*40

def audit():
    return {"user":{"type":"Bot"},"body":'<!-- FACTORY_CLOSURE_AUDIT_V1 issue=8 main='+SHA+' -->\n{"id": "AC-3", "should_close": true}'}

def proof(**overrides):
    data={"issue":{"number":8,"state":"closed"},"comments":[audit()],"current_main_sha":SHA,
          "linked_pr":{"merged_at":"2026-10-17T12:00:00Z","merge_commit_sha":SHA,"body":"Refs #8\n"},
          "required_criteria":("AC-3",)}
    data.update(overrides)
    return prove_closure(**data)

class ClosureCanaryAcceptance(unittest.TestCase):
    def test_ac_3_exactly_one_audit_and_merged_pr_proves_closure(self):
        self.assertEqual(proof(),[])

    def test_ac_3_duplicate_audits_are_rejected(self):
        self.assertTrue(proof(comments=[audit(),audit()]))

    def test_ac_3_missing_criterion_prevents_closure_proof(self):
        self.assertTrue(proof(required_criteria=("AC-3","AC-4")))

    def test_ac_3_audit_must_be_ancestor_of_current_main(self):
        self.assertTrue(proof(is_ancestor=lambda ancestor,descendant: False))
