"""AC-4: a complete proof must bind both deliveries to one real hosted run."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
sys.path.insert(0,str(ROOT/".factory/tests"))
from two_issue_canary import (LiveTwoIssueCanaryMissing, STAGES, WORKFLOW,
                              ARTIFACT, verify_live_two_issue_canary)
from post_merge_closure import blocked_message
from issue_48_live_evidence import verify_phase, UnverifiedLiveDelivery
from issue_48_live_evidence_fixtures import EvidenceAPI, MAIN_SHA, REPO, make_evidence

SHA="d"*40
RUN={"id":404,"name":WORKFLOW,"head_sha":SHA,"head_branch":"main",
     "event":"workflow_dispatch","status":"completed","conclusion":"success"}

class Fake:
    def __init__(self, duplicates=False):
        self.duplicates=duplicates
    def get(self,path):
        if path=="/git/ref/heads/main": return {"object":{"sha":SHA}}
        if path=="/issues/47": return {"state":"closed"}
        if path.startswith("/actions/runs?"):
            data=[RUN,RUN] if self.duplicates else [RUN]
            return {"total_count":len(data),"workflow_runs":data}
        if path.endswith("/jobs?per_page=100"):
            return {"total_count":len(STAGES),"jobs":[
                {"name":n,"status":"completed","conclusion":"success"}
                for n in STAGES]}
        if path.endswith("/artifacts?per_page=100"):
            return {"total_count":1,"artifacts":[{
                "id":405,"name":ARTIFACT,"expired":False,
                "digest":"sha256:"+"e"*64}]}
        raise AssertionError(path)

class Acceptance(unittest.TestCase):
    def test_ac_4_single_run_and_nonexpired_artifact_required(self):
        proof=verify_live_two_issue_canary(Fake(),SHA)
        self.assertEqual(proof["main_sha"],SHA)
        self.assertEqual(proof["run_id"],404)
        self.assertEqual(proof["artifact_id"],405)
        self.assertEqual(proof["artifact_digest"],"sha256:"+"e"*64)
        self.assertEqual(tuple(proof["stages"]),STAGES)
        self.assertEqual(proof["source"],WORKFLOW)
        with self.assertRaises(LiveTwoIssueCanaryMissing):
            verify_live_two_issue_canary(Fake(duplicates=True),SHA)
        self.assertLess(STAGES.index("real-first-issue"),
                        STAGES.index("real-second-issue"))

    def test_ac_4_all_live_phases_verify_two_ordered_deliveries_and_ten_faults(self):
        evidence = make_evidence()
        summary = verify_phase(
            EvidenceAPI(evidence), evidence, repo=REPO, phase="all"
        )
        self.assertEqual(summary["verified_main_sha"], MAIN_SHA)
        self.assertEqual(summary["deliveries"], 2)
        self.assertEqual(summary["recovery_cases"], 5)
        self.assertEqual(summary["negative_cases"], 5)

        reversed_order = make_evidence()
        reversed_order["deliveries"][1]["closed_at"] = "2026-10-17T11:00:00Z"
        with self.assertRaises(UnverifiedLiveDelivery):
            verify_phase(
                EvidenceAPI(reversed_order), reversed_order,
                repo=REPO, phase="all",
            )
        duplicate = make_evidence()
        duplicate["deliveries"][1]["pr"] = duplicate["deliveries"][0]["pr"]
        with self.assertRaises(UnverifiedLiveDelivery):
            verify_phase(
                EvidenceAPI(duplicate), duplicate, repo=REPO, phase="all"
            )

    def test_ac_4_successful_canary_triggers_audited_recheck_and_lists_unproven_criteria(self):
        closure=(ROOT/".github/workflows/factory-verified-closure.yml").read_text()
        self.assertIn("Factory two-issue autonomous delivery canary",closure)
        self.assertIn("github.event.workflow_run.event == 'workflow_dispatch'",closure)
        message=blocked_message({
            "reason":"acceptance_incomplete_or_untrusted_target",
            "missing_criteria":[],
            "unproven_criteria":["AC-1","AC-2","AC-3","AC-4"],
            "evidence_blocker":"live_two_issue_canary_not_verified",
        },SHA)
        for criterion in ("AC-1","AC-2","AC-3","AC-4"):
            self.assertIn(criterion,message)
        self.assertIn("live_two_issue_canary_not_verified",message)
