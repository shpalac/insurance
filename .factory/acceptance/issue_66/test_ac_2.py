"""Issue #66 AC-2: example arithmetic and no falsely promoted edge."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "docs/examples/hypothetical-credit-spread.json"


class HypotheticalCandidateAcceptance(unittest.TestCase):
    def test_ac_2_worked_example_has_consistent_fail_closed_result(self):
        payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        credit = payload["assumed_credit_points"] * payload["contract_multiplier"]
        payout = payload["assumed_expected_payout_points"] * payload["contract_multiplier"]
        costs = payload["assumed_all_in_transaction_costs_usd"]
        loss_cap = payload["width_points"] * payload["contract_multiplier"] - credit + costs

        self.assertEqual(credit - payout - costs, payload["modeled_net_expected_pnl_usd"])
        self.assertEqual(loss_cap, payload["modeled_maximum_loss_usd"])
        self.assertGreater(payload["modeled_net_expected_pnl_usd"], 0)
        self.assertIsNone(payload["conservative_ev_confidence_lower_bound_usd"])
        self.assertEqual(payload["point_in_time_options_backtest"], "NOT_PERFORMED")
        self.assertEqual(payload["classification"], "UNVERIFIED")
        self.assertEqual(payload["recommendation"], "NO TRADE")
        self.assertIn("FICTIONAL", payload["example_type"])

        self.assertIn("docs/examples/hypothetical-credit-spread.json", readme)
        self.assertIn("fictional arithmetic example", readme.lower())
        self.assertIn("$210 − $160 − $16 = **+$34**", readme)
        self.assertIn("$500 − $210 + $16 = **$306**", readme)
        self.assertIn("Without calibrated uncertainty", readme)


if __name__ == "__main__":
    unittest.main()
