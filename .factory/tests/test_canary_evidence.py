"""Phase 7 canary must fail closed on synthetic or incomplete proofs."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from verify_canary_evidence import STEPS, validate_proof, verify_online  # noqa: E402

REPO = "shpalac/insurance"
SHA = "a" * 40


def proof():
    return {
        "repository": REPO, "mode": "live", "main_sha": SHA,
        "steps": {
            key: {
                "result": "passed",
                "workflow_run_url": f"https://github.com/{REPO}/actions/runs/123",
                "artifact_sha256": "b" * 64,
                "commit_sha": SHA,
            }
            for key in STEPS
        },
    }


class CanaryEvidenceTests(unittest.TestCase):
    def test_valid_shape_passes_structural_preflight(self):
        self.assertEqual(validate_proof(proof(), repository=REPO), [])

    def test_empty_evidence_is_rejected(self):
        self.assertTrue(validate_proof({}, repository=REPO))

    def test_simulated_canary_is_rejected(self):
        candidate = proof()
        candidate["mode"] = "simulated"
        self.assertTrue(validate_proof(candidate, repository=REPO))

    def test_missing_fault_injection_is_rejected(self):
        candidate = proof()
        del candidate["steps"]["expired_lease_resumed"]
        self.assertTrue(validate_proof(candidate, repository=REPO))

    def test_missing_main_sha_rejected(self):
        candidate = proof()
        candidate["main_sha"] = "main"
        self.assertTrue(validate_proof(candidate, repository=REPO))

    def test_false_success_rejected(self):
        candidate = proof()
        candidate["steps"]["ci_only_admission"]["result"] = "skipped"
        self.assertTrue(validate_proof(candidate, repository=REPO))

    def test_wrong_repository_rejected(self):
        candidate = proof()
        candidate["repository"] = "other/repository"
        self.assertTrue(validate_proof(candidate, repository=REPO))

    def test_offsite_run_url_rejected(self):
        candidate = proof()
        candidate["steps"]["merged"]["workflow_run_url"] = "https://evil.invalid/run/2"
        self.assertTrue(validate_proof(candidate, repository=REPO))

    def test_real_online_run_and_digest_can_be_verified(self):
        evidence = proof()
        def fetch(path):
            if path == "/git/ref/heads/main":
                return {"object": {"sha": SHA}}
            if path == "/actions/runs/123":
                return {
                    "head_sha": SHA, "status": "completed", "conclusion": "success"
                }
            if path == "/actions/runs/123/artifacts":
                return {"total_count": 1, "artifacts": [
                    {"digest": "sha256:" + "b" * 64, "expired": False}
                ]}
            raise AssertionError("Unexpected URL: " + path)
        self.assertEqual(verify_online(evidence, repository=REPO, fetch=fetch), [])

    def test_online_digest_must_exist_and_be_unexpired(self):
        evidence = proof()
        def fetch(path):
            if path == "/git/ref/heads/main":
                return {"object": {"sha": SHA}}
            if path.startswith("/actions/runs/") and path.endswith("/artifacts"):
                return {"total_count": 1, "artifacts": [
                    {"digest": "sha256:" + "c" * 64, "expired": True}
                ]}
            return {"head_sha": SHA, "status": "completed", "conclusion": "success"}
        self.assertTrue(verify_online(evidence, repository=REPO, fetch=fetch))

    def test_online_main_sha_and_run_head_mismatches_block(self):
        evidence = proof()
        def fetch(path):
            if path == "/git/ref/heads/main":
                return {"object": {"sha": "c" * 40}}
            if path.startswith("/actions/runs/"):
                return {"head_sha": "d" * 40, "status": "completed", "conclusion": "success"}
            raise AssertionError(path)
        self.assertTrue(verify_online(evidence, repository=REPO, fetch=fetch))

    def test_missing_artifact_hash_rejected(self):
        candidate = proof()
        candidate["steps"]["issue_closed"]["artifact_sha256"] = ""
        self.assertTrue(validate_proof(candidate, repository=REPO))


if __name__ == "__main__":
    unittest.main()
