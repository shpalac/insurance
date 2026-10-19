"""AC-2: optional workflow must pin real upstream and run Rust engine."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[3]

class Acceptance(unittest.TestCase):
    def test_ac_2_optional_engine_job_contract(self):
        workflow=(ROOT/".github/workflows/lambdaclass-research.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("afdbacc0b9b9c137edc38d656778f81b84093b2f",workflow)
        self.assertIn("maturin",workflow)
        self.assertIn("BacktestEngine",workflow)
        self.assertNotIn("pull_request:",workflow)
        self.assertNotIn("IBKR",workflow)
