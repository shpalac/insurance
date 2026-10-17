"""AC-2: protected paths require independently verified owner authorization."""
import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from trusted_admission import admission_blockers

SHA = "a" * 40

def candidate():
    pr = {"head": {"sha": SHA}, "state": "open", "draft": False,
          "base": {"ref": "main"}, "mergeable": True}
    run = {"head_sha": SHA, "event": "pull_request", "conclusion": "success"}
    jobs = [{"name": n, "status": "completed", "conclusion": "success"}
            for n in ("issue-completion", "factory-gate-preflight") ]
    return pr, run, jobs

class ProtectedPathAC2Acceptance(unittest.TestCase):
    def test_ac_2_protected_path_without_owner_auth_is_denied(self):
        pr, run, jobs = candidate()
        errors = admission_blockers(pr, run, jobs, [".factory/config.yaml"], [], "shpalac")
        self.assertIn("Protected paths need owner-authored, exact-head approval", errors)

    def test_ac_2_owner_auth_for_exact_head_allows_protected_path_without_review(self):
        pr, run, jobs = candidate()
        errors = admission_blockers(
            pr, run, jobs, [".factory/config.yaml"],
            [{"user": {"login": "shpalac"}, "body": f"FACTORY-OWNER-AUTH sha={SHA} reason=authorized policy update"}],
            "shpalac")
        self.assertNotIn("Protected paths need owner-authored, exact-head approval", errors)

    def test_ac_2_auth_for_stale_sha_does_not_authorize_current_head(self):
        pr, run, jobs = candidate()
        errors = admission_blockers(
            pr, run, jobs, [".factory/config.yaml"],
            [{"user": {"login": "shpalac"}, "body": f"FACTORY-OWNER-AUTH sha={'b'*40} reason=old head"}],
            "shpalac")
        self.assertIn("Protected paths need owner-authored, exact-head approval", errors)
