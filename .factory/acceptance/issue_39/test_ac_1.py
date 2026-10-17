import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from cross_os_acceptance import RUNNERS, runner_identity

class HostedMatrixAcceptance(unittest.TestCase):
    def test_ac_1_real_hosted_os_dispatch_and_gate(self):
        for name, os_name in RUNNERS.items():
            runner_identity(name, os_name)
        workflow = (ROOT / ".github/workflows/ci-selective.yml").read_text()
        for name in ("acceptance-macos", "acceptance-windows"):
            self.assertIn("  " + name + ":", workflow)
            self.assertIn("name: " + name, workflow)
        self.assertIn("RESULT_ACCEPTANCE_MACOS", workflow)
        self.assertIn("RESULT_ACCEPTANCE_WINDOWS", workflow)
        self.assertIn("--runner macos-latest", workflow)
        self.assertIn("--runner windows-latest", workflow)
