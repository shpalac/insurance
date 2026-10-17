"""Merge-admission guard: CI-only does not mean unguarded merging.

Do not merge from this module: an owner-trusted controller must first establish
effective GitHub branch protection independently and then call this guard
against fresh authoritative PR/check-run metadata.
"""
from __future__ import annotations
from dataclasses import dataclass
from fnmatch import fnmatchcase
import re

SHA = re.compile(r"^[a-f0-9]{40}$")
CHECKS = (
    "factory-gate-preflight",
    "factory-bootstrap-gate",
    "unit-tests",
    "issue-completion",
)
PROTECTED = (".factory/**", ".github/workflows/**", "AGENTS.md", "SECURITY.md")


@dataclass(frozen=True)
class Admission:
    head_sha: str
    eligible: bool
    failures: tuple[str, ...]


def assess(
    *, pr: dict, checks: list[dict], actual_head: str,
    allowed_paths: list[str], owner_authorized: bool,
    protection_confirmed: bool, expected_issue: int,
) -> Admission:
    """Pure fail-closed decision. Untrusted PR authorizations are ignored."""
    errors = []
    head = pr.get("head", {}).get("sha")
    if not isinstance(head, str) or not SHA.fullmatch(head):
        return Admission("", False, ("Invalid PR head",))
    if actual_head != head:
        errors.append("PR changed since verification")
    if pr.get("base", {}).get("ref") != "main":
        errors.append("PR does not target main")
    if not pr.get("mergeable") or pr.get("draft") or pr.get("merged"):
        errors.append("PR mergeability is unverified")
    if not protection_confirmed:
        errors.append("Enforced main branch protections are unverified")
    if pr.get("state") != "open":
        errors.append("PR not open")
    if pr.get("security_hold") or "status:blocked" in pr.get("labels", []):
        errors.append("Security or policy hold")
    if type(expected_issue) is not int or expected_issue < 1:
        errors.append("No verified linked Issue")
    body = pr.get("body") or ""
    if not re.search(r"(?m)^Refs #" + str(expected_issue) + r"\s*$", body):
        errors.append("Missing exact Refs declaration")
    changed = pr.get("changed_paths")
    if not isinstance(changed, list) or not changed:
        errors.append("Missing authoritative changed-path inventory")
        changed = []
    for path in changed:
        if not isinstance(path, str) or not any(
            fnmatchcase(path, pattern) for pattern in allowed_paths
        ):
            errors.append("Changed path falls outside the validated Issue scope")
            break
    if (any(any(fnmatchcase(path, pat) for pat in PROTECTED)
            for path in changed if isinstance(path, str))
            and owner_authorized is not True):
        errors.append("Protected path needs independent owner authorization")
    for name in CHECKS:
        matching = [
            item for item in checks
            if item.get("name") == name
            and item.get("head_sha") == head
            and item.get("status") == "completed"
            and item.get("conclusion") == "success"
            and item.get("app", {}).get("slug") == "github-actions"
        ]
        if len(matching) != 1:
            errors.append("Missing unique passing check: " + name)
    return Admission(head, not errors, tuple(errors))
