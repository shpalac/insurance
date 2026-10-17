#!/usr/bin/env python3
"""Fail-closed aggregate status gate for dependency-aware CI workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

SHA = re.compile(r"^[a-f0-9]{40}$")
JOBS = ("scanner", "factory", "docs", "macos", "windows")


def gate_errors(manifest: dict, head_sha: str, statuses: dict) -> list[str]:
    errors = []
    if not SHA.fullmatch(head_sha):
        return ["Missing verified head SHA"]
    if not isinstance(manifest, dict):
        return ["Missing or invalid impact manifest"]
    digest = manifest.get("integrity_sha256")
    body = {key: value for key, value in manifest.items() if key != "integrity_sha256"}
    expected_digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if digest != expected_digest:
        errors.append("Impact manifest digest mismatch")
    if manifest.get("head_sha") != head_sha:
        errors.append("Impact manifest head SHA mismatch")
    selected = manifest.get("selected_jobs")
    if not isinstance(selected, dict) or set(selected) != set(JOBS):
        errors.append("Impact selected_jobs missing or incomplete")
        selected = {}
    if not manifest.get("changed_paths"):
        errors.append("No changed files in impact manifest")
    for name in JOBS:
        flag = selected.get(name)
        if type(flag) is not bool:
            errors.append(f"Selection flag for {name} must be boolean")
        elif flag and statuses.get(name) != "success":
            errors.append(f"Selected {name} job did not succeed")
    for baseline in ("impact", "policy", "issue_completion",
                     "acceptance_macos", "acceptance_windows"):
        if statuses.get(baseline) != "success":
            errors.append(f"Mandatory {baseline} job did not succeed")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", default=os.environ.get("HEAD_SHA", ""))
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(os.environ.get("IMPACT_MANIFEST", "null"))
    except ValueError:
        manifest = None
    statuses = {
        name: os.environ.get(f"RESULT_{name.upper()}", "").lower()
        for name in (*JOBS, "impact", "policy", "issue_completion",
                     "acceptance_macos", "acceptance_windows")
    }
    errors = gate_errors(manifest, args.head, statuses)
    for issue in errors:
        print(f"ERROR: {issue}", file=sys.stderr)
    if errors:
        return 1
    print("PASS: all selected CI jobs and mandatory baseline succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
