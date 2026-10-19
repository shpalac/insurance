"""AC-1: independent synthetic cash/mark/NAV oracle."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research/lambdaclass"))
from synthetic_probe import expected_accounting, INITIAL_CASH, FICTIONAL_QUOTES

class Acceptance(unittest.TestCase):
    def test_ac_1_synthetic_accounting(self):
        rows = expected_accounting()
        self.assertEqual(len(rows), 3)
        self.assertEqual([round(x.nav, 2) for x in rows],
                         [9980.0, 10020.0, 10060.0])
        self.assertEqual(rows[0].cash, 9880.0)
        self.assertEqual(rows[2].option_mark, 0)
        self.assertEqual(rows[2].cash, 10060.0)
        self.assertEqual(FICTIONAL_QUOTES[0][0], "2026-01-05")
