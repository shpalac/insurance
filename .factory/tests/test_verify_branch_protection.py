"""Real branch enforcement must come from effective GitHub rules, not YAML text."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from verify_branch_protection import (
    REQUIRED, audit, validated_rules, validated_legacy_protection,
)


class BranchRulesTests(unittest.TestCase):
    def test_no_rules_fail_closed(self):
        self.assertTrue(audit(None, None))
        self.assertTrue(audit([], {}))

    def test_modern_effective_rules_enforce_exact_contexts(self):
        rules = [{
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [
                    {"context": name} for name in sorted(REQUIRED)
                ],
            },
        }]
        self.assertEqual(validated_rules(rules), [])
        self.assertEqual(audit(rules, None), [])

    def test_partial_policy_cannot_accidentally_pass(self):
        partial = [{
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [
                {"context": "unit-tests"},
            ]},
        }]
        self.assertTrue(validated_rules(partial))
        self.assertTrue(audit(partial, None))

    def test_union_of_two_incomplete_policies_must_fail(self):
        modern = [{
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [
                {"context": "unit-tests"},
            ]},
        }]
        classic = {
            "required_status_checks": {
                "contexts": ["factory-bootstrap-gate", "factory-gate-preflight"]
            }
        }
        self.assertTrue(audit(modern, classic))

    def test_classic_required_contexts_prove_enforcement(self):
        legacy = {"required_status_checks": {
            "strict": True,
            "contexts": ["unit-tests", "factory-bootstrap-gate"],
            "checks": [{"context": "factory-gate-preflight"}],
        }}
        self.assertEqual(validated_legacy_protection(legacy), [])
        self.assertEqual(audit(None, legacy), [])

    def test_future_check_name_drift_does_not_count_as_enforcement(self):
        fake = {"required_status_checks": {
            "contexts": ["unit-tests", "factory-bootstrap-gate",
                         "factory-gate"]
        }}
        self.assertTrue(validated_legacy_protection(fake))


if __name__ == "__main__":
    unittest.main()
