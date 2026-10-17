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
) -> list[dict]:
    """Execute only trusted registry argv for explicitly linked criteria."""
    if not SHA.fullmatch(head_sha):
        raise AcceptanceError("Expected exact immutable PR head SHA")
    errors = validate_body(issue_body, root=root, expected_issue_id=issue_id)
    if errors:
        raise AcceptanceError("; ".join(errors))
    manifest = extract_manifest(issue_body)
    targets = load_targets(root) if targets is None else targets
    selected = manifest["acceptance_criteria"]
    all_ids = {ac["id"] for ac in selected}
    if criteria_subset is not None:
        if not criteria_subset or not criteria_subset.issubset(all_ids):
            raise AcceptanceError("Invalid claimed AC subset")
        selected = [ac for ac in selected if ac["id"] in criteria_subset]

    results = []
    for criterion in selected:
        name = f"{issue_id}/{criterion['id']}"
        target = targets.get(name)
        if not isinstance(target, dict):
            raise AcceptanceError(f"No reviewed trusted test target: {name}")
        args = target.get("argv")
        if (not isinstance(args, list) or not args
                or not all(isinstance(x, str) and x for x in args)
                or not isinstance(target.get("runner_os"), str)):
            raise AcceptanceError(f"Invalid trusted target: {name}")
        if target["runner_os"] != criterion["runner_os"]:
            raise AcceptanceError(f"OS mismatch for: {name}")
        # Registry argv must not launch arbitrary shells or depend on PATH.
        if args[0] not in {"python", "python3"} or args[1:3] != ["-m", "unittest"]:
            raise AcceptanceError(f"Untrusted executable type: {name}")
        report = _validated_report_path(root, criterion["required_report"])
        report.parent.mkdir(parents=True, exist_ok=True)
        if report.exists():
            report.unlink()
        runtime = min(criterion["timeout_seconds"], 900)
        result = subprocess.run(
            [sys.executable, *args[1:]],
            cwd=root, capture_output=True, text=True, timeout=runtime,
            check=False, env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": str(root),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        if result.returncode:
            raise AcceptanceError(
                f"{name}: trusted test failed with exit {result.returncode}: "
                f"{result.stderr[-800:]}"
            )
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
