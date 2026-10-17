"""Disposable negative branch-protection canary; MUST NEVER MERGE."""
import unittest

class NegativeMergeCanary(unittest.TestCase):
    def test_required_unit_tests_reject_this_branch(self):
        self.fail("ISSUE35_NEGATIVE_CANARY: intentional required-check failure; do not merge")
