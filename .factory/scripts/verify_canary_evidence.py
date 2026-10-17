#!/usr/bin/env python3
"""Validate structured live-canary proof references; no synthetic pass is trusted.

This structural preflight is NOT a substitute for online GitHub run/commit
verification or independent review. It cannot activate the factory.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from urllib import request
from pathlib import Path
import re
import sys

SHA = re.compile(r"^[a-f0-9]{40}$")
DIGEST = re.compile(r"^[a-f0-9]{64}$")
STEPS = (
    "issue_created", "validated", "lease_unique", "tests_red_green",
    "ci_selected", "ci_only_admission", "merged", "main_acceptance",
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



def verify_online(evidence: dict, *, repository: str, fetch) -> list[str]:
    """Verify real GitHub Actions run SHAs and nonexpired artifact digests.

    Even verified artifacts are not evidence of unattended agent dispatch or
    effective branch protection without separate live canary proof.
    """
    errors = validate_proof(evidence, repository=repository)
    if errors:
        return errors
    main = evidence["main_sha"]
    try:
        if fetch("/git/ref/heads/main")["object"]["sha"] != main:
            errors.append("Default-branch SHA changed since the canary proof")
        for key in STEPS:
            row = evidence["steps"][key]
            run_id = row["workflow_run_url"].rsplit("/", 1)[-1]
            run = fetch(f"/actions/runs/{run_id}")
            if (run.get("head_sha") != row["commit_sha"]
                    or run.get("status") != "completed"
                    or run.get("conclusion") != "success"):
                errors.append(f"{key}: GitHub run not completed successfully at SHA")
                continue
            artifacts = fetch(f"/actions/runs/{run_id}/artifacts")
            items = artifacts.get("artifacts", [])
            if (not isinstance(items, list)
                    or artifacts.get("total_count", 0) > 100):
                errors.append(f"{key}: missing or incomplete artifact listing")
                continue
            expected = "sha256:" + row["artifact_sha256"]
            if not any(
                record.get("digest") == expected
                and not record.get("expired", True)
                for record in items if isinstance(record, dict)
            ):
                errors.append(f"{key}: artifact digest missing or expired")
    except (KeyError, TypeError, ValueError, OSError):
        errors.append("GitHub live evidence API unavailable or malformed")
    return errors

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args(argv)
    try:
        evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
        issues = validate_proof(evidence, repository=args.repo)
        if not issues and args.online:
            token = os.environ.get("GH_TOKEN", "")
            if not token:
                raise ValueError("Online verification requires a GitHub read token")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
                raise ValueError("Invalid repository identity")
            def fetch(path):
                if not path.startswith("/") or "://" in path:
                    raise ValueError("Unexpected GitHub API path")
                req = request.Request(
                    "https://api.github.com/repos/" + args.repo + path,
                    headers={
                        "Authorization": "Bearer " + token,
                        "Accept": "application/vnd.github+json",
                    },
                )
                with request.urlopen(req, timeout=20) as response:
                    return json.load(response)
            issues = verify_online(evidence, repository=args.repo, fetch=fetch)
    except (OSError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for issue in issues:
        print(f"ERROR: {issue}", file=sys.stderr)
    if issues:
        return 1
    print(
        "STRUCTURAL OR LIVE-ARTIFACT PASS ONLY: full authenticated worker, "
        "lease, merge and Issue-closure canary verification remains mandatory."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
