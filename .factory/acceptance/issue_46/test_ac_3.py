import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from lease_state import InMemoryLeaseStore,acquire,checkpoint
from lease_fencing import WorkerProof
from pr_merge_coordinator import REQUIRED
from repair_recovery import approve_candidate,identify_failure
from repair_canary_proof import verify_live_repair_proof,LiveRepairProofMissing

SHA="a"*40
MAIN="b"*40
class Acceptance(unittest.TestCase):
    def test_ac_3_only_current_green_security_verified_owner_authorized_head_merges(self):
        now=datetime(2026,10,18,tzinfo=timezone.utc)
        store=InMemoryLeaseStore()
        x=acquire(store,entity=8,owner="integrator",role="integrator",
                  now=now,ttl=timedelta(minutes=30))
        x=checkpoint(store,entity=8,epoch=x.epoch,owner=x.owner,now=now,
                     branch="factory/issue-8",sha=SHA,diff="current merge candidate")
        proof=WorkerProof(8,x.epoch,x.revision,x.owner,x.role,x.branch,x.commit_sha)
        pr={"number":88,"state":"open","draft":False,
            "head":{"sha":SHA},"base":{"sha":MAIN,"ref":"main"},
            "mergeable":True,"mergeable_state":"clean"}
        checks=[{"name":name,"status":"completed",
                 "conclusion":"success","head_sha":SHA} for name in REQUIRED]
        comments=[{"user":{"login":"shpalac"},
                   "body":"FACTORY-OWNER-AUTH sha="+SHA+
                          " reason=Reviewed current protected factory patch"}]
        kw={"pr":pr,"checks":checks,"comments":comments,
            "changed_paths":[".factory/scripts/example.py"],"owner":"shpalac",
            "main_sha":MAIN,"store":store,"proof":proof,
            "authenticated_login":"integrator","approved_logins":{"integrator"},
            "now":now}
        class NoRealRepair:
            def get(self,path):
                return {"total_count": 0, "workflow_runs": []}
        with self.assertRaises(LiveRepairProofMissing):
            verify_live_repair_proof(NoRealRepair(), MAIN)
        closure = (ROOT / ".factory/scripts/post_merge_closure.py").read_text()
        self.assertNotIn("verify_live_repair_proof(api, sha)", closure)
        self.assertNotIn("for dependency in (43, 44, 45)", closure)
        dispatcher = (ROOT / ".factory/scripts/repair_dispatch.py").read_text()
        self.assertIn("verify_live_repair_proof(api, main_sha)", dispatcher)
        self.assertLess(
            dispatcher.index("verify_live_repair_proof(api, main_sha)"),
            dispatcher.index('api.call("POST","/dispatches"'),
        )
        self.assertTrue(approve_candidate(**kw))
        self.assertFalse(approve_candidate(**dict(kw,comments=[])))
        self.assertFalse(approve_candidate(**dict(kw,checks=checks[:-1])))
        self.assertFalse(approve_candidate(**dict(kw,
            pr=dict(pr,mergeable_state="dirty"))))
        self.assertFalse(approve_candidate(**dict(kw,now=now+timedelta(hours=1))))
        failed=[{"name":"policy","conclusion":"failure","status":"completed"}]
        run={"id":901,"head_sha":SHA,"event":"pull_request",
             "name":"Factory selective CI","status":"completed","conclusion":"failure"}
        self.assertEqual(identify_failure(run=run,jobs=failed,pr=pr).reason,
                         "security_or_policy_failure_requires_intervention")
