"""AC-2: preserve authoritative evidence that GitHub rejected a failing-check merge.

PR #63 is a deliberately failing negative canary and MUST remain unmerged.
This test validates the checked-in evidence contract, not a simulated API call.
The linked live PR and its GitHub checks are the authoritative external record.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / ".factory" / "evidence" / "issue_35_negative_merge.json"


class NegativeMergeEvidenceAcceptance(unittest.TestCase):
    def test_ac_2_records_live_rejection_without_claiming_canary_was_merged(self):
        record = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(record["repository"], "shpalac/insurance")
        self.assertEqual(record["issue"], 35)
        self.assertEqual(record["pull_request"], 63)
        self.assertEqual(record["attempted_merge_http_status"], 405)
        self.assertEqual(record["merge_result"], "rejected")
        self.assertFalse(record["merged"])
        self.assertEqual(record["required_check_failure"], "factory-bootstrap-gate")
        self.assertTrue(record["evidence_url"].startswith("https://github.com/shpalac/insurance/pull/63"))
        self.assertEqual(len(record["head_sha"]), 40)
        self.assertTrue(all(ch in "0123456789abcdef" for ch in record["head_sha"]))


if __name__ == "__main__":
    unittest.main()
