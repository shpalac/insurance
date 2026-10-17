import hashlib
import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from cross_os_acceptance import runner_identity
from cross_os_proof import verify_payload, CrossOSProofError
from run_acceptance_manifest import AcceptanceError

class EvidenceRejectionAcceptance(unittest.TestCase):
    def test_ac_2_wrong_os_sha_missing_junit_or_zero_assertions_fails(self):
        with self.assertRaises(ValueError):
            runner_identity("macos-latest", "Linux")
        sha = "a" * 40
        path = "reports/cross_os/issue_39_ac_2.xml"
        raw = b'<testsuite assertions="0"><testcase name="test"/></testsuite>'
        record = {"issue": 39, "id": "AC-2", "runner": "macos-latest",
                  "head_sha": sha, "status": "PASS", "testcases": 1,
                  "assertions": 0, "report": path,
                  "report_sha256": hashlib.sha256(raw).hexdigest()}
        payload = {"version": 1, "run_id": 123, "sha": sha,
                   "runner": "macos-latest", "records": [record]}
        with self.assertRaises(CrossOSProofError):
            verify_payload(payload, "macos-latest", "b" * 40,
                           [(39, "AC-2")], {path: raw}, 123)
        with self.assertRaises(CrossOSProofError):
            verify_payload(payload, "macos-latest", sha,
                           [(39, "AC-2")], {}, 123)
        with self.assertRaises((AcceptanceError, CrossOSProofError)):
            verify_payload(payload, "macos-latest", sha,
                           [(39, "AC-2")], {path: raw}, 123)
