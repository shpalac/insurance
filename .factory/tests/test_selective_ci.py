"""Conservative impact selection and fail-closed factory gate proofs."""

import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from compute_impact import impacted  # noqa: E402
from verify_factory_gate import gate_errors  # noqa: E402

HEAD = "a" * 40


class ImpactAndGateTests(unittest.TestCase):
    def ok_statuses(self, manifest):
        return {
            "impact": "success",
            "policy": "success",
            "issue_completion": "success",
            "acceptance_macos": "success",
            "acceptance_windows": "success",
            **{
                name: "success" if selected else "skipped"
                for name, selected in manifest["selected_jobs"].items()
            },
        }

    def test_docs_diff_avoids_application_tests(self):
        result = impacted(["docs/factory/standards.md"], HEAD)
        self.assertFalse(result["selected_jobs"]["scanner"])
        self.assertFalse(result["selected_jobs"]["factory"])
        self.assertTrue(result["selected_jobs"]["docs"])

    def test_scanner_change_selects_scanner_only(self):
        result = impacted(["src/insurance/core.py"], HEAD)
        self.assertTrue(result["selected_jobs"]["scanner"])
        self.assertFalse(result["selected_jobs"]["factory"])
        self.assertFalse(result["selected_jobs"]["windows"])

    def test_control_plane_escalates_to_all(self):
        result = impacted([".github/workflows/ci.yml"], HEAD)
        self.assertTrue(all(result["selected_jobs"].values()))

    def test_unknown_path_escalates_to_all(self):
        result = impacted(["unmapped/new_build_tool.xyz"], HEAD)
        self.assertTrue(all(result["selected_jobs"].values()))

    def test_global_lockfile_escalates_to_all(self):
        result = impacted(["some/dependencies.lock"], HEAD)
        self.assertTrue(all(result["selected_jobs"].values()))

    def test_windows_platform_selects_windows(self):
        result = impacted(["windows/desktop/app.py"], HEAD)
        self.assertTrue(result["selected_jobs"]["windows"])
        self.assertFalse(result["selected_jobs"]["scanner"])

    def test_empty_diff_escalates_to_full_suite(self):
        result = impacted([], HEAD)
        self.assertTrue(all(result["selected_jobs"].values()))

    def test_deleted_test_file_stays_affected(self):
        result = impacted(["tests/test_core.py"], HEAD)
        self.assertTrue(result["selected_jobs"]["scanner"])

    def test_reject_incomplete_sha(self):
        with self.assertRaises(ValueError):
            impacted(["docs/README.md"], "main")

    def test_gate_accepts_true_success(self):
        result = impacted(["src/insurance/core.py"], HEAD)
        self.assertEqual(gate_errors(result, HEAD, self.ok_statuses(result)), [])

    def test_selected_skipped_fails(self):
        result = impacted(["src/insurance/core.py"], HEAD)
        statuses = self.ok_statuses(result)
        statuses["scanner"] = "skipped"
        self.assertTrue(gate_errors(result, HEAD, statuses))

    def test_selected_failed_fails(self):
        result = impacted(["src/insurance/core.py"], HEAD)
        statuses = self.ok_statuses(result)
        statuses["scanner"] = "failure"
        self.assertTrue(gate_errors(result, HEAD, statuses))

    def test_missing_or_skipped_issue_completion_fails(self):
        result = impacted(["src/insurance/core.py"], HEAD)
        statuses = self.ok_statuses(result)
        statuses["issue_completion"] = "skipped"
        self.assertTrue(gate_errors(result, HEAD, statuses))
        statuses.pop("issue_completion")
        self.assertTrue(gate_errors(result, HEAD, statuses))

    def test_head_mismatch_fails(self):
        result = impacted(["src/insurance/core.py"], HEAD)
        self.assertTrue(gate_errors(result, "b" * 40, self.ok_statuses(result)))

    def test_corrupt_manifest_fails(self):
        result = impacted(["src/insurance/core.py"], HEAD)
        result["selected_jobs"]["scanner"] = False
        self.assertTrue(gate_errors(result, HEAD, self.ok_statuses(result)))

    def test_missing_baseline_fails(self):
        result = impacted(["docs/factory/standards.md"], HEAD)
        statuses = self.ok_statuses(result)
        statuses["policy"] = "skipped"
        self.assertTrue(gate_errors(result, HEAD, statuses))


if __name__ == "__main__":
    unittest.main()
