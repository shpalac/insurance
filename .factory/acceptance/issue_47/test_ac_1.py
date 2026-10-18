"""Issue #47: executable guarded integration acceptance tests."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory" / "scripts"))
from pr_merge_coordinator import REQUIRED, approved, check_gate, select

SHA = "a" * 40
MAIN = "b" * 40
REPO = "shpalac/insurance"


def candidate(state="clean", paths=None, auth=True, green=True):
    pr = {"number": 47, "state": "open", "draft": False,
          "created_at": "2026-10-18T00:00:00Z",
          "head": {"sha": SHA, "repo": {"full_name": REPO}},
          "base": {"ref": "main"}, "mergeable": True,
          "mergeable_state": state}
    checks = [{"name": n, "head_sha": SHA, "status": "completed",
               "conclusion": "success"} for n in REQUIRED]
    if not green:
        checks[0]["conclusion"] = "failure"
    comments = ([{"user": {"login": "shpalac"},
                  "body": "FACTORY-OWNER-AUTH sha=" + SHA +
                          " reason=Approve protected issue forty seven changes"}]
                if auth else [])
    return pr, {47: paths or ["src/insurance/strategy.py"]}, {47: comments}, {47: checks}


class GuardedIntegratorAcceptance(unittest.TestCase):
    def decision(self, **kwargs):
        pr, files, comments, checks = candidate(**kwargs)
        return select([pr], MAIN, REPO, files, comments, checks, "shpalac")

    def test_ac_1_rejects_missing_checks_drafts_forks_and_stale_sha(self):
        self.assertEqual(self.decision(green=False)["action"], "idle")
        pr, files, comments, checks = candidate()
        pr["draft"] = True
        self.assertEqual(select([pr], MAIN, REPO, files, comments, checks,
                                "shpalac")["action"], "idle")
        pr["draft"] = False
        pr["head"]["repo"]["full_name"] = "attacker/insurance"
        self.assertEqual(select([pr], MAIN, REPO, files, comments, checks,
                                "shpalac")["action"], "idle")
        self.assertFalse(check_gate(checks[47], "c" * 40))



if __name__ == "__main__":
    unittest.main()
