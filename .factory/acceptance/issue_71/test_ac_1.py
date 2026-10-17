import unittest
from datetime import datetime,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from factory_efficiency import aggregate
class Acceptance(unittest.TestCase):
    def test_ac_1_lead_time_failure_rate_rework_merges_idle_and_interventions(self):
        issues=[{"number":1,"created_at":"2026-10-17T18:00:00Z",
                 "closed_at":"2026-10-17T21:00:00Z"},
                {"number":2,"created_at":"2026-10-17T15:00:00Z",
                 "closed_at":"2026-10-17T21:00:00Z"}]
        prs=[{"number":10,"merged_at":"2026-10-17T21:00:00Z","body":"Refs #1"},
             {"number":11,"merged_at":"2026-10-17T22:00:00Z","body":"Refs #1"}]
        runs=[{"status":"completed","conclusion":"success"},
              {"status":"completed","conclusion":"failure"}]
        auth={"user":{"login":"shpalac"},"body":"FACTORY-OWNER-AUTH sha="+"a"*40+
              " reason=Reviewed protected execution semantics"}
        idle={1:[{"user":{"type":"Bot"},
            "body":"<!-- FACTORY_STALL_WATCH_V1 -->\nSTALLED\nIdle seconds: 3600\n"}]}
        d=aggregate(issues,prs,runs,{10:[auth],11:[]},idle,"shpalac",
                    datetime(2026,10,18,0,0,tzinfo=timezone.utc))
        self.assertEqual(d["issue_lead_time_hours"]["median"],4.5)
        self.assertEqual(d["ci_failure_rate"]["ratio"],0.5)
        self.assertEqual(d["prs_per_issue"]["counts"]["1"],2)
        self.assertEqual(d["merges_per_hour"],round(2/24,5))
        self.assertEqual(d["worker_idle_time_seconds"]["total_sampled_seconds"],3600)
        self.assertEqual(d["human_interventions"]["owner_authorization_comments"],1)
