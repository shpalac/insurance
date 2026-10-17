#!/usr/bin/env python3
"""Validate structured live-canary proof references; no synthetic pass is trusted.

This structural preflight is NOT a substitute for online GitHub run/commit
verification or independent review. It cannot activate the factory.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

SHA = re.compile(r"^[a-f0-9]{40}$")
DIGEST = re.compile(r"^[a-f0-9]{64}$")
STEPS = (
    "issue_created", "validated", "lease_unique", "tests_red_green",
    "ci_selected", "independent_review", "merged", "main_acceptance",
    "issue_closed", "next_issue",
    "manual_rejected", "repair_recovered", "expired_lease_resumed",
    "stale_agent_blocked", "failed_gate_blocked", "unauthorized_merge_blocked",
)


def validate_proof(evidence: dict, *, repository: str) -> list[str]:
    errors = []
    if evidence.get("repository") != repository:
        errors.append("Evidence does not match target repository")
    if evidence.get("mode") != "live":
        errors.append("Canary requires a real GitHub execution (not a simulation)")
    sha = evidence.get("main_sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        errors.append("Missing exact default-branch SHA")
    steps = evidence.get("steps")
    if not isinstance(steps, dict):
        return errors + ["Missing step evidence"]
    if set(steps) != set(STEPS):
        errors.append("Canary evidence step set incomplete or unexpected")
    for step in STEPS:
        proof = steps.get(step)
        if not isinstance(proof, dict):
            errors.append(f"{step}: missing structured proof")
            continue
        if proof.get("result") != "passed":
            errors.append(f"{step}: proof is not passing")
        run_url = proof.get("workflow_run_url", "")
        prefix = f"https://github.com/{repository}/actions/runs/"
        if not isinstance(run_url, str) or not run_url.startswith(prefix):
            errors.append(f"{step}: expected matching GitHub Actions URL")
        elif not run_url[len(prefix):].isdigit():
            errors.append(f"{step}: invalid Actions run ID")
        digest = proof.get("artifact_sha256")
        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            errors.append(f"{step}: artifact integrity digest missing")
        if not isinstance(proof.get("commit_sha"), str) or not SHA.fullmatch(
            proof["commit_sha"]
        ):
            errors.append(f"{step}: missing exact proof commit SHA")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    try:
        evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
        issues = validate_proof(evidence, repository=args.repo)
    except (OSError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for issue in issues:
        print(f"ERROR: {issue}", file=sys.stderr)
    if issues:
        return 1
    print(
        "STRUCTURAL PASS ONLY: live GitHub runs, review identities, "
        "merge records and artifact SHAs still require independent online verification."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
