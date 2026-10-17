import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from compute_impact import impacted

class DocsAndMandatoryPolicyAcceptance(unittest.TestCase):
    def test_ac_3_docs_avoid_compilers_not_secret_or_policy_checks(self):
        plan = impacted(["docs/factory/report.md"], "a" * 40)
        self.assertTrue(plan["selected_jobs"]["docs"])
        self.assertFalse(plan["selected_jobs"]["scanner"])
        self.assertFalse(plan["selected_jobs"]["macos"])
        self.assertFalse(plan["selected_jobs"]["windows"])
        ci = (ROOT / ".github/workflows/ci-selective.yml").read_text()
        self.assertIn("Run mandatory secret and pinned-workflow checks", ci)
        self.assertIn("scan_security.py --base", ci)
        self.assertIn("needs: [impact, policy, issue-completion", ci)
        self.assertIn("diff_coverage.py --base", ci)
        self.assertIn("scanner_safety_gate.py", ci)
