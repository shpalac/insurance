#!/usr/bin/env python3
"""Run all implementation-shipped acceptance tests as permanent CI regressions.

This deliberately has no issue-number registry. Every named Issue suite stays
discoverable after its GitHub Issue closes. Separate PR-linked acceptance still
binds full evidence to the exact candidate head and remote Issue manifest.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from acceptance_discovery import DiscoveryError, validate_named_test

ROOT = Path(__file__).resolve().parents[2]
ISSUE_DIR = re.compile(r"^issue_([1-9][0-9]*)$")
TEST_FILE = re.compile(r"^test_ac_([1-9][0-9]*)\.py$")
MAX_SUITES = 1000


def discover(root: Path) -> list[tuple[int, str]]:
    base = root / ".factory" / "acceptance"
    if not base.exists():
        return []
    if not base.is_dir() or base.is_symlink() or not base.resolve().is_relative_to(root.resolve()):
        raise DiscoveryError("Invalid acceptance root")
    suites: list[tuple[int, str]] = []
    for folder in sorted(base.iterdir()):
        match = ISSUE_DIR.fullmatch(folder.name)
        if not match or not folder.is_dir() or folder.is_symlink():
            raise DiscoveryError("Unexpected entry in acceptance root")
        for path in sorted(folder.iterdir()):
            if path.name == "__pycache__":
                raise DiscoveryError("Untracked generated acceptance directory")
            file_match = TEST_FILE.fullmatch(path.name)
            if not file_match:
                raise DiscoveryError("Unexpected entry in Issue acceptance directory")
            criterion = "AC-" + file_match.group(1)
            validate_named_test(path, criterion)
            suites.append((int(match.group(1)), criterion))
            if len(suites) > MAX_SUITES:
                raise DiscoveryError("Acceptance suites exceed CI capacity; shard runners")
    return suites


def run_all(root: Path, *, run=subprocess.run) -> dict:
    suites = discover(root)
    for issue, criterion in suites:
        n = criterion.split("-")[1]
        command = [
            sys.executable, str(root / ".factory/scripts/run_named_acceptance.py"),
            "--issue", str(issue), "--criterion", criterion,
            "--report", f"reports/permanent/issue_{issue}_ac_{n}.xml",
        ]
        completed = run(
            command, cwd=root, check=False, capture_output=True, text=True,
            timeout=120, env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": str(root),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        if completed.returncode != 0:
            raise DiscoveryError(
                f"Permanent acceptance regression failed: #{issue} {criterion}"
            )
    return {"checked": len(suites), "issues": len({issue for issue, _ in suites})}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        summary = run_all(args.root)
        print(json.dumps({"status": "PASS", **summary}, sort_keys=True))
        return 0
    except (DiscoveryError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        print(f"ERROR: permanent acceptance blocked ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
