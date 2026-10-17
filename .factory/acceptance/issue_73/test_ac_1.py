import unittest
from datetime import datetime,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from stall_watchdog import detect
class Acceptance(unittest.TestCase):
    def test_ac_1_claim_without_updates_trips_configurable_idle_threshold(self):
        now=datetime.fromisoformat("2026-10-18T02:00:00+00:00")
        lease={"entity":73,"phase":"claimed","owner":"worker","epoch":1,"heartbeat_at":"2026-10-18T00:45:00Z"}
        result=detect(73,lease,[],now,threshold_minutes=45)
        self.assertTrue(result["stalled"])
        self.assertEqual(result["idle_seconds"],4500)
        self.assertEqual(result["latest_activity_at"],"2026-10-18T00:45:00+00:00")
        self.assertFalse(detect(73,lease,["2026-10-18T01:55:00Z"],now)["stalled"])
