"""AC-4: failed CI, stale SHA, or unauthorized workflow changes fail closed."""
import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from trusted_admission import admission_blockers
SHA = "a" * 40

def fixture():
    return ({"head":{"sha":SHA},"state":"open","draft":False,
             "base":{"ref":"main"},"mergeable":True},
            {"head_sha":SHA,"event":"pull_request","conclusion":"success"},
            [{"name":name,"status":"completed","conclusion":"success"}
             for name in ("issue-completion","factory-gate-preflight")])

class FailClosedAcceptance(unittest.TestCase):
    def test_ac_4_stale_workflow_run_and_failed_check_block_admission(self):
        pr, run, jobs = fixture()
        run["head_sha"] = "c" * 40
        jobs[0]["conclusion"] = "failure"
        errors = admission_blockers(pr, run, jobs, ["src/app.py"], [], "shpalac")
        self.assertTrue(any("stale" in item for item in errors))
        self.assertTrue(any("issue-completion" in item for item in errors))

    def test_ac_4_unauthorized_workflow_change_blocks_without_exact_sha_auth(self):
        pr, run, jobs = fixture()
        errors = admission_blockers(pr, run, jobs, [".github/workflows/ci.yml"], [], "shpalac")
        self.assertIn("Protected paths need owner-authored, exact-head approval", errors)
