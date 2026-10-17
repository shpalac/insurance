import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from cross_os_proof import verified_hosted_rows, CrossOSProofError

class MainRunnerProofAcceptance(unittest.TestCase):
    def test_ac_3_missing_live_main_runner_prevents_closure(self):
        class API:
            def get(self, path):
                return {"workflow_runs": []}
        with self.assertRaises(CrossOSProofError):
            verified_hosted_rows(API(), "a" * 40,
                                 {"windows-latest": [(39, "AC-3")]})
        source = (ROOT / ".factory/scripts/post_merge_closure.py").read_text()
        self.assertIn("verified_hosted_rows(api, sha, required_os)", source)
        self.assertIn("cross_os_proof import", source)
        workflow = (ROOT / ".github/workflows/factory-verified-closure.yml").read_text()
        self.assertIn("post_merge_closure.py prepare", workflow)
