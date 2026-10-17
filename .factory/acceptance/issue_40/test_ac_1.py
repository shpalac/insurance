import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from diff_coverage import patch_changed_lines, calculate, CoverageError

class DiffCoverageAcceptance(unittest.TestCase):
    def test_ac_1_changed_executable_lines_under_90_fail(self):
        patch = ("diff --git a/src/insurance/core.py b/src/insurance/core.py\n"
                 "+++ b/src/insurance/core.py\n"
                 "@@ -2,0 +3,10 @@\n")
        changed = patch_changed_lines(patch)
        self.assertEqual(len(changed["src/insurance/core.py"]), 10)
        report = {"files": {"src/insurance/core.py": {
            "executed_lines": [3], "missing_lines": list(range(4, 13))}}}
        evaluated = calculate(changed, report, 90)
        self.assertFalse(evaluated["passed"])
        self.assertEqual(evaluated["changed_executable_lines"], 10)
        self.assertEqual(evaluated["percent"], 10)
        report["files"]["src/insurance/core.py"]["executed_lines"] = list(range(3, 12))
        report["files"]["src/insurance/core.py"]["missing_lines"] = [12]
        self.assertTrue(calculate(changed, report, 90)["passed"])
        with self.assertRaises(CoverageError):
            calculate(changed, {"files": {}}, 90)
