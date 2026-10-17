import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from stall_watchdog import comment_decision,MARKER
class Acceptance(unittest.TestCase):
    def test_ac_2_scan_is_read_only_and_publish_is_status_only(self):
        status={"issue":73,"stalled":True,"idle_seconds":3600,"threshold_minutes":45,
                "latest_activity_at":"2026-10-18T01:00:00+00:00",
                "observed_at":"2026-10-18T02:00:00+00:00"}
        action,cid,body=comment_decision([],status)
        self.assertEqual(action,"create")
        self.assertIn(MARKER,body)
        self.assertEqual(comment_decision([{"id":12,"body":body,"user":{"type":"Bot"}}],status)[0],"noop")
        wf=(ROOT/".github/workflows/factory-stall-watchdog.yml").read_text()
        self.assertIn("issues: read",wf.split("  report:")[0])
        self.assertIn("issues: write",wf.split("  report:")[1])
        self.assertNotIn("git push",wf)
