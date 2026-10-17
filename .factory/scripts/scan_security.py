#!/usr/bin/env python3
"""Mandatory CI policy scanner for leaked credentials and unpinned workflow actions.

Runs on ALL PRs, including docs-only diffs, before merge. This conservative
scanner recognizes known credential structures, not every possible secret.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

SHA = re.compile(r"^[0-9a-f]{40}$")
GITHUB_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{50,})\b")
AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
HEX = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
EXEMPTIONS = ("./",)


def inspect_added_lines(lines: list[str]) -> list[str]:
    """Read only new patch lines; never expose secret values in diagnostics."""
    errors = []
    for line_number, text in enumerate(lines, 1):
        if (GITHUB_TOKEN.search(text) or AWS_KEY.search(text) or PRIVATE_KEY.search(text)):
            errors.append(f"Potential credential on added line {line_number}")
    return errors


def workflow_action_errors(content: str, path: str) -> list[str]:
    errors = []
    for match in USES.finditer(content):
        ref = match.group(1)
        if ref.startswith(EXEMPTIONS):
            continue
        if ref.startswith("docker://"):
            if "@sha256:" not in ref:
                errors.append(f"{path}: container action must use immutable sha256 digest")
            continue
        if "@" not in ref:
            errors.append(f"{path}: action without pinned revision")
            continue
        action, revision = ref.rsplit("@", 1)
        if not action or not HEX.fullmatch(revision):
            errors.append(f"{path}: action must use a 40-character commit SHA")
    return errors


def scan_patch(patch: str) -> list[str]:
    """Exclude removed lines and diff metadata, including +++ b/path lines."""
    added = [
        line[1:] for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return inspect_added_lines(added)


def scan_repo(root: Path, patch: str) -> list[str]:
    errors = scan_patch(patch)
    for workflow in sorted((root / ".github/workflows").glob("*.y*ml")):
        errors.extend(workflow_action_errors(
            workflow.read_text(encoding="utf-8"),
            workflow.relative_to(root).as_posix(),
        ))
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    args = p.parse_args(argv)
    if not SHA.fullmatch(args.base) or not SHA.fullmatch(args.head):
        print("ERROR: invalid baseline or candidate SHA", file=sys.stderr)
        return 1
    try:
        result = subprocess.run(
            ["git", "diff", "--unified=0", "--no-ext-diff", args.base, args.head],
            capture_output=True, text=True, timeout=45, check=True,
        )
        errors = scan_repo(Path.cwd(), result.stdout)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: security scan unable to verify git range ({type(exc).__name__})", file=sys.stderr)
        return 1
    for problem in errors:
        print("ERROR: " + problem, file=sys.stderr)
    if errors:
        return 1
    print("PASS: mandatory credential signatures and workflow pinning checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
