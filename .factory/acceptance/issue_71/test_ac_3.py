import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from factory_efficiency import aggregate
from datetime import datetime,timezone
class Acceptance(unittest.TestCase):
    def test_ac_3_definitions_are_documented_and_empty_sample_is_explicit(self):
        source=(ROOT/"docs/factory/efficiency-metrics.md").read_text()
        for term in ("Lead time","CI failure rate","PRs per Issue",
                     "Merges per hour","Worker idle time","Human interventions"):
            self.assertIn(term,source)
        d=aggregate([],[],[],{},{},"shpalac",datetime(2026,10,18,tzinfo=timezone.utc))
        self.assertIsNone(d["issue_lead_time_hours"]["median"])
        self.assertIsNone(d["ci_failure_rate"]["ratio"])
        self.assertIsNone(d["prs_per_issue"]["mean"])
        self.assertEqual(d["merges_per_hour"],0)
        self.assertIn("older_history",d["coverage_limits"])
