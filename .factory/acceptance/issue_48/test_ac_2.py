"""AC-2: incomplete fault injection or stopped repair fails live signoff."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from two_issue_canary import LiveTwoIssueCanaryMissing, STAGES, WORKFLOW, verify_live_two_issue_canary

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
