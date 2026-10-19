"""Fictional fixture contract; actual SDK smoke runs in dedicated CI."""
import csv
import os
from pathlib import Path
import tempfile
import unittest

from research.lambdaclass_probe import EXPECTED, write_fixture, run_probe


class LambdaClassResearchTest(unittest.TestCase):
    def test_fixture_contains_one_contract_and_bid_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            stocks, options = write_fixture(Path(tmp))
            with stocks.open(newline="", encoding="utf-8") as stream:
                stocks_rows = list(csv.DictReader(stream))
            with options.open(newline="", encoding="utf-8") as stream:
                option_rows = list(csv.DictReader(stream))
        self.assertEqual(len(stocks_rows), 9)
        self.assertEqual(len(option_rows), 9)
        self.assertEqual({row["underlying"] for row in option_rows}, {"XYZ"})
        self.assertEqual({row["optionroot"] for row in option_rows}, {"XYZ200717P00080000"})
        self.assertEqual(option_rows[0]["quotedate"], "2020-06-01")
        self.assertEqual(float(option_rows[0]["ask"]), 1.0)
        self.assertEqual(float(option_rows[0]["bid"]), 0.9)
        self.assertEqual(float(option_rows[-2]["bid"]), 30.0)
        self.assertEqual(stocks_rows[-1]["date"], "2020-07-02")

    def test_independent_accounting_derivation(self):
        # 5% of $100,030 buys floor($5,001.50 / $100) = 50 long puts;
        # 950 whole stock shares are bought with the remaining budget.
        initial = 100030.0
        contracts = int((initial * 0.05) // (1.0 * 100))
        shares = int((initial * 0.95) // 100.0)
        cash = initial - (contracts * 1.0 * 100) - (shares * 100.0)
        self.assertEqual(contracts, 50)
        self.assertEqual(shares, 950)
        self.assertEqual(cash, 30)
        self.assertEqual(EXPECTED["entry_nav"], cash + shares * 100 + contracts * 0.9 * 100)
        self.assertEqual(EXPECTED["crash_day_nav"], cash + shares * 80 + contracts * 5.0 * 100)
        self.assertEqual(EXPECTED["final_nav"], cash + shares * 50 + contracts * 30.0 * 100)

    def test_real_engine_when_ci_requires_it(self):
        if os.environ.get("LAMBDACLASS_SMOKE_REQUIRED") != "1":
            self.skipTest("SDK is intentionally not a production dependency")
        result = run_probe()
        self.assertEqual(result["status"], "SYNTHETIC_ENGINE_COMPATIBILITY_ONLY")
        self.assertEqual(result["recommendation"], "NO TRADE")
        self.assertEqual(result["actual"]["final_nav"], 197530.0)


if __name__ == "__main__":
    unittest.main()
