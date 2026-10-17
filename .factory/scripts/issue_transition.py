#!/usr/bin/env python3
"""Evaluate Issue validation from trusted code; never run Issue-authored commands."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

from validate_issue_manifest import validate_body

ROOT = Path(__file__).resolve().parents[2]
READY = "status:ready"
TRIAGE = "status:triage"
REPORT_MARKER = "<!-- FACTORY_ISSUE_VALIDATION_V1 -->"


def evaluate(event: dict, allowed_logins: set[str]) -> dict:
    """Return a fail-closed, deterministic decision for an Issue webhook."""
    issue = event.get("issue") or {}
    number = issue.get("number")
    sender = (event.get("sender") or {}).get("login", "")
    action = event.get("action", "")
    errors = []
    if not isinstance(number, int) or number < 1:
        errors.append("Missing valid Issue number")
    if action not in {"opened", "edited", "reopened", "labeled"}:
        errors.append("Unrecognized Issue event action")
    if sender not in allowed_logins or not allowed_logins:
        errors.append("Sender is not an approved Issue Validator")
    if issue.get("pull_request"):
        errors.append("Pull requests cannot become executable Issues")
    if not errors:
        errors.extend(validate_body(
            issue.get("body") or "", expected_issue_id=number
        ))
    return {
        "issue_number": number,
        "ready": not errors,
        "diagnostics": errors,
        "actor": sender,
        "action": action,
    }


def desired_labels(current: set[str], *, ready: bool) -> tuple[set[str], set[str]]:
    """Calculate the minimal idempotent label delta."""
    target = READY if ready else TRIAGE
    opposite = TRIAGE if ready else READY
    add = {target} - current
    remove = {opposite} & current
    return add, remove


def _request(url: str, token: str, method: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url, data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        value = response.read()
    return json.loads(value) if value else None


def update_report(
    decision: dict, *, repository: str, token: str
) -> None:
    """Maintain one sticky, sanitized validation comment per issue."""
    owner, name = repository.split("/", 1)
    number = decision["issue_number"]
    root = (
        f"https://api.github.com/repos/"
        f"{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(name, safe='')}"
    )
    diagnostics = [
        str(message).replace("\\n", " ").replace("\x60", "'")[:400]
        for message in decision["diagnostics"][:20]
    ]
    result = "READY" if decision["ready"] else "TRIAGE — REJECTED"
    report = (
        f"{REPORT_MARKER}\\n"
        f"### Factory Issue validation: {result}\\n"
        + ("\\n".join(f"- {message}" for message in diagnostics)
           if diagnostics else "All static checks passed.")
        + "\\n\\nNo Issue-provided commands were executed."
    )
    # Enumerate pages so repeated webhook deliveries cannot create duplicates.
    page = 1
    previous = None
    while page <= 50:
        comments = _request(
            f"{root}/issues/{number}/comments?per_page=100&page={page}",
            token, "GET"
        )
        if not comments:
            break
        for comment in comments:
            if (REPORT_MARKER in comment.get("body", "")
                    and comment.get("user", {}).get("type") == "Bot"):
                previous = comment
                break
        if previous:
            break
        page += 1
    if previous is not None:
        if previous["body"] != report:
            _request(
                f"{root}/issues/comments/{previous['id']}",
                token, "PATCH", {"body": report}
            )
    else:
        _request(
            f"{root}/issues/{number}/comments",
            token, "POST", {"body": report}
        )


def apply_decision(decision: dict, *, repository: str, token: str) -> dict:
    """Idempotently update only ready/triage labels from authorized workflow."""
    if not token or not repository or "/" not in repository:
        raise ValueError("Missing repository or token")
    number = decision["issue_number"]
    if not isinstance(number, int) or number < 1:
        raise ValueError("Issue number not validated")
    owner, name = repository.split("/", 1)
    base = (
        f"https://api.github.com/repos/"
        f"{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(name, safe='')}/issues/{number}"
    )
    issue = _request(base, token, "GET")
    current = {label["name"] for label in issue.get("labels", [])}
    update_report(decision, repository=repository, token=token)
    add, remove = desired_labels(current, ready=decision["ready"])
    for label in sorted(add):
        _request(f"{base}/labels", token, "POST", {"labels": [label]})
    for label in sorted(remove):
        try:
            _request(
                f"{base}/labels/{urllib.parse.quote(label, safe='')}",
                token,
                "DELETE",
            )
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
    return {"added": sorted(add), "removed": sorted(remove)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    event = json.loads(args.event.read_text(encoding="utf-8"))
    config = yaml.safe_load(
        (ROOT / ".factory/config.yaml").read_text(encoding="utf-8")
    )
    allowed_logins = set(
        config["orchestration"].get("approved_agent_logins", [])
    )
    decision = evaluate(event, allowed_logins)
    print(json.dumps(decision, sort_keys=True))
    if args.apply:
        apply_decision(
            decision,
            repository=os.environ.get("GITHUB_REPOSITORY", ""),
            token=os.environ.get("GITHUB_TOKEN", ""),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
