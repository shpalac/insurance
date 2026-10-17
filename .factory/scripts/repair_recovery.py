#!/usr/bin/env python3
"""Bounded CI repair state machine; no PR-authored commands ever execute.

A trusted role and current durable lease are required for reservation,
dispatch and eventual merge admission. External agents remain disabled until
owner-approved GitHub App permissions and role-scoped dispatch are configured.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
import re

from lease_state import Lease, LeaseStore, StaleLease
from lease_fencing import WorkerProof, assert_fence
from pr_merge_coordinator import check_gate, approved

SHA = re.compile(r"^[a-f0-9]{40}$")
REPAIRABLE = frozenset({
    "scanner", "factory", "macos", "windows", "unit-tests",
    "acceptance-macos", "acceptance-windows",
})
SECURITY = frozenset({
    "policy", "issue-completion", "factory-gate-preflight",
    "factory-bootstrap-gate", "factory-trusted-admission",
})
MAX_REPAIRS = 3
MAX_CONFLICT_REBASES = 2


class RepairDenied(ValueError):
    pass


@dataclass(frozen=True)
class RepairResult:
    action: str
    reason: str
    run_id: int
    sha: str
    failed_jobs: tuple[str, ...]
    idempotency_key: str = ""


def identify_failure(*, run: dict, jobs: list[dict], pr: dict,
                     last_run_id: int = 0, attempts: int = 0) -> RepairResult:
    """Only actual failed test/lint runs on the current same-repository head."""
    id_ = run.get("id")
    sha = run.get("head_sha")
    if type(id_) is not int or id_ < 1 or not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise RepairDenied("Untrusted CI run identity")
    def refuse(reason, failed=()):
        return RepairResult("blocked", reason, id_, sha, tuple(sorted(failed)))
    if (run.get("event") != "pull_request"
            or run.get("name") != "Factory selective CI"
            or run.get("status") != "completed" or run.get("conclusion") != "failure"):
        return refuse("not_a_completed_failed_pr_run")
    if (pr.get("state") != "open" or pr.get("draft")
            or (pr.get("head") or {}).get("sha") != sha
            or (pr.get("base") or {}).get("ref") != "main"):
        return refuse("stale_branch_or_invalid_pr")
    if id_ <= last_run_id:
        return refuse("duplicate_or_stale_run")
    if attempts >= MAX_REPAIRS:
        return refuse("ci_repair_budget_exhausted")
    failed = {job.get("name") for job in jobs
              if job.get("status") == "completed" and job.get("conclusion") == "failure"}
    if not failed:
        return refuse("missing_failed_job_evidence")
    if failed & SECURITY:
        return refuse("security_or_policy_failure_requires_intervention", failed)
    if not failed.issubset(REPAIRABLE):
        return refuse("unexpected_failed_job_requires_intervention", failed)
    key = hashlib.sha256(json.dumps({
        "id": id_, "head_sha": sha, "pr": pr.get("number"),
        "failed": sorted(failed),
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return RepairResult("dispatch", "test_or_lint_failed", id_, sha,
                        tuple(sorted(failed)), key)


def reserve_repair(
    store: LeaseStore, *, proof: WorkerProof, result: RepairResult,
    authenticated_login: str, approved_logins: set[str], now: datetime,
) -> WorkerProof:
    """One nonforced CAS reservation per immutable CI failure/run/head."""
    if result.action != "dispatch" or not re.fullmatch(
        r"[a-f0-9]{64}", result.idempotency_key
    ):
        raise RepairDenied("No safe repair dispatch")
    lease = assert_fence(
        store, proof=proof, operation="ci_repair",
        authenticated_login=authenticated_login,
        approved_logins=approved_logins, now=now,
        actual_branch=proof.branch, actual_sha=proof.commit_sha,
    )
    if lease.attempts >= MAX_REPAIRS:
        raise RepairDenied("repair attempts exhausted")
    fingerprint = hashlib.sha256(("run:" + result.idempotency_key).encode()).hexdigest()
    if fingerprint in lease.diff_hashes:
        raise RepairDenied("duplicate CI repair run reservation")
    if lease.commit_sha != result.sha or not lease.branch.startswith("factory/"):
        raise RepairDenied("Repair run differs from leased branch checkpoint")
    next_lease = replace(
        lease, revision=lease.revision + 1, phase="repairing",
        diff_hashes=(*lease.diff_hashes, fingerprint),
    )
    if not store.cas(lease.entity, lease.revision, next_lease):
        raise StaleLease("Lost durable reservation CAS to competing worker")
    return WorkerProof(
        lease.entity, next_lease.epoch, next_lease.revision,
        next_lease.owner, next_lease.role,
        next_lease.branch, next_lease.commit_sha,
    )


def normalized_diff_hash(diff: str) -> str:
    if not isinstance(diff, str) or not diff.strip():
        raise RepairDenied("Missing actual normalized diff")
    return hashlib.sha256("\n".join(
        line.strip() for line in diff.replace("\r\n", "\n").split("\n")
        if line.strip()
    ).encode()).hexdigest()


def record_failure(
    lease: Lease, *, normalized_hash: str, attempts: int,
    conflict_rebases: int,
) -> tuple[str, str]:
    """Third unsuccessful repair/repeated diff/exhausted conflict -> blocked."""
    if (not re.fullmatch(r"[a-f0-9]{64}", normalized_hash)
            or type(attempts) is not int or attempts < 0
            or type(conflict_rebases) is not int or conflict_rebases < 0):
        raise RepairDenied("Invalid repair evidence")
    if normalized_hash in lease.diff_hashes:
        return ("blocked", "repeated_normalized_diff")
    if attempts >= MAX_REPAIRS:
        return ("blocked", "three_unsuccessful_repairs")
    if conflict_rebases >= MAX_CONFLICT_REBASES:
        return ("blocked", "conflict_rebase_budget_exhausted")
    return ("repairing", "bounded_retry_remaining")


def approve_candidate(
    *, pr: dict, checks: list[dict], comments: list[dict],
    changed_paths: list[str], owner: str, main_sha: str,
    store: LeaseStore, proof: WorkerProof,
    authenticated_login: str, approved_logins: set[str], now: datetime,
) -> bool:
    """Security, current-head required CI and integrator lease all mandatory."""
    head = (pr.get("head") or {}).get("sha", "")
    if (not isinstance(head, str) or not SHA.fullmatch(head)
            or not SHA.fullmatch(main_sha)
            or pr.get("state") != "open" or pr.get("draft")
            or pr.get("mergeable_state") != "clean"
            or not pr.get("mergeable") or
            (pr.get("base") or {}).get("sha") != main_sha):
        return False
    if (not isinstance(changed_paths, list) or not changed_paths
            or len(changed_paths) >= 100):
        return False
    protected = any(p.startswith((".factory/", ".github/workflows/"))
                    or p in ("AGENTS.md", "SECURITY.md")
                    for p in changed_paths if isinstance(p, str))
    if protected and not approved(comments, owner, head):
        return False
    try:
        assert_fence(store, proof=proof, operation="integrator_merge",
                     authenticated_login=authenticated_login,
                     approved_logins=approved_logins, now=now,
                     actual_branch=proof.branch, actual_sha=head)
    except StaleLease:
        return False
    return check_gate(checks, head)
