"""Issue #90 AC-3: enforce documented synthetic-only scope and MIT."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class Acceptance(unittest.TestCase):
    def test_ac_3_mit_and_no_trade_safety_contract_preserved(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        doc = (ROOT / "docs/research-lambdaclass.md").read_text(encoding="utf-8")
        probe = (ROOT / "research/lambdaclass_probe.py").read_text(encoding="utf-8")
        scanner = (ROOT / "src/insurance/core.py").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("synthetic", doc.lower())
        self.assertIn("NO TRADE", doc)
        self.assertIn("not a historical", doc.lower())
        self.assertIn('"recommendation": "NO TRADE"', probe)
        self.assertIn('"supports_trade_recommendations": False', probe)
        self.assertNotIn("options_portfolio_backtester", scanner)


if __name__ == "__main__":
    unittest.main()
