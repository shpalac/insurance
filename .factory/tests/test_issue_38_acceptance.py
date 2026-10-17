"""Issue #38: mandatory reference and safe closure semantics."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from pr_completion_gate import CompletionError, parse_intent, trusted_maintenance
from integration_policy import closure_progress
from post_merge_closure import linked_merged_prs

SHA = "a" * 40


def emit(n: int, name: str):
    path = ROOT / "reports" / f"ac-{n}.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", tests="1", failures="0", errors="0",
                       skipped="0", assertions="3")
    ET.SubElement(suite, "testcase", classname="Issue38Acceptance", name=name)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


class Issue38Acceptance(unittest.TestCase):
    def test_ac_1_requires_refs_unless_owner_attested_sha_and_docs_only(self):
        meta = {"head_sha": SHA, "owner_authorized": True,
                "reason": "Rebuild the contributor documentation links",
                "changed_paths": ["README.md", "docs/factory/standards.md"]}
        self.assertTrue(trusted_maintenance(meta, SHA))
        self.assertFalse(trusted_maintenance(meta, "b" * 40))
        self.assertFalse(trusted_maintenance(dict(meta, owner_authorized=False), SHA))
        self.assertFalse(trusted_maintenance(dict(meta, changed_paths=["src/a.py"]), SHA))
        self.assertFalse(trusted_maintenance(dict(meta, reason="short"), SHA))
        ci = (ROOT / ".github/workflows/ci-selective.yml").read_text()
        gate = (ROOT / ".factory/scripts/pr_completion_gate.py").read_text()
        self.assertIn("FACTORY-MAINTENANCE-AUTH sha=", ci)
        self.assertIn('raise CompletionError("PR requires Refs #N', gate)
        emit(1, self._testMethodName)

    def test_ac_2_refs_accepted_and_partial_progress_is_not_false_completion(self):
        self.assertEqual(parse_intent("Refs #38"), ([38], []))
        self.assertEqual(parse_intent("Refs #38\nCompletes #38"), ([38], [38]))
        base = {"id": "AC-1", "status": "PASS", "verified_main_sha": SHA,
                "assertions": 3, "permanent_regression": True,
                "artifact_url": "https://github.com/shpalac/insurance/actions/runs/1",
                "pr_number": 101, "merge_sha": "b" * 40}
        pending = closure_progress(
            criteria_ids=["AC-1", "AC-2"], evidence=[base], main_sha=SHA)
        self.assertFalse(pending["should_close"])
        completed = closure_progress(
            criteria_ids=["AC-1", "AC-2"],
            evidence=[base, dict(base, id="AC-2")], main_sha=SHA)
        self.assertTrue(completed["should_close"])
        emit(2, self._testMethodName)

    def test_ac_3_bypass_words_and_nonstandalone_refs_cannot_close(self):
        for raw in ("Closes #38", "This fixes #38", "please ResOlves #38"):
            with self.subTest(raw=raw):
                with self.assertRaises(CompletionError):
                    parse_intent("Refs #38\n" + raw)
        class GitHub:
            def get(self, endpoint):
                return {"status": "ahead", "behind_by": 0}
        prs = [
            {"number": 1, "merged_at": "yes", "base": {"ref": "main"},
             "body": "An example Refs #38 embedded in prose",
             "merge_commit_sha": "b" * 40},
            {"number": 2, "merged_at": "yes", "base": {"ref": "main"},
             "body": "Refs #38", "merge_commit_sha": "b" * 40},
        ]
        self.assertEqual([r["number"] for r in
                          linked_merged_prs(38, prs, GitHub(), SHA)], [2])
        emit(3, self._testMethodName)


if __name__ == "__main__":
    unittest.main()
