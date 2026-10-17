#!/usr/bin/env python3
"""Discover Issue acceptance tests shipped with an implementation, not in Issue text.

Convention:
    .factory/acceptance/issue_<github-issue>/test_ac_<criterion-number>.py

Each file must expose one or more unittest.TestCase methods named
test_ac_<criterion-number>_<behavior> with explicit self.assert* calls.
The verifier is repository-owned. Issue-authored shell commands are ignored.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re

ISSUE = re.compile(r"^[1-9][0-9]*$")
CRITERION = re.compile(r"^AC-([1-9][0-9]*)$")
ROOT = Path(__file__).resolve().parents[2]


class DiscoveryError(ValueError):
    pass


def named_path(root: Path, issue: int, criterion: str) -> Path:
    if type(issue) is not int or issue < 1:
        raise DiscoveryError("GitHub Issue number must be positive")
    match = CRITERION.fullmatch(criterion)
    if not match:
        raise DiscoveryError("Invalid acceptance criterion identifier")
    base = root / ".factory" / "acceptance"
    path = base / f"issue_{issue}" / f"test_ac_{match.group(1)}.py"
    # Neither the acceptance root nor an Issue directory may be symlinked
    # outside the checked-out repository. Broken symlinks fail closed too.
    if (base.is_symlink() or (base / f"issue_{issue}").is_symlink()
            or not base.resolve().is_relative_to(root.resolve())
            or not path.resolve().is_relative_to(base.resolve())):
        raise DiscoveryError("Acceptance test path escapes the trusted repository")
    return path


def validate_named_test(path: Path, criterion: str) -> int:
    """Fail closed on missing/ambiguous unittest definitions before execution."""
    match = CRITERION.fullmatch(criterion)
    if not match or not path.is_file() or path.is_symlink():
        raise DiscoveryError(f"Missing ordinary acceptance test: {criterion}")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError, UnicodeError) as exc:
        raise DiscoveryError(f"Malformed acceptance test for {criterion}") from exc
    prefix = f"test_ac_{match.group(1)}_"
    accepted = 0
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {
            ast.unparse(base) for base in node.bases
            if isinstance(base, (ast.Name, ast.Attribute))
        }
        if not ({"unittest.TestCase", "TestCase"} & bases):
            continue
        for method in node.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not method.name.startswith("test_"):
                continue
            if not method.name.startswith(prefix) or isinstance(method, ast.AsyncFunctionDef):
                raise DiscoveryError(
                    f"{criterion} must use named synchronous test_ac methods"
                )
            calls = [
                sub for sub in ast.walk(method)
                if isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "self"
                and sub.func.attr.startswith("assert")
            ]
            if not calls:
                raise DiscoveryError(f"{criterion} test lacks an explicit assertion")
            accepted += 1
    if accepted < 1:
        raise DiscoveryError(f"{criterion} has no named unittest.TestCase methods")
    return accepted


def available_criteria(
    root: Path, issue: int, criteria: list[str], reviewed: dict
) -> dict[str, str]:
    """Identify complete test coverage without executing tests or Issue commands.

    A legacy reviewed target retains priority; new Issues auto-discover a test
    file for each criterion without editing a central JSON registry.
    """
    available: dict[str, str] = {}
    for criterion in criteria:
        key = f"{issue}/{criterion}"
        path = named_path(root, issue, criterion)
        if key in reviewed:
            if not isinstance(reviewed[key], dict):
                raise DiscoveryError(f"Invalid reviewed target for {key}")
            available[criterion] = "reviewed"
        elif path.exists() or path.is_symlink():
            validate_named_test(path, criterion)
            available[criterion] = "co-shipped"
    return available
