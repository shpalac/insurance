import unittest
from datetime import datetime,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from stall_watchdog import detect,comment_decision
class Acceptance(unittest.TestCase):
    def test_ac_3_repeat_recovery_and_untrusted_comment_do_not_spam(self):
        now=datetime.fromisoformat("2026-10-18T02:00:00+00:00")
        lease={"entity":73,"phase":"repairing","owner":"worker","epoch":3,
               "heartbeat_at":"2026-10-18T00:15:00Z"}
        result=detect(73,lease,[],now)
        self.assertTrue(result["stalled"])
        self.assertFalse(detect(73,dict(lease,phase="done"),[],now)["stalled"])
        action,_,note=comment_decision([],result)
        self.assertEqual(action,"create")
        self.assertEqual(comment_decision([{"id":5,"body":note,
                     "user":{"type":"Bot"}}],result)[0],"noop")
        self.assertEqual(comment_decision([{"id":5,"body":note,
                     "user":{"type":"User"}}],result)[0],"create")
        self.assertEqual(comment_decision([{"id":5,"body":"old "+note,
                     "user":{"type":"Bot"}}],result)[0],"update")
