import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from merge_admission import assess, CHECKS

SHA = "a" * 40
def candidate(**overrides):
    pr = dict(head={"sha": SHA}, base={"ref": "main"}, mergeable=True,
              draft=False, merged=False, state="open", labels=[],
              body="Refs #6\n", changed_paths=[".factory/scripts/merge_admission.py"])
    pr.update(overrides)
    return pr
def checks():
    return [dict(name=name, head_sha=SHA, status="completed",
                 conclusion="success", app={"slug":"github-actions"}) for name in CHECKS]
def decide(pr=None, results=None, **kwargs):
    opts = dict(pr=pr if pr is not None else candidate(),
                checks=results if results is not None else checks(),
                actual_head=SHA, allowed_paths=[".factory/**"],
                owner_authorized=True, protection_confirmed=True, expected_issue=6)
    opts.update(kwargs)
    return assess(**opts)
class AdmissionTests(unittest.TestCase):
    def test_current_verified_head_admitted(self):
        self.assertTrue(decide().eligible)
    def test_stale_head_rejected(self):
        self.assertFalse(decide(actual_head="b"*40).eligible)
    def test_missing_required_check_rejected(self):
        self.assertFalse(decide(results=checks()[:-1]).eligible)
    def test_wrong_sha_check_rejected(self):
        c=checks(); c[0]["head_sha"]="b"*40
        self.assertFalse(decide(results=c).eligible)
    def test_branch_rules_must_be_verified(self):
        self.assertFalse(decide(protection_confirmed=False).eligible)
    def test_protected_write_needs_owner(self):
        self.assertFalse(decide(owner_authorized=False).eligible)
    def test_security_hold_rejected(self):
        self.assertFalse(decide(candidate(security_hold=True)).eligible)
    def test_draft_rejected(self):
        self.assertFalse(decide(candidate(draft=True)).eligible)
    def test_out_of_scope_rejected(self):
        self.assertFalse(decide(candidate(changed_paths=["secrets.txt"])).eligible)
    def test_wrong_issue_rejected(self):
        self.assertFalse(decide(expected_issue=7).eligible)
if __name__ == "__main__":
    unittest.main()
