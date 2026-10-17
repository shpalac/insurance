"""AC-3: bounded event-driven queue progression and blocker prioritization."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from lease_state import InMemoryLeaseStore, acquire, complete
from orchestrator_loop import plan_next, prioritize

def emit():
    path = ROOT / "reports" / "ac-3.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", tests="1", failures="0", errors="0",
                       skipped="0", assertions="10")
    ET.SubElement(suite, "testcase", classname="Issue45AC3",
                  name="test_ac_3_queue_prioritizes_failures_and_advances")
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)

class Acceptance(unittest.TestCase):
    def test_ac_3_queue_prioritizes_failures_and_advances(self):
        now = datetime(2026, 10, 18, tzinfo=timezone.utc)
        items = [
            {"number": 45, "kind": "ready-issue", "linked_issue": 45,
             "is_pr": False},
            {"number": 82, "kind": "failing-pr", "linked_issue": 46,
             "is_pr": True},
            {"number": 99, "kind": "triage-issue", "linked_issue": 99,
             "is_pr": False},
        ]
        ordered = prioritize(items)
        self.assertEqual(ordered[0]["kind"], "failing-pr")
        plan = plan_next(items, {}, now=now, max_concurrent=2)
        self.assertEqual(plan["issue"], 46)
        self.assertEqual(plan["source_number"], 82)
        self.assertEqual(plan["role"], "ci-engineer")

        store = InMemoryLeaseStore()
        active = acquire(store, entity=46, owner="approved-worker",
                         role="ci-engineer", now=now,
                         ttl=timedelta(minutes=30))
        resumed_plan = plan_next(items, store.read_all(), now=now,
                                 max_concurrent=2)
        self.assertEqual(resumed_plan["issue"], 45)
        self.assertEqual(resumed_plan["role"], "planner")
        self.assertIsNone(plan_next(items, store.read_all(), now=now,
                                    max_concurrent=1))

        complete(store, entity=46, epoch=active.epoch, owner=active.owner,
                 now=now + timedelta(minutes=1))
        after_close = plan_next(
            [items[0]], store.read_all(), now=now + timedelta(minutes=1),
            max_concurrent=2,
        )
        self.assertEqual(after_close["issue"], 45)
        self.assertEqual(after_close["kind"], "ready-issue")

        dispatch_workflow = (ROOT / ".github/workflows/factory-agent-dispatch.yml").read_text()
        diagnostics_workflow = (ROOT / ".github/workflows/factory-orchestrator.yml").read_text()
        self.assertIn("workflow_run:", dispatch_workflow)
        self.assertIn("github.event.workflow_run.event == 'issues'", dispatch_workflow)
        self.assertIn("github.event.workflow_run.event == 'schedule'", dispatch_workflow)
        self.assertIn("ref: main", dispatch_workflow)
        self.assertIn("persist-credentials: false", dispatch_workflow)
        self.assertNotIn("\npull_request:", dispatch_workflow)
        self.assertIn("schedule:", diagnostics_workflow)
        self.assertIn("issues:", diagnostics_workflow)
        emit()

if __name__ == "__main__":
    unittest.main()
