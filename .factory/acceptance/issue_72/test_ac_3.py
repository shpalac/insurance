import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
class Acceptance(unittest.TestCase):
    def test_ac_3_contributing_defines_atomic_scope_dependencies_and_tests(self):
        doc=(ROOT/"CONTRIBUTING.md").read_text()
        self.assertIn("one PR per Issue",doc)
        self.assertIn("depends_on_issues",doc)
        self.assertIn(".factory/acceptance/issue_N/test_ac_K.py",doc)
        self.assertIn("Refs #N",doc)
        self.assertIn("FACTORY-OWNER-AUTH sha=",doc)
        workflow=(ROOT/".github/workflows/factory-issue-preflight.yml").read_text()
        self.assertIn("ref: main",workflow)
        self.assertIn("issues: write",workflow)
        self.assertIn("cancel-in-progress: false",workflow)
