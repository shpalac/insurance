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

    effective = fetch("/rules/branches/main")
    legacy = fetch("/branches/main/protection")
    errors = audit(effective, legacy)
    if errors:
        for item in errors:
            print("ERROR:", item, file=sys.stderr)
        return 1
    print("PASS: main has enforced required CI checks under active GitHub rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
