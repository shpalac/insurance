#!/usr/bin/env python3
"""Compute a conservative deterministic impacted-job manifest for a Git diff."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

SHA = re.compile(r"^[a-f0-9]{40}$")
JOBS = ("scanner", "factory", "docs", "macos", "windows")
GLOBAL_NAMES = {"pyproject.toml", "AGENTS.md", "SECURITY.md", ".gitignore"}
GLOBAL_PREFIXES = (".github/", ".factory/", "requirements", "setup.")
DOC_NAMES = {"README.md", "CONTRIBUTING.md", "LICENSE"}


def impacted(files: list[str], head_sha: str) -> dict:
    """Unknown paths, empty change lists and control-plane edits fail closed."""
    if not SHA.fullmatch(head_sha):
        raise ValueError("Expected an exact 40-character Git commit SHA")
    selected = dict.fromkeys(JOBS, False)
    reason = "affected_modules"
    for raw in files:
        path = raw.replace("\\", "/").strip()
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Invalid repository path in diff")
        if (path in GLOBAL_NAMES or path.startswith(GLOBAL_PREFIXES)
                or path.endswith((".lock", ".toml"))):
            reason = "global_dependency_modified"
            break
        if path in DOC_NAMES or path.startswith("docs/") or path.endswith(".md"):
            selected["docs"] = True
        elif path.startswith(("src/insurance/", "tests/", "data/observations/")):
            selected["scanner"] = True
        elif path.startswith("macos/"):
            selected["macos"] = True
        elif path.startswith("windows/"):
            selected["windows"] = True
        elif path.startswith(("ios/", "android/")):
            reason = "unknown_platform_dependencies"
            break
        else:
            reason = "unknown_dependency_impact"
            break
    if not files:
        reason = "empty_or_unavailable_diff"
    if reason != "affected_modules":
        selected = dict.fromkeys(JOBS, True)
    if not any(selected.values()):
        selected["docs"] = True
    body = {
        "schema_version": "1.0",
        "head_sha": head_sha,
        "selected_jobs": selected,
        "reason": reason,
        "changed_paths": sorted(set(files)),
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {**body, "integrity_sha256": digest}


def git_changed_paths(base_sha: str, head_sha: str) -> list[str]:
    if not SHA.fullmatch(base_sha) or not SHA.fullmatch(head_sha):
        raise ValueError("Unsafe or incomplete commit SHA")
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base_sha, head_sha],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return sorted(set(result.stdout.splitlines()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = impacted(git_changed_paths(args.base, args.head), args.head)
    value = json.dumps(result, sort_keys=True, separators=(",", ":"))
    print(value)
    if args.output:
        with args.output.open("a", encoding="utf-8") as stream:
            stream.write(f"manifest={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
