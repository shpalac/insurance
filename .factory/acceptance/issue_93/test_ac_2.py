"""Issue 93 AC-2: run the co-shipped regression suite."""
import unittest
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[3]
namespace = runpy.run_path(str(ROOT / ".factory/acceptance/issue_93/test_ac_1.py"))
Base = namespace["Issue93Acceptance"]

class Issue93AC2(unittest.TestCase):
    def test_ac_2(self):
        instance = Base("test_ac_2_missing_failed_wrong_app_and_head_fail_closed")
        instance.setUp()
        try:
            getattr(instance, instance._testMethodName)()
        finally:
            instance.tearDown()
