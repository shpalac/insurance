"""Issue 93 AC-3: run the co-shipped regression suite."""
import unittest
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[3]
namespace = runpy.run_path(str(ROOT / ".factory/acceptance/issue_93/test_ac_1.py"))
Base = namespace["Issue93Acceptance"]

class Issue93AC3(unittest.TestCase):
    def test_ac_3(self):
        instance = Base("test_ac_3_changed_main_fails_before_check_lookup")
        instance.setUp()
        try:
            getattr(instance, instance._testMethodName)()
        finally:
            instance.tearDown()
