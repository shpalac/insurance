import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from factory_efficiency import render,MARKER
class Acceptance(unittest.TestCase):
    def test_ac_2_versioned_artifact_and_single_bot_tracking_comment(self):
        report={"schema_version":1,"as_of":"2026-10-18T00:00:00Z",
          "issue_lead_time_hours":{"median":2,"count":2},
          "ci_failure_rate":{"ratio":0.1,"failures":1,"completed":10},
          "prs_per_issue":{"mean":1.2},"merges_per_hour":0.5,
          "worker_idle_time_seconds":{"total_sampled_seconds":900},
          "human_interventions":{"owner_authorization_comments":3}}
        self.assertIn(MARKER,render(report))
        self.assertIn("CI failure rate:",render(report))
        wf=(ROOT/".github/workflows/factory-efficiency.yml").read_text()
        self.assertIn("factory-efficiency-v1.json",wf)
        self.assertIn("retention-days: 90",wf)
        self.assertIn("issues: read",wf.split("  publish:")[0])
        self.assertIn("issues: write",wf.split("  publish:")[1])
        script=(ROOT/".factory/scripts/factory_efficiency.py").read_text()
        self.assertIn("bot.get(\"body\")!=body",script)
        self.assertIn("TRACKING_ISSUE = 71",script)
