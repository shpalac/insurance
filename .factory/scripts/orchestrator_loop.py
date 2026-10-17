#!/usr/bin/env python3
"""Read-only, scheduled dispatcher diagnostics; never spawn agents implicitly."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REFS = re.compile(r"(?m)^\s*Refs #([1-9][0-9]*)\s*$")
SHA = re.compile(r"^[a-f0-9]{40}$")


def prioritize(items: list[dict]) -> list[dict]:
    """Give regressions and failed PRs precedence over independent ready work."""
    scores = {
        "main-regression": 0,
        "merge-blocker": 1,
        "failing-pr": 2,
        "review-pr": 3,
        "ready-issue": 4,
        "triage-issue": 5,
    }
    return sorted(items, key=lambda item: (
        scores.get(item.get("kind"), 100),
        item.get("number", 0),
    ))


def plan_next(
    items: list[dict], leases: dict, *, now: datetime, max_concurrent: int
) -> dict | None:
    """Select one ready work item, prioritizing failures and merge blockers.

    A closed Issue is absent from the open queue, so the same planner naturally
    advances to the next eligible task after completion. Existing active leases
    are never claimed a second time.
    """
    if (now.tzinfo is None or type(max_concurrent) is not int
            or not 1 <= max_concurrent <= 32 or not isinstance(leases, dict)):
        raise ValueError("Invalid queue planning context")
    active = {
        number: lease for number, lease in leases.items()
        if lease.expires_at > now
        and lease.phase not in {"blocked", "completed", "cancelled"}
    }
    roles = {
        "main-regression": "ci-engineer",
        "merge-blocker": "integrator",
        "failing-pr": "ci-engineer",
        "ready-issue": "planner",
    }
    open_issue_ids = {
        item.get("number") for item in items
        if not item.get("is_pr") and type(item.get("number")) is int
    }
    ordered = prioritize(items)
    # Re-deliver the same active lease/checkpoint first. The backend's stable
    # idempotency key must resume the existing worker, never create a duplicate.
    for item in ordered:
        kind = item.get("kind")
        issue = item.get("linked_issue")
        if (kind not in roles or type(issue) is not int or issue < 1
                or issue not in active):
            continue
        lease = active[issue]
        if lease.phase not in {"claimed", "repairing"}:
            continue
        return {
            "issue": issue, "source_number": item.get("number"),
            "kind": kind, "role": lease.role,
            "resume": True, "reason": "resume_durable_lease",
        }
    if len(active) >= max_concurrent:
        return None
    for item in ordered:
        kind = item.get("kind")
        if kind not in roles:
            continue
        issue = item.get("linked_issue")
        if type(issue) is not int or issue < 1 or issue not in open_issue_ids or issue in active:
            continue
        return {
            "issue": issue,
            "source_number": item.get("number"),
            "kind": kind,
            "role": roles[kind],
            "resume": False,
            "reason": "priority_queue_eligible",
        }
    return None


def _get_json(repo: str, token: str, path: str) -> dict | list:
    if not path.startswith("/") or "://" in path:
        raise ValueError("Invalid GitHub API path")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def classify_pull_request(pr: dict, checks: list[dict], labels: set[str]) -> str:
    """Classify from current remote checks and merge state, not labels alone."""
    if "priority:p0-regression" in labels:
        return "main-regression"
    if any(
        check.get("status") == "completed"
        and check.get("conclusion") == "failure"
        for check in checks
    ) or "status:ci-failing" in labels:
        return "failing-pr"
    if ("status:blocked" in labels
            or pr.get("mergeable_state") in {"dirty", "blocked", "behind"}):
        return "merge-blocker"
    if "status:changes-requested" in labels:
        return "failing-pr"
    return "review-pr"


def inspect_open(repo: str, token: str) -> list[dict]:
    """Fetch bounded GitHub issue/PR metadata, never execute their text."""
    if not REPOSITORY.fullmatch(repo) or not token:
        raise ValueError("Valid repository and read-only token required")
    items = []
    for page in range(1, 11):
        url = (
            f"https://api.github.com/repos/{repo}/issues"
            f"?state=open&per_page=100&page={page}"
        )
        issues = _get_json(repo, token,
                           f"/issues?state=open&per_page=100&page={page}")
        if not issues:
            break
        if page == 10 and len(issues) == 100:
            raise ValueError("Issue queue exceeds the bounded 1000-item reconciliation window")
        for issue in issues:
            labels = {item.get("name", "") for item in issue.get("labels", [])}
            is_pr = bool(issue.get("pull_request"))
            kind = (
                "review-pr" if is_pr
                else "ready-issue" if "status:ready" in labels
                else "triage-issue"
            )
            body = issue.get("body") or ""
            matches = REFS.findall(body)
            linked_issue = int(matches[0]) if len(matches) == 1 else None
            if is_pr:
                pull = _get_json(repo, token, f"/pulls/{issue['number']}")
                head = pull.get("head") or {}
                head_repo = head.get("repo") or {}
                head_sha = head.get("sha") or ""
                if (head_repo.get("full_name", "").lower() == repo.lower()
                        and SHA.fullmatch(head_sha)):
                    check_data = _get_json(
                        repo, token, f"/commits/{head_sha}/check-runs?per_page=100"
                    )
                    checks = check_data.get("check_runs", [])
                    if (type(check_data.get("total_count")) is not int
                            or check_data["total_count"] > 100
                            or not isinstance(checks, list)):
                        raise ValueError("PR check-run evidence is truncated or invalid")
                    kind = classify_pull_request(pull, checks, labels)
                else:
                    # Fork code is never sent to an external agent by this controller.
                    kind = "review-pr"
            elif "priority:p0-regression" in labels:
                kind = "main-regression"
            items.append({
                "number": issue["number"], "kind": kind,
                "url": issue.get("html_url", ""),
                "is_pr": is_pr,
                "linked_issue": linked_issue if is_pr else issue["number"],
                "labels": sorted(labels),
                "updated_at": issue.get("updated_at", ""),
            })
    return prioritize(items)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args(argv)
    config = yaml.safe_load(
        (ROOT / ".factory/config.yaml").read_text(encoding="utf-8")
    )
    if config["orchestration"]["enabled"]:
        print("NOTE: dispatcher is in diagnostic mode even with enabled=true.")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    items = inspect_open(repo, token)
    plan = plan_next(
        items, {}, now=datetime.now(timezone.utc),
        max_concurrent=config["orchestration"]["max_concurrent_agents"],
    )
    print(json.dumps({
        "mode": "read-only",
        "autonomous_dispatch": False,
        "next_candidate": plan,
        "queue": items[:50],
        "backlog_total": len(items),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
