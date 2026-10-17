import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from repair_recovery import identify_failure,reserve_repair,RepairDenied
from lease_state import InMemoryLeaseStore,acquire,checkpoint
from lease_fencing import WorkerProof
from pr_merge_coordinator import REQUIRED

SHA="a"*40
class Acceptance(unittest.TestCase):
    def test_ac_1_exact_failing_run_is_dispatched_once_under_current_lease(self):
        run={"id":991,"head_sha":SHA,"event":"pull_request",
             "name":"Factory selective CI","status":"completed","conclusion":"failure"}
        pr={"number":9,"state":"open","draft":False,
            "base":{"ref":"main"},"head":{"sha":SHA}}
        jobs=[{"name":"scanner","status":"completed","conclusion":"failure"}]
        plan=identify_failure(run=run,jobs=jobs,pr=pr)
        self.assertEqual(plan.action,"dispatch")
        self.assertEqual((plan.run_id,plan.sha,plan.failed_jobs),(991,SHA,("scanner",)))
        self.assertEqual(identify_failure(run=run,jobs=jobs,pr=pr,
                                         last_run_id=991).action,"blocked")
        self.assertEqual(identify_failure(run=run,jobs=jobs,pr=dict(pr,head={"sha":"b"*40})).action,"blocked")
        store=InMemoryLeaseStore()
        now=datetime(2026,10,18,tzinfo=timezone.utc)
        lease=acquire(store,entity=9,owner="ci-bot",role="ci-engineer",
                      now=now,ttl=timedelta(minutes=30))
        lease=checkpoint(store,entity=9,epoch=lease.epoch,owner=lease.owner,
                         now=now,branch="factory/issue-9",sha=SHA,diff="initial failure")
        proof=WorkerProof(9,lease.epoch,lease.revision,"ci-bot","ci-engineer",
                          lease.branch,lease.commit_sha)
        updated=reserve_repair(store,proof=proof,result=plan,
                               authenticated_login="ci-bot",
                               approved_logins={"ci-bot"},now=now)
        self.assertGreater(updated.revision,proof.revision)
        with self.assertRaises(RepairDenied):
            reserve_repair(store,proof=updated,result=plan,
                           authenticated_login="ci-bot",approved_logins={"ci-bot"},now=now)
        wf=(ROOT/".github/workflows/factory-repair-dispatch.yml").read_text()
        self.assertIn("ref: main",wf)
        self.assertIn("cancel-in-progress: false",wf)
        self.assertIn("FACTORY_REPAIR_ENABLED",wf)
        dispatcher=(ROOT/".factory/scripts/repair_dispatch.py").read_text()
        self.assertIn('"run_id":decision.run_id',dispatcher)
        self.assertIn('"head_sha":decision.sha',dispatcher)
