#!/usr/bin/env python3
"""Prove a job is testing GitHub's expected commit, not a mislabeled SHA.

A pull_request checkout normally points to GitHub's synthetic merge commit.
Its parents must include the immutable PR head; on push, the checkout equals
the pushed commit. The proof runs *before* acceptance test execution.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

SHA = re.compile(r"^[a-f0-9]{40}$")


def verify_identity(
    actual: str, run_sha: str, head_sha: str, event: str,
    parent_shas: tuple[str, ...] = (),
) -> list[str]:
    errors = []
    if not all(isinstance(v, str) and SHA.fullmatch(v)
               for v in (actual, run_sha, head_sha)):
        return ["Missing or invalid immutable commit SHA"]
    if actual != run_sha:
        errors.append("Checkout does not match GitHub workflow run SHA")
    if event == "pull_request":
        if len(parent_shas) < 2 or head_sha not in parent_shas:
            errors.append("Tested merge commit is not descended directly from PR head")
    elif event == "push":
        if actual != head_sha:
            errors.append("Push checkout does not match pushed head")
    else:
        errors.append("Unrecognized CI event for checkout proof")
    return errors


def git_identity(root: Path) -> tuple[str, tuple[str, ...]]:
    actual = subprocess.check_output(
        ["git", "rev-parse", "--verify", "HEAD"], cwd=root, text=True,
        timeout=15,
    ).strip()
    parent_line = subprocess.check_output(
        ["git", "show", "-s", "--format=%P", "HEAD"], cwd=root, text=True,
        timeout=15,
    ).strip()
    return actual, tuple(parent_line.split()) if parent_line else ()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args(argv)
    try:
        actual, parents = git_identity(Path.cwd())
        errors = verify_identity(actual, args.run, args.head, args.event, parents)
    except (OSError, subprocess.SubprocessError) as exc:
        print("ERROR: checkout identity unavailable: " + type(exc).__name__,
              file=sys.stderr)
        return 1
    for problem in errors:
        print("ERROR: " + problem, file=sys.stderr)
    if errors:
        return 1
    print("PASS: checked-out SHA and immutable candidate ancestry verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
