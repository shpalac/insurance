import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from factory_ci_metrics import build_report, percentile, MetricsError

SHA = "a" * 40

def fixture(n, elapsed):
    timestamp = "2026-10-18T00:00:00Z"
    return ({"id": n, "name": "Factory selective CI",
             "head_sha": SHA, "status": "completed", "event": "pull_request",
             "conclusion": "success", "created_at": timestamp,
             "run_started_at": timestamp,
             "updated_at": f"2026-10-18T00:{elapsed:02d}:00Z"},
            [{"name": "scanner", "status": "completed", "conclusion": "success",
              "started_at": timestamp,
              "completed_at": f"2026-10-18T00:{elapsed:02d}:00Z"}])

class PerformanceMetricAcceptance(unittest.TestCase):
    def test_ac_2_sha_run_context_and_lane_percentiles_are_measured(self):
        run, jobs = fixture(100, 1)
        history = [fixture(101, 3), fixture(102, 5)]
        report = build_report(run, jobs, history, ["src/insurance/core.py"],
                              "github-pr-files", [
            {"name": "factory-gate-preflight", "head_sha": SHA,
             "conclusion": "success", "completed_at": "2026-10-18T00:01:00Z"}])
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["current"]["run_id"], 100)
        self.assertEqual(report["current"]["sha"], SHA)
        self.assertTrue(report["paths_complete"])
        self.assertEqual(report["history_runs"], 3)
        self.assertEqual(report["lanes"]["scanner"]["p50_seconds"], 180)
        self.assertEqual(report["lanes"]["scanner"]["p95_seconds"], 288)
        self.assertEqual(report["required_checks"]["factory-gate-preflight"], "success")
        self.assertEqual(report["required_checks"]["unit-tests"], "pending")
        self.assertIsNone(percentile([], 0.50))
        with self.assertRaises(MetricsError):
            build_report(run, jobs, history, ["../../unsafe"], "github-pr-files", [])
        workflow = (ROOT / ".github/workflows/factory-ci-metrics.yml").read_text()
        self.assertIn("workflow_run:", workflow)
        self.assertIn("ref: main", workflow)
        self.assertIn("factory-ci-performance-v1", workflow)
