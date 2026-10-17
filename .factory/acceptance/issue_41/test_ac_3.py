import hashlib
import tempfile
import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from post_merge_closure import durable_report_fields, ReconcileError

class DurableReportAcceptance(unittest.TestCase):
    def test_ac_3_report_digest_survives_expiring_hosted_link(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "reports" / "ac-3.xml"
            report.parent.mkdir(parents=True)
            raw = b'<testsuite tests="1" assertions="2"><testcase name="real"/></testsuite>'
            report.write_bytes(raw)
            row = {"artifact": "reports/ac-3.xml", "assertions": 2,
                   "testcases": 1, "runner": "ubuntu-latest"}
            proof = durable_report_fields(row, root=root)
            self.assertEqual(proof["report_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(proof["testcases"], 1)
            with self.assertRaises(ReconcileError):
                durable_report_fields(dict(row, artifact="reports/missing.xml"), root=root)
            with self.assertRaises(ReconcileError):
                durable_report_fields(dict(row, assertions=0), root=root)
        source = (ROOT / ".factory/scripts/post_merge_closure.py").read_text()
        self.assertIn('"hosted_artifacts_days": 30', source)
        self.assertIn('"durable_reports"', source)
