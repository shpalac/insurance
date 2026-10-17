#!/usr/bin/env python3
"""Run issue acceptance against trusted repository-owned targets only.

Never run Issue-provided shell commands. This process is intended for an
unprivileged runner with no writable GitHub token or secrets.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from validate_issue_manifest import extract_manifest, validate_body
from acceptance_discovery import DiscoveryError, available_criteria, named_path

ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r"^[0-9a-f]{40}$")


class AcceptanceError(ValueError):
    """An acceptance gate must fail closed on malformed evidence."""


def load_targets(root: Path = ROOT) -> dict:
    registry = json.loads(
        (root / ".factory/acceptance-targets.json").read_text(encoding="utf-8")
    )
    targets = registry.get("targets")
    if not isinstance(targets, dict):
        raise AcceptanceError("Trusted target registry must contain targets")
    return targets


def verify_report(path: Path) -> dict:
    """Require non-empty passing JUnit evidence with recorded assertions."""
    try:
        parsed = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        raise AcceptanceError(f"Missing or invalid JUnit evidence: {exc}") from exc
    root = parsed.getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise AcceptanceError("Unexpected JUnit XML root")
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    cases = [case for suite in suites for case in suite.iter("testcase")]
    if not cases:
        raise AcceptanceError("Zero executed testcases")
    if any(case.find("failure") is not None or case.find("error") is not None
           for case in cases):
        raise AcceptanceError("JUnit contains failed or errored testcases")
    if any(case.find("skipped") is not None for case in cases):
        raise AcceptanceError("JUnit contains skipped required testcases")
    assertions = 0
    for suite in suites:
        count = suite.get("assertions", "0")
        try:
            assertions += int(count)
        except ValueError as exc:
            raise AcceptanceError("Invalid JUnit assertion count") from exc
    if assertions < 1:
        raise AcceptanceError("JUnit contains no recorded test assertions")
    return {"testcases": len(cases), "assertions": assertions}


def _validated_report_path(root: Path, relative: str) -> Path:
    """Reject traversal and symlink escapes even if the manifest was bypassed."""
    if not relative.startswith("reports/"):
        raise AcceptanceError("JUnit evidence must be under reports/")
    absolute = (root / relative).resolve()
    if not absolute.is_relative_to(root.resolve()):
        raise AcceptanceError("JUnit evidence escapes repository root")
    return absolute


def run_criteria(
    issue_body: str, *, issue_id: int, head_sha: str,
    root: Path = ROOT, targets: dict | None = None,
    criteria_subset: set[str] | None = None,
    runner_os: str = "ubuntu-latest",
) -> list[dict]:
    """Execute only trusted registry argv for explicitly linked criteria."""
    if not SHA.fullmatch(head_sha):
        raise AcceptanceError("Expected exact immutable PR head SHA")
    errors = validate_body(issue_body, root=root, expected_issue_id=issue_id)
    if errors:
        raise AcceptanceError("; ".join(errors))
    manifest = extract_manifest(issue_body)
    targets = load_targets(root) if targets is None else targets
    if runner_os not in {"ubuntu-latest", "macos-latest", "windows-latest"}:
        raise AcceptanceError("Unsupported hosted OS")
    selected = manifest["acceptance_criteria"]
    all_ids = {ac["id"] for ac in selected}
    if criteria_subset is not None:
        if not criteria_subset or not criteria_subset.issubset(all_ids):
            raise AcceptanceError("Invalid claimed AC subset")
        selected = [ac for ac in selected if ac["id"] in criteria_subset]

    try:
        available = available_criteria(
            root, issue_id, [ac["id"] for ac in selected], targets
        )
    except DiscoveryError as exc:
        raise AcceptanceError(str(exc)) from exc
    # Pre-clear all reports before running any grouped target. Existing
    # registered suites often emit multiple AC reports in one invocation.
    for criterion in selected:
        report = _validated_report_path(root, criterion["required_report"])
        report.parent.mkdir(parents=True, exist_ok=True)
        if report.exists():
            report.unlink()

    results = []
    executed: set[tuple[str, ...]] = set()
    for criterion in selected:
        if criterion["runner_os"] != runner_os:
            raise AcceptanceError("Criterion is assigned to a different hosted OS")
        name = f"{issue_id}/{criterion['id']}"
        source = available.get(criterion["id"])
        if source is None:
            raise AcceptanceError(
                f"No implementation-shipped acceptance test for {name}; "
                f"add .factory/acceptance/issue_{issue_id}/"
                f"test_ac_{criterion['id'].split('-')[1]}.py"
            )
        report = _validated_report_path(root, criterion["required_report"])
        if source == "reviewed":
            target = targets[name]
            args = target.get("argv")
            if (not isinstance(args, list) or len(args) < 3
                    or not all(isinstance(x, str) and x for x in args)
                    or not isinstance(target.get("runner_os"), str)):
                raise AcceptanceError(f"Invalid reviewed target: {name}")
            if target["runner_os"] != criterion["runner_os"]:
                raise AcceptanceError(f"OS mismatch for: {name}")
            if args[0] not in {"python", "python3"} or args[1:3] != ["-m", "unittest"]:
                raise AcceptanceError(f"Untrusted executable type: {name}")
            command = (sys.executable, *args[1:])
            cache_key = ("reviewed", *command)
        else:
            # No arbitrary command comes from Issue text, and new Issues
            # require no hand-edited registry.
            if criterion["runner_os"] != runner_os:
                raise AcceptanceError(f"{name}: requires runner-specific hosted proof")
            command = (
                sys.executable,
                str(root / ".factory/scripts/run_named_acceptance.py"),
                "--issue", str(issue_id), "--criterion", criterion["id"],
                "--report", str(report),
            )
            cache_key = ("co-shipped", *command)
        if cache_key not in executed:
            runtime = min(criterion["timeout_seconds"], 900)
            result = subprocess.run(
                command, cwd=root, capture_output=True, text=True,
                timeout=runtime, check=False, env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONPATH": str(root),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            if result.returncode:
                raise AcceptanceError(
                    f"{name}: acceptance failed ({result.returncode}): "
                    f"{result.stderr[-300:]}"
                )
            executed.add(cache_key)
        evidence = verify_report(report)
        results.append({
            "id": criterion["id"],
            "target": name,
            "runner": criterion["runner_os"],
            "head_sha": head_sha,
            "artifact": criterion["required_report"],
            **evidence,
            "status": "PASS",
        })
    return results


def traceability_table(results: list[dict]) -> str:
    lines = [
        "<!-- FACTORY_ACCEPTANCE_REPORT -->",
        "| Criterion | Reviewed target | Runner | Result | Assertions | Evidence |",
        "|---|---|---|---|---:|---|",
    ]
    for record in results:
        lines.append(
            f"| {record['id']} | {record['target']} | {record['runner']} "
            f"| {record['status']} | {record['assertions']} "
            f"| \`{record['artifact']}\` |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue-body", required=True, type=Path)
    parser.add_argument("--issue", required=True, type=int)
    parser.add_argument("--head", required=True)
    parser.add_argument("--criteria", help="Comma-separated claimed AC identifiers")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    subset = set(args.criteria.split(",")) if args.criteria else None
    try:
        rows = run_criteria(
            args.issue_body.read_text(encoding="utf-8"),
            issue_id=args.issue, head_sha=args.head, criteria_subset=subset
        )
    except (AcceptanceError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    report = traceability_table(rows)
    print(report)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
