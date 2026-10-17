#!/usr/bin/env python3
"""Read-only, scheduled dispatcher diagnostics; never spawn agents implicitly."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


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
        request = urllib.request.Request(
            url, headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            }
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            issues = json.load(response)
        if not issues:
            break
        for issue in issues:
            labels = {item.get("name", "") for item in issue.get("labels", [])}
            is_pr = bool(issue.get("pull_request"))
            kind = (
                "review-pr" if is_pr
                else "ready-issue" if "status:ready" in labels
                else "triage-issue"
            )
            if "priority:p0-regression" in labels:
                kind = "main-regression"
            if is_pr and "status:blocked" in labels:
                kind = "merge-blocker"
            elif is_pr and ("status:ci-failing" in labels
                            or "status:changes-requested" in labels):
                kind = "failing-pr"
            items.append({
                "number": issue["number"], "kind": kind,
                "url": issue.get("html_url", ""),
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
    print(json.dumps({
        "mode": "read-only",
        "autonomous_dispatch": False,
        "queue": items[:50],
        "backlog_total": len(items),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
