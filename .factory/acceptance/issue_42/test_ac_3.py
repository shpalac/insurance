import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from compute_impact import impacted
from verify_factory_gate import gate_errors

class SelectiveMandatoryAcceptance(unittest.TestCase):
    def test_ac_3_docs_only_skips_native_builds_but_required_checks_fail_closed(self):
        sha = "a" * 40
        manifest = impacted(["docs/factory/ci-performance.md"], sha)
        self.assertTrue(manifest["selected_jobs"]["docs"])
        for name in ("scanner", "macos", "windows", "factory"):
            self.assertFalse(manifest["selected_jobs"][name])
        statuses = {"impact": "success", "policy": "success",
                    "issue_completion": "success",
                    "acceptance_macos": "success", "acceptance_windows": "success"}
        statuses.update({
            name: "success" if selected else "skipped"
            for name, selected in manifest["selected_jobs"].items()
        })
        self.assertEqual(gate_errors(manifest, sha, statuses), [])
        for name in ("policy", "issue_completion", "acceptance_macos",
                     "acceptance_windows"):
            with self.subTest(name=name):
                self.assertTrue(gate_errors(manifest, sha,
                                            dict(statuses, **{name: "failure"})))
        self.assertTrue(all(impacted(["surprise/new_plugin.zzz"], sha)["selected_jobs"].values()))
        workflow = (ROOT / ".github/workflows/ci-selective.yml").read_text()
        self.assertIn("scan_security.py --base", workflow)
        self.assertIn("RESULT_ACCEPTANCE_WINDOWS:", workflow)
        self.assertIn("cache-dependency-path: .factory/requirements-dev.txt", workflow)
