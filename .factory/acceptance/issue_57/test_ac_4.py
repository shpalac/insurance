"""AC-4: existing reviewed tests still pass without N duplicate suite runs."""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from run_acceptance_manifest import load_targets, run_criteria, verify_report
from acceptance_discovery import available_criteria


def manifest():
    return {"acceptance_criteria": [
        {"id": f"AC-{n}", "runner_os": "ubuntu-latest",
         "required_report": f"reports/legacy-{n}.xml",
         "timeout_seconds": 60}
        for n in (1, 2)
    ]}


class CompatibilityAcceptance(unittest.TestCase):
    def test_ac_4_existing_reviewed_registry_remains_supported(self):
        registry = load_targets(ROOT)
        self.assertIn("5/AC-1", registry)
        self.assertEqual(
            available_criteria(ROOT, 5, ["AC-1"], registry),
            {"AC-1": "reviewed"}
        )

    def test_ac_4_shared_legacy_unittest_runs_only_once_for_two_criteria(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = {
                "runner_os": "ubuntu-latest",
                "argv": ["python", "-m", "unittest", "discover",
                         "-s", ".factory/tests", "-p", "test_legacy.py"],
            }
            targets = {"944/AC-1": target, "944/AC-2": target}
            invocations = []
            def run_group(command, **kwargs):
                invocations.append(tuple(command))
                for n in (1, 2):
                    path = root / "reports" / f"legacy-{n}.xml"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    suite = ET.Element("testsuite", tests="1", assertions="2")
                    ET.SubElement(suite, "testcase", name=f"test_ac_{n}")
                    ET.ElementTree(suite).write(path)
                return SimpleNamespace(returncode=0, stderr="")
            with mock.patch("run_acceptance_manifest.validate_body", return_value=[]), \
                 mock.patch("run_acceptance_manifest.extract_manifest",
                            return_value=manifest()), \
                 mock.patch("run_acceptance_manifest.subprocess.run",
                            side_effect=run_group):
                records = run_criteria(
                    "untrusted illustrative commands", issue_id=944,
                    head_sha="a"*40, root=root, targets=targets
                )
            self.assertEqual(len(invocations), 1)
            self.assertEqual([row["id"] for row in records], ["AC-1", "AC-2"])
            self.assertTrue(all(row["assertions"] >= 1 for row in records))

    def test_ac_4_junit_cannot_claim_success_without_case_or_assertions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "invalid.xml"
            path.write_text('<testsuite tests="0" assertions="0"/>')
            with self.assertRaises(ValueError):
                verify_report(path)


if __name__ == "__main__":
    unittest.main()
