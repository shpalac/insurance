import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
sys.path.insert(0, str(ROOT / "src"))
from scanner_safety_gate import cases, verify
from insurance.core import scan_snapshot, Settings

class ScannerSafetyAcceptance(unittest.TestCase):
    def test_ac_2_invalid_market_data_never_supports_trading(self):
        self.assertEqual(verify()["cases"], 6)
        for label, snapshot in cases():
            with self.subTest(label=label):
                result = scan_snapshot(snapshot, Settings(simulations=200))
                self.assertEqual(result["recommendation"], "NO TRADE")
                self.assertEqual(result["market_data_eligible"], 0)
                self.assertEqual(result["supported_opportunities"], [])
                self.assertTrue(result["rejection_counts"])
