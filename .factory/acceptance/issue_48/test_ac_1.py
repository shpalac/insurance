"""AC-1: a real autonomous delivery must be separately attested on main."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from two_issue_canary import LiveTwoIssueCanaryMissing, verify_live_two_issue_canary

SHA="a"*40

class MissingPrerequisites:
    def __init__(self, issue47="open", runs=None):
        self.issue47=issue47
        self.runs=runs if runs is not None else []
    def get(self, path):
        if path=="/git/ref/heads/main":
            return {"object":{"sha":SHA}}
        if path=="/issues/47":
            return {"state":self.issue47}
        if path.startswith("/actions/runs?"):
            return {"total_count":len(self.runs),"workflow_runs":self.runs}
        raise AssertionError("unexpected source: "+path)

class Acceptance(unittest.TestCase):
    def test_ac_1_does_not_substitute_unit_tests_for_live_agent_delivery(self):
        with self.assertRaises(LiveTwoIssueCanaryMissing):
            verify_live_two_issue_canary(MissingPrerequisites(),SHA)
        with self.assertRaises(LiveTwoIssueCanaryMissing):
            verify_live_two_issue_canary(MissingPrerequisites(issue47="closed"),SHA)
        closure=(ROOT/".factory/scripts/post_merge_closure.py").read_text()
        self.assertIn('if number == 48:',closure)
        self.assertIn('item["two_issue_canary"] = verify_live_two_issue_canary(api, sha)',closure)
        self.assertIn('item.get("two_issue_canary") != verify_live_two_issue_canary(api, sha)',closure)
        self.assertTrue(SHA and len(SHA)==40)
