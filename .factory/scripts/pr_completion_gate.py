#!/usr/bin/env python3
"""Fail-closed PR completion preflight. A merge alone is NOT acceptance proof.

Every linked PR uses "Refs #N". When all acceptance targets for an Issue
are registered, CI automatically runs *all* of them at the PR head even without
an explicit completion marker; an incomplete result blocks the merge. When
targets are not yet registered, multi-PR issues remain partial and mergeable
(subject to the other CI gates), while single-PR issues fail closed.
"Completes #N" is accepted for compatibility but is never required for automatic
post-merge closure. The separate trusted-main audit is authoritative.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

from run_acceptance_manifest import AcceptanceError, load_targets, run_criteria
from acceptance_discovery import DiscoveryError, available_criteria
from validate_issue_manifest import extract_manifest, validate_body

ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r"^[0-9a-f]{40}$")
REF = re.compile(r"(?im)^\s*Refs\s+#([1-9][0-9]*)\s*$")
COMPLETES = re.compile(r"(?im)^\s*Completes\s+#([1-9][0-9]*)\s*$")
NATIVE_CLOSE = re.compile(
    r"(?im)\b(?:Close[sd]?|Fix(?:e[sd])?|Resolve[sd]?)\s+#([1-9][0-9]*)\b"
)
MAX_COMPLETES = 10

MAINTENANCE_PATHS = frozenset(("README.md", "CONTRIBUTING.md", "LICENSE"))


def trusted_maintenance(meta: dict | None, head_sha: str) -> bool:
    """A separate token-scoped GitHub API step attests a SHA-bound owner approval.

    A candidate PR body, author/actor field or label alone never grants this.
    """
    if not isinstance(meta, dict) or meta.get("head_sha") != head_sha:
        return False
    reason = meta.get("reason")
    files = meta.get("changed_paths")
    return (
        meta.get("owner_authorized") is True
        and isinstance(reason, str) and 12 <= len(reason) <= 300
        and isinstance(files, list) and 0 < len(files) < 100
        and all(isinstance(p, str) and
                (p in MAINTENANCE_PATHS or p.startswith("docs/"))
                and ".." not in p.split("/") for p in files)
    )



class CompletionError(ValueError):
    pass


def parse_intent(body: str) -> tuple[list[int], list[int]]:
    """Only explicit standalone PR-body declarations carry closure intent."""
    if not isinstance(body, str):
        raise CompletionError("PR description must be text")
    if NATIVE_CLOSE.search(body):
        raise CompletionError(
            "Native Closes/Fixes/Resolves bypass audited closure; use Refs and Completes"
        )
    refs = [int(value) for value in REF.findall(body)]
    completes = [int(value) for value in COMPLETES.findall(body)]
    if len(refs) != len(set(refs)) or len(completes) != len(set(completes)):
        raise CompletionError("Duplicate Issue reference or completion declaration")
    if len(completes) > MAX_COMPLETES:
        raise CompletionError("Too many completion declarations")
    if not set(completes).issubset(refs):
        raise CompletionError("Every Completes #N must also have Refs #N")
    return refs, completes


def preflight(
    body: str, *, head_sha: str, fetch_issue, root: Path = ROOT,
    run=run_criteria,
) -> list[dict]:
    """Evaluate complete-issue claims against every acceptance criterion."""
    if not isinstance(head_sha, str) or not SHA.fullmatch(head_sha):
        raise CompletionError("Missing immutable PR head SHA")
    refs, completes = parse_intent(body)
    # The trusted registry is repository-owned; the public Issue cannot
    # supply shell commands or claim that an acceptance test exists.
    targets = load_targets(root)
    reports = []
    for number in refs:
        issue = fetch_issue(number)
        if (not isinstance(issue, dict) or issue.get("number") != number
                or issue.get("state") != "open" or "pull_request" in issue):
            raise CompletionError(f"Linked Issue #{number} is missing or not open")
        issue_body = issue.get("body") or ""
        errors = validate_body(issue_body, root=root, expected_issue_id=number)
        if errors:
            raise CompletionError(
                f"Issue #{number}: invalid acceptance specification: " + "; ".join(errors)
            )
        manifest = extract_manifest(issue_body)
        expected = [ac["id"] for ac in manifest["acceptance_criteria"]]
        try:
            coverage = available_criteria(root, number, expected, targets)
        except DiscoveryError as exc:
            raise CompletionError(
                f"Issue #{number}: invalid co-shipped acceptance: {exc}"
            ) from exc
        registered = len(coverage) == len(expected)
        if not registered and number not in completes:
            if not manifest["dependencies"]["multi_pr_allowed"]:
                raise CompletionError(
                    f"Issue #{number} is single-PR: all acceptance targets "
                    "must be implemented and verified before merging"
                )
            # Multi-PR work may land incrementally. But tests already shipped
            # with the implementation must actually pass at the candidate SHA.
            # Legacy incomplete registry entries are skipped during migration.
            partial = {
                criterion for criterion in expected
                if coverage.get(criterion) == "co-shipped"
            }
            if partial:
                try:
                    linux_partial = {ac for ac in partial if
                        next(row["runner_os"] for row in manifest["acceptance_criteria"]
                             if row["id"] == ac) == "ubuntu-latest"}
                    partial_rows = (run(
                        issue_body, issue_id=number, head_sha=head_sha,
                        root=root, criteria_subset=linux_partial,
                    ) if linux_partial else [])
                except (AcceptanceError, OSError) as exc:
                    raise CompletionError(
                        f"Issue #{number}: partial acceptance failed "
                        f"({type(exc).__name__})"
                    ) from exc
                if ([row.get("id") for row in partial_rows]
                        != [ac for ac in expected if ac in linux_partial]
                        or any(
                            row.get("status") != "PASS"
                            or row.get("head_sha") != head_sha
                            or row.get("assertions", 0) < 1
                            or row.get("testcases", 0) < 1
                            for row in partial_rows
                        )):
                    raise CompletionError(
                        f"Issue #{number}: incomplete or failed partial evidence"
                    )
                reports.append({
                    "issue": number, "partial_criteria": sorted(partial),
                    "head_sha": head_sha, "complete": False,
                })
            # Post-merge verification intentionally keeps the parent open.
            continue

        # When the registry becomes complete, there is no manual "finishing
        # PR" action. Every linked PR automatically proves all criteria.
        # Non-Linux ACs are enforced by mandatory hosted jobs and the aggregate
        # gate, never by pretending Ubuntu has executed them.
        linux = {ac["id"] for ac in manifest["acceptance_criteria"]
                 if ac["runner_os"] == "ubuntu-latest"}
        try:
            rows = (run(issue_body, issue_id=number, head_sha=head_sha,
                        root=root, criteria_subset=linux) if linux else [])
        except (AcceptanceError, OSError) as exc:
            raise CompletionError(
                f"Issue #{number}: trusted acceptance failed ({type(exc).__name__})"
            ) from exc
        if [r.get("id") for r in rows] != [ac for ac in expected if ac in linux]:
            raise CompletionError(f"Issue #{number}: incomplete criterion coverage")
        if any(
            row.get("status") != "PASS" or row.get("head_sha") != head_sha
            or type(row.get("assertions")) is not int or row["assertions"] < 1
            or type(row.get("testcases")) is not int or row["testcases"] < 1
            for row in rows
        ):
            raise CompletionError(f"Issue #{number}: insufficient test evidence")
        reports.append({"issue": number, "criteria": expected, "head_sha": head_sha})
    return reports


def supplied_issue(issues: dict, number: int) -> dict:
    """Consume metadata captured by a separate read-only step."""
    entry = issues.get(str(number))
    if not isinstance(entry, dict) or entry.get("number") != number:
        raise CompletionError(f"Trusted Issue payload absent for #{number}")
    return entry


def main() -> int:
    event_name = os.getenv("GITHUB_EVENT_NAME")
    if event_name != "pull_request":
        print("Completion preflight: no PR closure intent on main push")
        return 0
    event_path = os.getenv("GITHUB_EVENT_PATH", "")
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        pr = event["pull_request"]
        body = pr.get("body") or ""
        head = pr["head"]["sha"]
        refs, completes = parse_intent(body)
        source = os.getenv("COMPLETION_ISSUES_PATH", "")
        if not source:
            raise CompletionError("Missing trusted Issue payload file")
        issues = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(issues, dict):
            raise CompletionError("Malformed Issue payload")
        if not refs:
            if not trusted_maintenance(issues.get("_maintenance"), head):
                raise CompletionError("PR requires Refs #N or SHA-bound owner-approved docs-only maintenance")
            print("PASS: owner-approved docs-only maintenance exemption")
            return 0
        reports = preflight(
            body, head_sha=head, root=ROOT,
            fetch_issue=lambda n: supplied_issue(issues, n),
        )
        summary = os.getenv("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write("### Verified PR completion promises\n")
                for report in reports:
                    ids = report.get("criteria") or report.get("partial_criteria", [])
                    stage = "complete" if "criteria" in report else "partial"
                    handle.write(
                        f"- Issue #{report['issue']}: {stage}, "
                        f"{len(ids)} verified acceptance criteria at `{head}`\\n"
                    )
        print(f"Automatically verified {len(reports)} fully accepted issue(s) at {head}")
        return 0
    except (CompletionError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: completion gate blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
