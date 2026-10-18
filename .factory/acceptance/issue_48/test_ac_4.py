"""AC-4: a complete proof must bind both deliveries to one real hosted run."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from two_issue_canary import (LiveTwoIssueCanaryMissing, STAGES, WORKFLOW,
                              ARTIFACT, verify_live_two_issue_canary)

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
