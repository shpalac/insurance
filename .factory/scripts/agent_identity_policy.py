"""Fail-closed GitHub-native identity admission for disabled-by-default orchestration."""
from __future__ import annotations
from dataclasses import dataclass

ROLE_PERMISSIONS = {
    "validator": frozenset({"issues:read", "contents:read"}),
    "developer": frozenset({"contents:read", "contents:write", "pull_requests:write"}),
    "integrator": frozenset({"contents:read", "pull_requests:write", "checks:read"}),
}
GITHUB_ACTIONS_IDENTITY = "github-actions[bot]"

@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str

def authorize(*, enabled: bool, actor: str, role: str, permissions: set[str],
              approved_logins: set[str], trusted_workflow: bool,
              owner_approved: bool, protected_paths: bool = False) -> Decision:
    if not enabled:
        return Decision(False, "orchestration disabled")
    if role not in ROLE_PERMISSIONS:
        return Decision(False, "unknown role")
    if not actor or actor not in approved_logins:
        return Decision(False, "actor not allowlisted")
    if actor == GITHUB_ACTIONS_IDENTITY and not trusted_workflow:
        return Decision(False, "workflow identity not bound to trusted workflow")
    if not ROLE_PERMISSIONS[role].issubset(permissions):
        return Decision(False, "missing role permissions")
    if protected_paths and (not owner_approved or role == "developer"):
        return Decision(False, "protected paths require independent owner approval and integrator")
    if role == "integrator" and not trusted_workflow:
        return Decision(False, "integrator requires trusted workflow")
    return Decision(True, "role authorized")
