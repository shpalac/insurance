"""Issue #90 AC-2: fail-closed, actual upstream-engine CI contract."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class Acceptance(unittest.TestCase):
    def test_ac_2_hosted_ci_pins_dependency_and_runs_real_engine(self):
        workflow = (ROOT / ".github/workflows/lambdaclass-research.yml").read_text(
            encoding="utf-8"
        )
        probe = (ROOT / "research/lambdaclass_probe.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("LAMBDACLASS_SMOKE_REQUIRED:", workflow)
        self.assertIn('"1"', workflow)
        self.assertIn(
            "options_portfolio_backtester.git@afdbacc0b9b9c137edc38d656778f81b84093b2f",
            workflow,
        )
        self.assertIn("research/lambdaclass_probe.py --output", workflow)
        self.assertIn("python -m unittest discover", workflow)
        self.assertIn("engine.run(rebalance_freq=1, rebalance_unit=\"BMS\")", probe)
        self.assertIn("MarketAtBidAsk()", probe)
        self.assertIn("engine.assert_invariants = True", probe)
        self.assertIn("raise AssertionError(", probe)


if __name__ == "__main__":
    unittest.main()
