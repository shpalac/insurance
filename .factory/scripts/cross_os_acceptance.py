#!/usr/bin/env python3
"""Execute only Issue-declared, locally shipped tests on the actual hosted OS."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from acceptance_discovery import available_criteria
from run_acceptance_manifest import load_targets, run_criteria
from validate_issue_manifest import extract_manifest, validate_body

ROOT = Path(__file__).resolve().parents[2]
RUNNERS = {"macos-latest": "macOS", "windows-latest": "Windows"}

def runner_identity(expected, actual):
    if RUNNERS.get(expected) != actual:
        raise ValueError("Actual hosted runner does not match the declared runner")

def collect(root, issues, runner, sha, run_id):
    if runner not in RUNNERS or len(sha) != 40 or run_id < 1:
        raise ValueError("Invalid hosted acceptance identity")
    registry = load_targets(root)
    records = []
    for key, issue in sorted(issues.items(), key=lambda pair: int(pair[0])):
        number = int(key)
        body = issue.get("body") or ""
        if issue.get("number") != number:
            raise ValueError("Issue identity mismatch")
        if validate_body(body, root=root, expected_issue_id=number):
            continue
        criteria = [c["id"] for c in extract_manifest(body)["acceptance_criteria"]
                    if c["runner_os"] == runner]
        if not criteria:
            continue
        available = available_criteria(root, number, criteria, registry)
        selected = {c for c in criteria if c in available}
        if not selected:
            continue
        rows = run_criteria(body, issue_id=number, head_sha=sha, root=root,
                            criteria_subset=selected, runner_os=runner)
        for row in rows:
            k = row["id"].split("-")[1]
            destination = f"reports/cross_os/issue_{number}_ac_{k}.xml"
            path = root / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / row["artifact"], path)
            records.append({
                "issue": number, "id": row["id"], "runner": runner,
                "head_sha": sha, "status": row["status"],
                "testcases": row["testcases"], "assertions": row["assertions"],
                "report": destination,
                "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return {"version": 1, "run_id": run_id, "sha": sha, "runner": runner,
            "records": records}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runner", choices=tuple(RUNNERS), required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--issues", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    try:
        runner_identity(a.runner, os.getenv("RUNNER_OS", ""))
        if os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN"):
            raise ValueError("Acceptance subprocess must not have API credentials")
        actual = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=15).strip()
        if actual != os.getenv("GITHUB_SHA"):
            raise ValueError("Tested commit differs from workflow event")
        report = collect(ROOT, json.loads(a.issues.read_text()), a.runner,
                         a.head, a.run_id)
        a.output.write_text(json.dumps(report, sort_keys=True))
        print(json.dumps({"hosted_os": a.runner, "criteria": len(report["records"])}))
        return 0
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        print("ERROR: hosted acceptance blocked (" + type(exc).__name__ + ")",
              file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
