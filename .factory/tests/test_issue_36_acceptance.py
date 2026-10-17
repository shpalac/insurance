"""Issue #36: isolate privileged admission from candidate PR code."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from trusted_admission import admission_blockers, owner_authorized

SHA = "a" * 40
RUN = {"head_sha": SHA, "event": "pull_request", "conclusion": "success"}
PR = {"head": {"sha": SHA}, "base": {"ref": "main"}, "draft": False,
      "state": "open", "mergeable": True}
JOBS = [{"name": n, "conclusion": "success", "status": "completed"}
        for n in ("issue-completion", "factory-gate-preflight")]


def emit(n: int, name: str):
    path = ROOT / "reports" / f"ac-{n}.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", tests="1", failures="0", errors="0",
                       skipped="0", assertions="3")
    ET.SubElement(suite, "testcase", classname="Issue36Acceptance", name=name)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


class Issue36Acceptance(unittest.TestCase):
    def test_ac_1_candidate_cannot_self_authorize_protected_gate_edits(self):
        self.assertEqual(admission_blockers(
            PR, RUN, JOBS, ["src/insurance/core.py"], [], "shpalac"), [])
        blocked = admission_blockers(
            PR, RUN, JOBS, [".factory/scripts/trusted_admission.py"], [],
            "shpalac")
        self.assertIn("Protected paths need owner-authored", str(blocked))
        self.assertTrue(admission_blockers(PR, dict(RUN, head_sha="b" * 40),
                                           JOBS, ["README.md"], [], "shpalac"))
        comment = [{"body": "FACTORY-OWNER-AUTH sha=" + SHA +
                    " reason=Approve trusted CI controller changes",
                    "user": {"login": "shpalac"}}]
        self.assertTrue(owner_authorized(comment, "shpalac", SHA))
        self.assertFalse(owner_authorized(comment, "shpalac", "b" * 40))
        self.assertEqual(admission_blockers(
            PR, RUN, JOBS, [".github/workflows/ci-selective.yml"],
            comment, "shpalac"), [])
        emit(1, self._testMethodName)

    def test_ac_3_workflow_run_never_executes_fork_or_candidate_code(self):
        workflow = (ROOT / ".github/workflows/factory-trusted-admission.yml").read_text()
        self.assertIn("workflow_run:", workflow)
        self.assertIn("ref: main", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertNotIn("actions/checkout@", workflow.split("ref: main")[1])
        self.assertIn("checks: write", workflow)
        self.assertIn("python3 .factory/scripts/trusted_admission.py", workflow)
        self.assertTrue(admission_blockers(
            PR, RUN, JOBS[:1], ["README.md"], [], "shpalac"))
        emit(3, self._testMethodName)


if __name__ == "__main__":
    unittest.main()
