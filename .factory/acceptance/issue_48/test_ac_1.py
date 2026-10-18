"""AC-1: a real autonomous delivery must be separately attested on main."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
sys.path.insert(0,str(ROOT/".factory/tests"))
from two_issue_canary import LiveTwoIssueCanaryMissing, verify_live_two_issue_canary
from issue_48_live_evidence import load_evidence, verify_delivery, UnverifiedLiveDelivery
from live_evidence_fixtures import EvidenceAPI, MAIN_SHA, REPO, make_evidence

SHA="a"*40

class MissingPrerequisites:
    def __init__(self, issue47="open", runs=None):
        self.issue47=issue47
        self.runs=runs if runs is not None else []
    def get(self, path):
        if path=="/git/ref/heads/main":
            return {"object":{"sha":SHA}}
        if path=="/issues/47":
            return {"state":self.issue47}
        if path.startswith("/actions/runs?"):
            return {"total_count":len(self.runs),"workflow_runs":self.runs}
        raise AssertionError("unexpected source: "+path)

class Acceptance(unittest.TestCase):
    def test_ac_1_does_not_substitute_unit_tests_for_live_agent_delivery(self):
        with self.assertRaises(LiveTwoIssueCanaryMissing):
            verify_live_two_issue_canary(MissingPrerequisites(),SHA)
        with self.assertRaises(LiveTwoIssueCanaryMissing):
            verify_live_two_issue_canary(MissingPrerequisites(issue47="closed"),SHA)
        closure=(ROOT/".factory/scripts/post_merge_closure.py").read_text()
        self.assertIn('if number == 48:',closure)
        self.assertIn('item["two_issue_canary"] = verify_live_two_issue_canary(api, sha)',closure)
        self.assertIn('item.get("two_issue_canary") != verify_live_two_issue_canary(api, sha)',closure)
        self.assertTrue(SHA and len(SHA)==40)

    def test_ac_1_full_delivery_requires_real_issue_merge_checks_dispatch_and_audit(self):
        evidence = make_evidence()
        row = evidence["deliveries"][0]
        api = EvidenceAPI(evidence)
        result = verify_delivery(api, row, MAIN_SHA, repository=REPO)
        self.assertEqual(result["issue"], row["issue"])
        self.assertEqual(result["pr"], row["pr"])
        self.assertEqual(result["merge_sha"], row["merge_sha"])

        with self.assertRaises(UnverifiedLiveDelivery):
            verify_delivery(
                EvidenceAPI(evidence, {f"/issues/{row['issue']}": {
                    "number": row["issue"], "state": "open",
                }}),
                row, MAIN_SHA, repository=REPO,
            )
        check_path = f"/commits/{row['head_sha']}/check-runs?per_page=100"
        with self.assertRaises(UnverifiedLiveDelivery):
            verify_delivery(
                EvidenceAPI(evidence, {check_path: {"total_count": 0, "check_runs": []}}),
                row, MAIN_SHA, repository=REPO,
            )
        with self.assertRaises(UnverifiedLiveDelivery):
            verify_delivery(
                EvidenceAPI(evidence, {f"/actions/runs/{row['dispatch_run']}/artifacts?per_page=100": {
                    "total_count": 0, "artifacts": [],
                }}),
                row, MAIN_SHA, repository=REPO,
            )
        self.assertTrue(result["closed_at"])

    def test_ac_1_live_evidence_can_be_supplied_without_a_checked_in_file(self):
        workflow=(ROOT/".github/workflows/factory-two-issue-canary.yml").read_text()
        self.assertIn("evidence_json:",workflow)
        self.assertIn("required: true",workflow)
        self.assertEqual(workflow.count("FACTORY_LIVE_EVIDENCE_JSON"),5)
        supplied='{"schema_version":1,"repository":"shpalac/insurance","mode":"live"}'
        self.assertEqual(load_evidence(None,supplied),{
            "schema_version":1,"repository":"shpalac/insurance","mode":"live"})
