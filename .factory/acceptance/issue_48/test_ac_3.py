"""AC-3: invalid, synthetic, incomplete or expired evidence never authorizes closure."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
sys.path.insert(0,str(ROOT/".factory/tests"))
from two_issue_canary import (LiveTwoIssueCanaryMissing, STAGES, WORKFLOW,
                              verify_live_two_issue_canary, ARTIFACT)
from issue_48_live_evidence import load_evidence, UnverifiedLiveDelivery, verify_phase
from issue_48_live_evidence_fixtures import EvidenceAPI, REPO, make_evidence

SHA="c"*40
RUN={"id":313,"name":WORKFLOW,"head_sha":SHA,"head_branch":"main",
     "event":"workflow_dispatch","status":"completed","conclusion":"success"}

class Fake:
    def __init__(self, digest=None, expired=False):
        self.digest=digest
        self.expired=expired
    def get(self,path):
        if path=="/git/ref/heads/main": return {"object":{"sha":SHA}}
        if path=="/issues/47": return {"state":"closed"}
        if path.startswith("/actions/runs?"):
            return {"total_count":1,"workflow_runs":[RUN]}
        if path.endswith("/jobs?per_page=100"):
            return {"total_count":len(STAGES),"jobs":[
                {"name":n,"status":"completed","conclusion":"success"}
                for n in STAGES]}
        if path.endswith("/artifacts?per_page=100"):
            return {"total_count":1,"artifacts":[{
                "id":99,"name":ARTIFACT,"expired":self.expired,
                "digest":self.digest}]}
        raise AssertionError(path)

class Acceptance(unittest.TestCase):
    def test_ac_3_rejects_missing_digest_expired_or_off_sha_evidence(self):
        for digest,expired in [(None,False),("sha256:invalid",False),
                               ("sha256:"+"0"*64,True)]:
            with self.subTest(digest=digest,expired=expired):
                with self.assertRaises(LiveTwoIssueCanaryMissing):
                    verify_live_two_issue_canary(Fake(digest,expired),SHA)
        with self.assertRaises(LiveTwoIssueCanaryMissing):
            verify_live_two_issue_canary(Fake("sha256:"+"0"*64),"d"*40)
        self.assertIn("negative-admission",STAGES)
        self.assertIn("verify-independent-evidence",STAGES)

    def test_ac_3_live_evidence_rejects_wrong_repository_mode_and_duplicate_delivery(self):
        evidence = make_evidence()
        for mutate in (
            lambda value: value.update(repository="other/repository"),
            lambda value: value.update(mode="simulated"),
            lambda value: value["deliveries"].__setitem__(1, dict(value["deliveries"][0])),
        ):
            candidate = make_evidence()
            mutate(candidate)
            with self.subTest(candidate=candidate):
                with self.assertRaises(UnverifiedLiveDelivery):
                    verify_phase(EvidenceAPI(candidate), candidate, repo=REPO, phase="all")

        candidate = make_evidence()
        row = candidate["deliveries"][0]
        with self.assertRaises(UnverifiedLiveDelivery):
            verify_phase(
                EvidenceAPI(candidate, {
                    f"/actions/runs/{row['dispatch_run']}/artifacts?per_page=100": {
                        "total_count": 1, "artifacts": [{
                            "name": "factory-agent-dispatch-proof",
                            "digest": "sha256:wrong", "expired": False,
                        }],
                    },
                }),
                candidate, repo=REPO, phase="first",
            )

    def test_ac_3_missing_malformed_and_nonobject_evidence_is_rejected(self):
        for raw in ("", "{", "[]", "null", '"string"'):
            with self.subTest(raw=raw):
                with self.assertRaises(UnverifiedLiveDelivery):
                    load_evidence(None,raw)
