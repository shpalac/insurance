"""Permanent Issue acceptance runs from filesystem, including closed Issues."""
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from acceptance_discovery import DiscoveryError, named_path
from run_permanent_acceptance import discover, run_all


SAMPLE = """import unittest
class Sample(unittest.TestCase):
    def test_ac_1_real_contract(self):
        self.assertEqual(4 - 1, 3)
"""


class PermanentAcceptanceRegression(unittest.TestCase):
    def test_filesystem_discovery_does_not_depend_on_github_issue_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = named_path(root, 999, "AC-1")
            target.parent.mkdir(parents=True)
            target.write_text(SAMPLE)
            self.assertEqual(discover(root), [(999, "AC-1")])
            commands = []
            def successful(cmd, **kwargs):
                commands.append(cmd)
                self.assertNotIn("GH_TOKEN", kwargs["env"])
                self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
                return SimpleNamespace(returncode=0)
            result = run_all(root, run=successful)
            self.assertEqual(result, {"checked": 1, "issues": 1})
            self.assertEqual(len(commands), 1)
            self.assertIn("issue_999_ac_1.xml", commands[0][-1])

    def test_bad_suite_blocks_instead_of_silently_skipping(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = named_path(root, 999, "AC-1")
            target.parent.mkdir(parents=True)
            target.write_text(SAMPLE.replace("self.assertEqual(4 - 1, 3)", "pass"))
            with self.assertRaises(DiscoveryError):
                discover(root)

    def test_runtime_failure_stops_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = named_path(root, 999, "AC-1")
            target.parent.mkdir(parents=True)
            target.write_text(SAMPLE)
            with self.assertRaises(DiscoveryError):
                run_all(root, run=lambda *a, **k: SimpleNamespace(returncode=1))

    def test_mandatory_policy_job_calls_full_permanent_acceptance(self):
        ci = (ROOT / ".github/workflows/ci-selective.yml").read_text()
        self.assertIn("run: python3 .factory/scripts/run_permanent_acceptance.py", ci)
        self.assertIn("RESULT_POLICY", ci)
        self.assertIn("needs: [impact, policy, issue-completion", ci)


if __name__ == "__main__":
    unittest.main()
