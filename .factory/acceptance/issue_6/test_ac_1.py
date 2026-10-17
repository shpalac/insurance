"""AC-1: merge admission requires exact-head CI and protected authorization."""
import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from trusted_admission import admission_blockers

SHA = "a" * 40
def fixture():
    return (
        {"head":{"sha":SHA},"state":"open","draft":False,
         "base":{"ref":"main"},"mergeable":True},
        {"head_sha":SHA,"event":"pull_request","conclusion":"success"},
        [{"name":name,"status":"completed","conclusion":"success"}
         for name in ("issue-completion","factory-gate-preflight")],
    )

class AdmissionAcceptance(unittest.TestCase):
    def test_ac_1_current_head_and_required_checks_admit_only_valid_pr(self):
        pr, run, jobs = fixture()
        self.assertEqual(admission_blockers(pr, run, jobs, ["src/example.py"], [], "shpalac"), [])

    def test_ac_1_protected_paths_require_exact_sha_owner_comment(self):
        pr, run, jobs = fixture()
        errors = admission_blockers(pr, run, jobs, [".factory/config.yaml"], [], "shpalac")
        self.assertIn("Protected paths need owner-authored, exact-head approval", errors)
