"""Named hosted-runner acceptance tests for Issue #4 selective factory CI."""

from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from compute_impact import impacted
from verify_factory_gate import gate_errors
from scan_security import (
    inspect_added_lines, scan_patch, scan_repo, workflow_action_errors,
)

SHA = "a" * 40


def emit(ac: int, test_name: str) -> None:
    path = ROOT / "reports" / f"issue-4-ac-{ac}.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element(
        "testsuite", tests="1", failures="0", errors="0",
        skipped="0", assertions="2",
    )
    ET.SubElement(suite, "testcase", classname="Issue4Acceptance", name=test_name)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


class Issue4Acceptance(unittest.TestCase):
    def test_ac_1_docs_only_does_not_select_application_compilers(self):
        plan = impacted(["docs/factory/standards.md"], SHA)
        self.assertEqual(plan["reason"], "affected_modules")
        self.assertTrue(plan["selected_jobs"]["docs"])
        self.assertFalse(plan["selected_jobs"]["scanner"])
        self.assertFalse(plan["selected_jobs"]["macos"])
        self.assertFalse(plan["selected_jobs"]["windows"])
        emit(1, self._testMethodName)

    def test_ac_2_source_changes_select_consumer_tests_and_requested_os(self):
        plan = impacted(
            ["src/insurance/core.py", "tests/test_core.py"], SHA,
            requested_runners=("macos-latest", "windows-latest"),
        )
        # The scanner lane runs the full Python module and dependent test suite.
        self.assertTrue(plan["selected_jobs"]["scanner"])
        self.assertTrue(plan["selected_jobs"]["macos"])
        self.assertTrue(plan["selected_jobs"]["windows"])
        self.assertEqual(plan["requested_runners"], [
            "macos-latest", "windows-latest",
        ])
        with self.assertRaises(ValueError):
            impacted(["src/insurance/core.py"], SHA, ("self-hosted",))
        emit(2, self._testMethodName)

    def test_ac_3_unknown_dynamic_or_control_plane_changes_use_full_matrix(self):
        paths = (
            "pyproject.toml",
            ".github/workflows/ci-selective.yml",
            "deps/service.lock",
            "src/plugin_loader.xyz",
            "ios/mobile/feature.dart",
        )
        for path in paths:
            with self.subTest(path=path):
                plan = impacted([path], SHA)
                self.assertTrue(all(plan["selected_jobs"].values()))
        emit(3, self._testMethodName)

    def test_ac_4_failed_missing_skipped_stale_or_empty_gate_fails_closed(self):
        plan = impacted(["src/insurance/core.py"], SHA)
        statuses = {"impact": "success", "policy": "success",
                    "issue_completion": "success"}
        statuses.update({
            job: "success" if required else "skipped"
            for job, required in plan["selected_jobs"].items()
        })
        self.assertEqual(gate_errors(plan, SHA, statuses), [])
        for job, state in (
            ("policy", "failure"), ("scanner", "skipped"),
            ("issue_completion", "cancelled"), ("issue_completion", ""),
        ):
            with self.subTest(job=job, state=state):
                broken = dict(statuses, **{job: state})
                self.assertTrue(gate_errors(plan, SHA, broken))
        self.assertTrue(gate_errors(plan, "b" * 40, statuses))
        self.assertTrue(gate_errors(impacted([], SHA), SHA, statuses))
        emit(4, self._testMethodName)

    def test_ac_5_docs_always_run_security_policy_and_detect_added_secrets(self):
        workflow = (ROOT / ".github/workflows/ci-selective.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("needs: [impact, policy, issue-completion", workflow)
        self.assertIn("Run mandatory secret and pinned-workflow checks", workflow)
        self.assertIn("scan_security.py --base", workflow)
        # Construct known credential signatures in fragments so no literal
        # committed fake token gets mistaken for a real one by other scanners.
        github_signature = "gh" + "p_" + ("A" * 36)
        aws_signature = "AK" + "IA" + "0123456789ABCDEF"
        self.assertEqual(len(inspect_added_lines([github_signature])), 1)
        self.assertEqual(len(inspect_added_lines([aws_signature])), 1)
        self.assertTrue(scan_patch("+docs changed\n+" + github_signature + "\n"))
        self.assertFalse(scan_patch("--- a/readme.md\n-removed token\n+safe doc\n"))
        emit(5, self._testMethodName)

    def test_ac_6_actions_use_commit_shas_and_unpinned_actions_fail(self):
        self.assertEqual(scan_repo(ROOT, ""), [])
        unpinned = "steps:\n  - uses: actions/checkout@v4\n"
        pinned = (
            "steps:\n  - uses: actions/checkout@"
            + "a" * 40 + "\n"
        )
        self.assertTrue(workflow_action_errors(unpinned, "sample.yml"))
        self.assertEqual(workflow_action_errors(pinned, "sample.yml"), [])
        self.assertEqual(workflow_action_errors(
            "steps:\n  - uses: ./.github/actions/test\n", "sample.yml"
        ), [])
        emit(6, self._testMethodName)


if __name__ == "__main__":
    unittest.main()
