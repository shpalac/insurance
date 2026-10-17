import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from live_closure_canary import prove_closure
SHA="a"*40
def audit():
    return {"user":{"type":"Bot"},"body":'<!-- FACTORY_CLOSURE_AUDIT_V1 issue=8 main='+SHA+' -->\n{"id": "AC-1", "should_close": true}'}
def proof(**overrides):
    options=dict(issue={"number":8,"state":"closed"},comments=[audit()],current_main_sha=SHA,
                 linked_pr={"merged_at":"2026-10-17T12:00:00Z","merge_commit_sha":SHA,"body":"Refs #8\n"},
                 required_criteria=("AC-1",))
    options.update(overrides)
    return prove_closure(**options)
class CanaryTests(unittest.TestCase):
    def test_single_verified_audit(self):
        self.assertEqual(proof(),[])
    def test_open_issue_rejected(self):
        self.assertTrue(proof(issue={"number":8,"state":"open"}))
    def test_duplicate_audit_rejected(self):
        self.assertTrue(proof(comments=[audit(),audit()]))
    def test_missing_acceptance_rejected(self):
        self.assertTrue(proof(required_criteria=("AC-1","AC-2")))
    def test_unmerged_pr_rejected(self):
        self.assertTrue(proof(linked_pr={"body":"Refs #8\n"}))
    def test_non_bot_audit_rejected(self):
        c=audit(); c["user"]["type"]="User"
        self.assertTrue(proof(comments=[c]))
    def test_wrong_issue_rejected(self):
        self.assertTrue(proof(issue={"number":9,"state":"closed"}))
if __name__ == "__main__":
    unittest.main()
