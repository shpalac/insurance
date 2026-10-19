"""AC-3: no live-trading or dependency changes."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[3]

class Acceptance(unittest.TestCase):
    def test_ac_3_research_is_explicitly_non_actionable(self):
        text=(ROOT/"research/lambdaclass/README.md").read_text()
        self.assertIn("NO TRADE",text)
        self.assertIn("MIT",text)
        self.assertIn("fictional",text)
        self.assertIn("non-actionable",text)
        self.assertTrue((ROOT/"LICENSE").exists())
