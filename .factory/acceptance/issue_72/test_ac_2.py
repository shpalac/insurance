import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from issue_preflight import evaluate,label_delta,report,READY,BLOCKED
class Acceptance(unittest.TestCase):
    def test_ac_2_trusted_preflight_reports_schema_errors_and_role_separation(self):
        body=(ROOT/".factory/examples/valid-issue.md").read_text()
        valid=evaluate({"action":"opened","issue":{"number":142,"body":body}})
        self.assertTrue(valid["valid"],valid["errors"])
        self.assertEqual(label_delta({BLOCKED},True),({READY},{BLOCKED}))
        invalid=evaluate({"action":"edited","issue":{"number":142,"body":"missing manifest"}})
        self.assertFalse(invalid["valid"])
        self.assertTrue(invalid["errors"])
        self.assertIn(invalid["errors"][0].replace("<","&lt;"),report(invalid))
        self.assertEqual(label_delta({READY},False),({BLOCKED},{READY}))
        source=(ROOT/".factory/scripts/issue_preflight.py").read_text()
        self.assertIn("validate_body(",source)
        self.assertNotIn("subprocess",source)
