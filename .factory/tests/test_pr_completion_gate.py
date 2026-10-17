"""Regression checks for CI-only merge-to-closure admission."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))

from pr_completion_gate import (  # noqa: E402
    CompletionError, parse_intent, preflight, supplied_issue, main as gate_main,
)

SHA = "a" * 40
BODY = (ROOT / ".factory/examples/valid-issue.md").read_text(encoding="utf-8")


def issue(number=142, *, body=BODY):
    return {"number": number, "state": "open", "body": body}


def run_acceptance(_body, *, issue_id, head_sha, root):
    if issue_id != 142 or head_sha != SHA:
        raise AssertionError("Incorrect acceptance target")
    return [
        {"id": "AC-1", "status": "PASS", "head_sha": SHA, "testcases": 2,
         "assertions": 3},
        {"id": "AC-2", "status": "PASS", "head_sha": SHA, "testcases": 1,
         "assertions": 1},
    ]


class CompletionGateTests(unittest.TestCase):
    def test_partial_refs_have_no_closure_promise(self):
        self.assertEqual(parse_intent("Refs #142"), ([142], []))
        self.assertEqual(preflight("Refs #142", head_sha=SHA,
                                   fetch_issue=lambda _: None), [])

    def test_complete_issue_requires_explicit_declaration(self):
        self.assertEqual(parse_intent("Refs #142\nCompletes #142"), ([142], [142]))
        results = preflight("Refs #142\nCompletes #142", head_sha=SHA,
                            fetch_issue=issue, run=run_acceptance)
        self.assertEqual(results, [{
            "issue": 142, "criteria": ["AC-1", "AC-2"], "head_sha": SHA,
        }])

    def test_future_issue_form_self_id_closes_without_manual_number_edit(self):
        body = BODY.replace("issue_id: 142", 'issue_id: "self"')
        result = preflight(
            "Refs #142\nCompletes #142",
            head_sha=SHA,
            fetch_issue=lambda n: issue(body=body),
            run=run_acceptance,
        )
        self.assertEqual(result[0]["criteria"], ["AC-1", "AC-2"])

    def test_native_github_close_keywords_rejected(self):
        for word in ("Closes", "Fixes", "Resolves", "Close", "Fix"):
            with self.subTest(word=word):
                with self.assertRaises(CompletionError):
                    parse_intent("Refs #142\n" + word + " #142")

    def test_missing_refs_declaration_blocks(self):
        with self.assertRaises(CompletionError):
            parse_intent("Completes #142")

    def test_duplicate_or_overbudget_intents_block(self):
        for value in ("Refs #142\nRefs #142", "Refs #142\nCompletes #142\nCompletes #142"):
            with self.assertRaises(CompletionError):
                parse_intent(value)
        with self.assertRaises(CompletionError):
            parse_intent(
                "\n".join(f"Refs #{n}\nCompletes #{n}" for n in range(1, 13))
            )

    def test_missing_issue_and_closed_issue_block(self):
        with self.assertRaises(CompletionError):
            preflight("Refs #142\nCompletes #142", head_sha=SHA,
                      fetch_issue=lambda n: {})
        with self.assertRaises(CompletionError):
            preflight("Refs #142\nCompletes #142", head_sha=SHA,
                      fetch_issue=lambda n: dict(issue(), state="closed"))

    def test_manifest_issue_id_mismatch_fails(self):
        with self.assertRaises(CompletionError):
            preflight("Refs #142\nCompletes #142", head_sha=SHA,
                      fetch_issue=lambda n: dict(issue(), body=BODY.replace(
                          "issue_id: 142", "issue_id: 141")), run=run_acceptance)

    def test_missing_acceptance_manifest_fails_closed(self):
        with self.assertRaises(CompletionError):
            preflight("Refs #142\nCompletes #142", head_sha=SHA,
                      fetch_issue=lambda n: dict(issue(), body="plain English"))

    def test_incomplete_acceptance_subset_fails(self):
        with self.assertRaises(CompletionError):
            preflight("Refs #142\nCompletes #142", head_sha=SHA,
                      fetch_issue=issue,
                      run=lambda *a, **k: run_acceptance(*a, **k)[:1])

    def test_stale_head_or_skipped_test_blocks(self):
        def stale(*args, **kwargs):
            rows = run_acceptance(*args, **kwargs)
            rows[1]["head_sha"] = "b" * 40
            return rows
        with self.assertRaises(CompletionError):
            preflight("Refs #142\nCompletes #142", head_sha=SHA,
                      fetch_issue=issue, run=stale)

        def skipped(*args, **kwargs):
            rows = run_acceptance(*args, **kwargs)
            rows[0]["testcases"] = 0
            return rows
        with self.assertRaises(CompletionError):
            preflight("Refs #142\nCompletes #142", head_sha=SHA,
                      fetch_issue=issue, run=skipped)

    def test_zero_assertion_blocks(self):
        def empty(*args, **kwargs):
            rows = run_acceptance(*args, **kwargs)
            rows[1]["assertions"] = 0
            return rows
        with self.assertRaises(CompletionError):
            preflight("Refs #142\nCompletes #142", head_sha=SHA,
                      fetch_issue=issue, run=empty)

    def test_no_current_head_blocks(self):
        with self.assertRaises(CompletionError):
            preflight("Refs #142\nCompletes #142", head_sha="main",
                      fetch_issue=issue)

    def test_non_ubuntu_acceptance_requires_additional_runner(self):
        other = BODY.replace("runner_os: ubuntu-latest",
                             "runner_os: macos-latest", 1)
        with self.assertRaises(CompletionError):
            preflight("Refs #142\nCompletes #142", head_sha=SHA,
                      fetch_issue=lambda n: issue(body=other), run=run_acceptance)

    def test_token_free_issue_payload_requires_matching_number(self):
        self.assertEqual(
            supplied_issue({"142": issue()}, 142)["number"], 142
        )
        for payload in ({}, {"142": {"number": 143}}, {"142": "untrusted"}):
            with self.assertRaises(CompletionError):
                supplied_issue(payload, 142)

    def test_completion_gate_cannot_fall_back_to_api_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({
                "pull_request": {
                    "body": "Refs #142\\nCompletes #142",
                    "head": {"sha": SHA},
                }
            }))
            env = {
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event),
                "COMPLETION_ISSUES_PATH": str(Path(tmp) / "missing.json"),
                "GH_TOKEN": "test-token-that-must-not-be-used",
            }
            with mock.patch.dict(os.environ, env):
                self.assertEqual(gate_main(), 1)

    def test_push_to_main_is_noop(self):
        with mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push"}):
            self.assertEqual(gate_main(), 0)

    def test_pr_event_with_native_bypass_fails_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({
                "pull_request": {
                    "body": "Refs #142\nCloses #142",
                    "head": {"sha": SHA},
                }
            }))
            env = {
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event),
            }
            with mock.patch.dict(os.environ, env):
                self.assertEqual(gate_main(), 1)


if __name__ == "__main__":
    unittest.main()
