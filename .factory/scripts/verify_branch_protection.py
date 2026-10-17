#!/usr/bin/env python3
"""Audit GitHub's active main-branch rules without modifying protection.

A workflow file merely declaring required checks is not branch protection.
Only the effective GitHub rules API can establish merge enforcement.
"""
from __future__ import annotations
import json
import os
import re
import sys
from urllib import request, error

REQUIRED = frozenset((
    "unit-tests", "factory-bootstrap-gate", "factory-gate-preflight",
))


def validated_rules(rules: list[dict]) -> list[str]:
    if not isinstance(rules, list):
        return ["GitHub did not provide effective branch rules"]
    contexts = set()
    for rule in rules:
        if rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters") or {}
        for entry in params.get("required_status_checks", []):
            if isinstance(entry, dict) and isinstance(entry.get("context"), str):
                contexts.add(entry["context"])
    return [
        f"Missing enforced main check: {name}"
        for name in sorted(REQUIRED - contexts)
    ]


def validated_legacy_protection(protection: dict) -> list[str]:
    if not isinstance(protection, dict):
        return ["GitHub branch protection is unavailable"]
    checks = protection.get("required_status_checks") or {}
    contexts = set(checks.get("contexts") or [])
    contexts.update(
        item.get("context") for item in checks.get("checks", [])
        if isinstance(item, dict)
    )
    return [
        f"Missing enforced main check: {name}"
        for name in sorted(REQUIRED - contexts)
    ]


def audit(rules: list[dict] | None, protection: dict | None) -> list[str]:
    # Either a modern effective ruleset OR classic branch protection must
    # enforce all three checks; do not union two incomplete policies.
    if rules is not None and not validated_rules(rules):
        return []
    if protection is not None and not validated_legacy_protection(protection):
        return []
    return ["main does not independently enforce all required CI checks"]


def branch_protected(branch: dict | None) -> bool:
    """The branch itself must be protected, not merely advertise contexts."""
    return isinstance(branch, dict) and branch.get("protected") is True


def remediation(repo: str, errors: list[str], *, protected: bool) -> str:
    """Human-readable blocked owner action with no false green claims."""
    status = "PASS" if not errors and protected else "BLOCKED: OWNER ACTION REQUIRED"
    lines = [
        f"### Factory main branch enforcement: {status}",
        f"Repository: {repo}",
        "Required: " + ", ".join(sorted(REQUIRED)),
    ]
    if not protected:
        lines.append("The GitHub main branch is NOT protected.")
    lines.extend("Failure: " + line for line in errors)
    if errors or not protected:
        lines.extend([
            f"Configure actual enforcement at https://github.com/{repo}/settings/rules",
            "Choose target main; require all three named successful status checks.",
            "Independent reviewer approval remains optional; do not bypass CI.",
            "Rerun Factory branch protection audit to capture authoritative evidence.",
        ])
    return "\\n".join(lines) + "\\n"


def main() -> int:
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token = os.getenv("GH_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
        print("ERROR: missing repository or GitHub read token", file=sys.stderr)
        return 1
    base = f"https://api.github.com/repos/{repo}"
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    def fetch(path):
        try:
            req = request.Request(base + path, headers=headers)
            with request.urlopen(req, timeout=20) as response:
                return json.load(response)
        except (error.HTTPError, error.URLError):
            return None

    branch = fetch("/branches/main")
    effective = fetch("/rules/branches/main")
    legacy = fetch("/branches/main/protection")
    errors = audit(effective, legacy)
    if not branch_protected(branch):
        errors.append("main branch API says protected=false or is unavailable")
    report = remediation(repo, errors, protected=branch_protected(branch))
    print(report)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write(report)
    os.makedirs("reports", exist_ok=True)
    with open("reports/main-branch-enforcement.json", "w", encoding="utf-8") as out:
        json.dump({"repo": repo, "protected": branch_protected(branch),
                   "required_checks": sorted(REQUIRED), "errors": errors}, out,
                  sort_keys=True, indent=2)
    if errors:
        for item in errors:
            print("ERROR:", item, file=sys.stderr)
        return 1
    print("PASS: main has enforced required CI checks under active GitHub rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
