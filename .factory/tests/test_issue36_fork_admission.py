"""Issue #36: fork PRs cannot enter the privileged trusted-admission path."""
import os
import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
import trusted_admission


class FakeAPI:
    def __init__(self, pr):
        self.pr = pr
        self.calls = []

    def call(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.startswith("/pulls/"):
            return self.pr
        return {"ok": True}


class Issue36ForkAdmissionAcceptance(unittest.TestCase):
    def test_ac_3_fork_pr_is_blocked_before_jobs_files_or_comments_are_read(self):
        sha = "a" * 40
        pr = {
            "head": {"sha": sha, "repo": {"full_name": "attacker/insurance"}},
            "base": {"ref": "main"},
            "state": "open",
        }
        api = FakeAPI(pr)
        old = os.environ.get("GITHUB_REPOSITORY")
        os.environ["GITHUB_REPOSITORY"] = "shpalac/insurance"
        try:
            result = trusted_admission.handle({
                "workflow_run": {
                    "name": "Factory selective CI", "event": "pull_request",
                    "id": 123, "pull_requests": [{"number": 99}],
                }
            }, api, "shpalac")
        finally:
            if old is None:
                os.environ.pop("GITHUB_REPOSITORY", None)
            else:
                os.environ["GITHUB_REPOSITORY"] = old
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Fork PRs are not eligible for trusted admission", result["errors"])
        self.assertEqual([call[1] for call in api.calls],
                         ["/pulls/99", "/check-runs"])
        self.assertEqual(api.calls[-1][2]["conclusion"], "failure")

    def test_ac_3_missing_head_repository_fails_closed(self):
        sha = "b" * 40
        api = FakeAPI({"head": {"sha": sha, "repo": None}, "state": "open"})
        old = os.environ.get("GITHUB_REPOSITORY")
        os.environ["GITHUB_REPOSITORY"] = "shpalac/insurance"
        try:
            result = trusted_admission.handle({
                "workflow_run": {
                    "name": "Factory selective CI", "event": "pull_request",
                    "id": 124, "pull_requests": [{"number": 100}],
                }
            }, api, "shpalac")
        finally:
            if old is None:
                os.environ.pop("GITHUB_REPOSITORY", None)
            else:
                os.environ["GITHUB_REPOSITORY"] = old
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Fork PRs are not eligible for trusted admission", result["errors"])
        self.assertEqual(api.calls[-1][2]["conclusion"], "failure")


if __name__ == "__main__":
    unittest.main()
