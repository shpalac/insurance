"""AC-2: incomplete fault injection or stopped repair fails live signoff."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
sys.path.insert(0,str(ROOT/".factory/acceptance/issue_48"))
from two_issue_canary import LiveTwoIssueCanaryMissing, STAGES, WORKFLOW, verify_live_two_issue_canary
from issue_48_live_evidence import verify_fault, verify_phase, UnverifiedLiveDelivery
from live_evidence_fixtures import EvidenceAPI, MAIN_SHA, REPO, ALL_FAULTS, RECOVERY, make_evidence

SHA="b"*40
RUN={"id":310,"name":WORKFLOW,"head_sha":SHA,"head_branch":"main",
     "event":"workflow_dispatch","status":"completed","conclusion":"success"}

class Fake:
    def __init__(self, faults_green=False):
        self.faults_green=faults_green
    def get(self,path):
        if path=="/git/ref/heads/main": return {"object":{"sha":SHA}}
        if path=="/issues/47": return {"state":"closed"}
        if path.startswith("/actions/runs?"):
            return {"total_count":1,"workflow_runs":[RUN]}
        if path.endswith("/jobs?per_page=100"):
            return {"total_count":len(STAGES),"jobs":[
                {"name":n,"status":"completed","conclusion":
                 ("success" if self.faults_green or n!="fault-recovery" else "failure")}
                for n in STAGES]}
        raise AssertionError(path)

class Acceptance(unittest.TestCase):
    def test_ac_2_missing_recovery_and_conflict_faults_block_delivery(self):
        self.assertIn("fault-recovery",STAGES)
        self.assertIn("real-first-issue",STAGES)
        self.assertIn("real-second-issue",STAGES)
        with self.assertRaises(LiveTwoIssueCanaryMissing):
            verify_live_two_issue_canary(Fake(),SHA)
        with self.assertRaises(AssertionError):
            verify_live_two_issue_canary(Fake(faults_green=True),SHA)
        self.assertEqual(len(STAGES),5)

    def test_ac_2_every_hosted_fault_has_a_successful_job_and_digest(self):
        evidence = make_evidence()
        api = EvidenceAPI(evidence)
        for name in ALL_FAULTS:
            with self.subTest(fault=name):
                verify_fault(api, evidence["faults"][name], name)
        summary = verify_phase(api, evidence, repo=REPO, phase="recovery")
        self.assertEqual(summary["recovery_cases"], len(RECOVERY))
        name = RECOVERY[0]
        row = evidence["faults"][name]
        with self.assertRaises(UnverifiedLiveDelivery):
            verify_fault(
                EvidenceAPI(evidence, {
                    f"/actions/runs/{row['run_id']}/jobs?per_page=100": {
                        "total_count": 0, "jobs": [],
                    },
                }),
                row, name,
            )
        with self.assertRaises(UnverifiedLiveDelivery):
            verify_fault(
                EvidenceAPI(evidence, {
                    f"/actions/runs/{row['run_id']}/artifacts?per_page=100": {
                        "total_count": 0, "artifacts": [],
                    },
                }),
                row, name,
            )

    def test_ac_2_all_recovery_and_negative_stages_use_the_same_evidence_input(self):
        script=(ROOT/".factory/scripts/issue_48_live_evidence.py").read_text()
        workflow=(ROOT/".github/workflows/factory-two-issue-canary.yml").read_text()
        for case in ("injected_ci_failure","worker_interruption","expired_lease",
                     "simultaneous_claim","merge_conflict"):
            self.assertIn(case,script)
        for case in ("missing_required_check","unapproved_identity","protected_path",
                     "malicious_issue_prompt","stale_sha"):
            self.assertIn(case,script)
        for phase in ("first","recovery","negative","second","all"):
            self.assertIn("--phase "+phase,workflow)
        self.assertNotIn(".factory/live-evidence/issue_48.json",workflow)
        self.assertEqual(workflow.count("FACTORY_LIVE_EVIDENCE_JSON"),5)
