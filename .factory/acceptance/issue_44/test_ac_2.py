import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from lease_state import InMemoryLeaseStore,acquire,StaleLease
from lease_fencing import WorkerProof,assert_fence,ACTION_ROLE

class Acceptance(unittest.TestCase):
    def test_ac_2_stale_epochs_block_every_agent_mutation_role(self):
        origin=datetime(2026,10,18,tzinfo=timezone.utc)
        roles={"branch_push":"developer","ci_repair":"ci-engineer",
               "issue_transition":"validator","integrator_merge":"integrator"}
        self.assertEqual(set(roles),set(ACTION_ROLE))
        integrator=(ROOT/".factory/scripts/pr_merge_coordinator.py").read_text()
        self.assertIn("live_integrator_fence(api, latest, repo)",integrator)
        self.assertIn("active_integrator_lease_required",integrator)
        for idx,(action,role) in enumerate(roles.items()):
            with self.subTest(action=action):
                store=InMemoryLeaseStore()
                entity=4400+idx
                first=acquire(store,entity=entity,owner="first",role=role,
                              now=origin,ttl=timedelta(minutes=30))
                old=WorkerProof(entity,first.epoch,first.revision,"first",role,"","")
                self.assertEqual(assert_fence(store,proof=old,operation=action,
                    authenticated_login="first",approved_logins={"first"},
                    now=origin).epoch,1)
                late=origin+timedelta(minutes=31)
                with self.assertRaises(StaleLease):
                    assert_fence(store,proof=old,operation=action,
                        authenticated_login="first",approved_logins={"first"},now=late)
                renewed=acquire(store,entity=entity,owner="second",role=role,
                                now=late,ttl=timedelta(minutes=30))
                self.assertEqual(renewed.epoch,2)
                with self.assertRaises(StaleLease):
                    assert_fence(store,proof=old,operation=action,
                        authenticated_login="first",approved_logins={"first"},now=late)
                fresh=WorkerProof(entity,renewed.epoch,renewed.revision,"second",role,"","")
                self.assertEqual(assert_fence(store,proof=fresh,operation=action,
                    authenticated_login="second",approved_logins={"second"},now=late).epoch,2)
                with self.assertRaises(StaleLease):
                    assert_fence(store,proof=fresh,operation=action,
                        authenticated_login="attacker",approved_logins={"second"},now=late)
