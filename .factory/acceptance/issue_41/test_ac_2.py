import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
sys.path.insert(0, str(ROOT / ".factory/tests"))
from post_merge_closure import apply, prepare, ReconcileError
from test_post_merge_closure import FakeGitHub, passing_run, SHA

class ReplaySafeClosure(unittest.TestCase):
    def test_ac_2_replay_and_spec_change_fail_closed(self):
        api = FakeGitHub()
        plan = prepare(api, SHA, 101, run=passing_run)
        self.assertEqual(plan["items"][0]["status"], "ready")
        self.assertEqual(apply(api, SHA, plan)["closed"], [142])
        self.assertEqual(apply(api, SHA, plan)["closed"], [])
        self.assertEqual(len(api.comments[142]), 1)
        self.assertEqual(len(api.patches), 1)
        next_api = FakeGitHub()
        altered = prepare(next_api, SHA, 102, run=passing_run)
        next_api.issues[142]["body"] += "New acceptance revision."
        self.assertEqual(apply(next_api, SHA, altered)["closed"], [])
        stale_api = FakeGitHub()
        stale_plan = prepare(stale_api, SHA, 103, run=passing_run)
        stale_api.head = "b" * 40
        with self.assertRaises(ReconcileError):
            apply(stale_api, SHA, stale_plan)
        workflow = (ROOT / ".github/workflows/factory-verified-closure.yml").read_text()
        self.assertIn("group: insurance-verified-issue-closure", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
