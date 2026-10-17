"""Regression for audited closure's exact-main-SHA handoff."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/factory-verified-closure.yml"

class ClosureShaWiringTests(unittest.TestCase):
    def test_verify_proves_the_checked_out_main_commit(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('MAIN_SHA="$(git rev-parse HEAD)"', text)
        self.assertIn('echo "main_sha=$MAIN_SHA" >> "$GITHUB_OUTPUT"', text)
        self.assertIn('prepare --sha "$MAIN_SHA"', text)

    def test_privileged_apply_consumes_the_verification_sha(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('main_sha: ${{ steps.prove.outputs.main_sha }}', text)
        self.assertIn('MAIN_SHA: ${{ needs.verify.outputs.main_sha }}', text)
        self.assertIn('CLOSURE_PROOF: ${{ needs.verify.outputs.proof }}', text)
        self.assertNotIn('MAIN_SHA: ${{ github.event.workflow_run.head_sha || github.sha }}', text)

    def test_workflow_never_uses_untrusted_pr_code_with_write_token(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(text.count('ref: main'), 2)
        self.assertEqual(text.count('persist-credentials: false'), 2)
        self.assertIn('issues: write', text)
        self.assertIn('concurrency:', text)
        self.assertIn('cancel-in-progress: false', text)

if __name__ == "__main__":
    unittest.main()
