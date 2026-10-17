#!/usr/bin/env python3
"""Pure, fail-closed integration eligibility and post-merge closure audit.

This library does not merge PRs or write to GitHub. An authorized Integrator
must independently retrieve and verify GitHub evidence before acting.
"""

from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re

SHA = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_CHECKS = ("factory-gate", "acceptance-gate")


def assess_merge(
    pr: dict, *, required_checks: tuple[str, ...] = REQUIRED_CHECKS,
    protected_paths: tuple[str, ...] = (
        ".github/workflows/**", ".factory/**", "AGENTS.md", "SECURITY.md"
    ),
) -> list[str]:
    """Return all blockers for the exact PR head and independent review state."""
    blocked = []
    head = pr.get("head_sha")
    if not isinstance(head, str) or not SHA.fullmatch(head):
        return ["Invalid immutable PR head SHA"]
    if pr.get("base_branch") != "main":
        blocked.append("PR does not target main")
    if pr.get("draft"):
        blocked.append("Draft PR cannot merge")
    if pr.get("conflicted") is not False:
        blocked.append("Mergeability not proven conflict-free")
    if pr.get("hold") or "status:blocked" in pr.get("labels", []):
        blocked.append("PR is on hold")
    if pr.get("integrity_sha") != head:
        blocked.append("Impact evidence not pinned to current PR head")
    checks = pr.get("checks", {})
    for check in required_checks:
        report = checks.get(check, {})
        if report.get("head_sha") != head or report.get("conclusion") != "success":
            blocked.append(f"Missing successful {check} at current SHA")
    author = pr.get("author")
    reviewers = pr.get("reviews", [])
    valid_reviews = [
        review for review in reviewers
        if (review.get("verdict") == "APPROVE"
            and review.get("head_sha") == head
            and review.get("reviewer")
            and review.get("reviewer") != author
            and review.get("trusted_identity") is True)
    ]
    if not valid_reviews:
        blocked.append("Missing independent trusted approval of current head")
    if pr.get("unresolved_threads", 1) != 0:
        blocked.append("Unresolved review threads")
    paths = pr.get("changed_paths", [])
    if not isinstance(paths, list):
        blocked.append("Invalid changed path manifest")
        paths = []
    sensitive = [
        path for path in paths
        if isinstance(path, str)
        and any(fnmatchcase(path, pattern) for pattern in protected_paths)
    ]
    if sensitive and pr.get("maintainer_authorized") is not True:
        blocked.append("Protected paths lack maintainer authorization")
    if pr.get("scope_compliant") is not True:
        blocked.append("Issue path scope has not been verified")
    if pr.get("validated_issue") is not True:
        blocked.append("Linked executable Issue not validated")
    return blocked


def closure_progress(
    *, criteria_ids: list[str], evidence: list[dict],
    main_sha: str, issue_closed: bool = False
) -> dict:
    """Plan idempotent Issue closure only on verified main-branch evidence."""
    if not SHA.fullmatch(main_sha):
        raise ValueError("Invalid default-branch commit SHA")
    if not criteria_ids or len(criteria_ids) != len(set(criteria_ids)):
        raise ValueError("Missing or duplicate acceptance criteria")
    satisfied = {}
    merged_prs = set()
    for record in evidence:
        ac = record.get("id")
        sha = record.get("verified_main_sha")
        if ac not in criteria_ids or sha != main_sha:
            continue
        if (record.get("status") == "PASS"
                and isinstance(record.get("assertions"), int)
                and record["assertions"] > 0
                and record.get("permanent_regression") is True
                and record.get("artifact_url")
                and record.get("merge_sha")
                and isinstance(record.get("pr_number"), int)):
            satisfied[ac] = record
            merged_prs.add(record["pr_number"])
    missing = sorted(set(criteria_ids) - satisfied.keys())
    audit = {
        "schema_version": "1.0",
        "main_sha": main_sha,
        "verified_criteria": sorted(satisfied),
        "missing_criteria": missing,
        "completed": len(satisfied),
        "total": len(criteria_ids),
        "merged_prs": sorted(merged_prs),
        "evidence": [
            {
                "id": ac,
                "pr_number": satisfied[ac]["pr_number"],
                "merge_sha": satisfied[ac]["merge_sha"],
                "artifact_url": satisfied[ac]["artifact_url"],
            }
            for ac in sorted(satisfied)
        ],
        "should_close": not missing and not issue_closed,
        "already_closed": issue_closed,
    }
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-json", type=Path, required=True)
    args = parser.parse_args(argv)
    pr = json.loads(args.pr_json.read_text(encoding="utf-8"))
    errors = assess_merge(pr)
    print(json.dumps({"merge_allowed": not errors, "blockers": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
