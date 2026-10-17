#!/usr/bin/env python3
"""Require >=90% executed changed production lines in the tested PR commit.

Never accepts an exclusion list supplied by PR content. The trusted repository
owns both the source root and minimum coverage policy.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

SHA = re.compile(r"^[0-9a-f]{40}$")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
SOURCE = "src/insurance/"
ROOT = Path(__file__).resolve().parents[2]

class CoverageError(ValueError):
    pass

def patch_changed_lines(text: str) -> dict[str, set[int]]:
    paths = {}
    current = None
    for line in text.splitlines():
        if line.startswith("+++ "):
            raw = line[4:]
            current = raw[2:] if raw.startswith("b/") else None
            if current and current.startswith(SOURCE) and current.endswith(".py"):
                if ".." in current.split("/"):
                    raise CoverageError("Unsafe changed source file")
                paths.setdefault(current, set())
            else:
                current = None
        elif line.startswith("@@ ") and current:
            match = HUNK.match(line)
            if match is None:
                raise CoverageError("Unrecognized diff hunk")
            start, length = int(match.group(1)), int(match.group(2) or "1")
            if length > 10000 or start < 1:
                raise CoverageError("Oversized or invalid changed source hunk")
            paths[current].update(range(start, start + length))
    return paths

def calculate(changed: dict[str, set[int]], report: dict,
              minimum: float = 90.0) -> dict:
    if not isinstance(report, dict) or not isinstance(report.get("files"), dict):
        raise CoverageError("Missing machine-measured coverage report")
    if not 0 < minimum <= 100:
        raise CoverageError("Invalid trusted coverage floor")
    executed, missing = set(), set()
    for path, lines in changed.items():
        if not path.startswith(SOURCE) or not path.endswith(".py"):
            raise CoverageError("Unsupported coverage source")
        entry = report["files"].get(path)
        if entry is None:
            # Coverage.py --source=insurance must enumerate new production files.
            if lines:
                raise CoverageError(f"No measured coverage for changed file: {path}")
            continue
        observed = set(entry.get("executed_lines") or [])
        unobserved = set(entry.get("missing_lines") or [])
        if observed & unobserved or not all(type(x) is int and x > 0
                                           for x in observed | unobserved):
            raise CoverageError("Malformed line-level coverage measurement")
        for line in lines:
            marker = (path, line)
            if line in observed:
                executed.add(marker)
            if line in unobserved:
                missing.add(marker)
    total = len(executed) + len(missing)
    percent = 100.0 * len(executed) / total if total else 100.0
    return {"executed": len(executed), "missing": len(missing),
            "changed_executable_lines": total, "percent": round(percent, 2),
            "threshold": minimum, "passed": percent + 1e-9 >= minimum}

def verify(base: str, head: str, coverage: Path) -> dict:
    if not SHA.fullmatch(base) or not SHA.fullmatch(head):
        raise CoverageError("Invalid immutable diff identity")
    git = subprocess.run(
        ["git", "diff", "--unified=0", "--no-ext-diff",
         "--diff-filter=ACMR", base, head, "--", SOURCE],
        text=True, capture_output=True, timeout=30, check=True)
    paths = patch_changed_lines(git.stdout)
    source = json.loads(coverage.read_text(encoding="utf-8"))
    config = yaml.safe_load((ROOT / ".factory/config.yaml").read_text())
    floor = float(config["verification"]["min_diff_coverage_percent"])
    result = calculate(paths, source, floor)
    if not result["passed"]:
        raise CoverageError(f"Changed-line coverage {result['percent']}% below {floor}%")
    return {**result, "base_sha": base, "head_sha": head,
            "source_files": sorted(paths)}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--coverage", type=Path, required=True)
    args = p.parse_args()
    try:
        value = verify(args.base, args.head, args.coverage)
        print(json.dumps({"status": "PASS", **value}, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as exc:
        print("ERROR: diff coverage blocked (" + str(exc)[:300] + ")",
              file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
