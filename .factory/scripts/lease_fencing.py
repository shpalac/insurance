#!/usr/bin/env python3
"""Validate authenticated lease generation before every agent-directed write.

The fence must execute in trusted control-plane code immediately before an
authorized write. A dispatch envelope alone is never a capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from lease_state import Lease, LeaseConflict, LeaseStore, StaleLease, acquire

SHA = re.compile(r"^[0-9a-f]{40}$")
ACTION_ROLE = {
    "branch_push": frozenset({"developer"}),
    "ci_repair": frozenset({"ci-engineer", "developer"}),
    "issue_transition": frozenset({"validator"}),
    "integrator_merge": frozenset({"integrator"}),
}


@dataclass(frozen=True)
class WorkerProof:
    issue: int
    epoch: int
    revision: int
    owner: str
    role: str
    branch: str
    commit_sha: str


def assert_fence(
    store: LeaseStore, *, proof: WorkerProof, operation: str,
    authenticated_login: str, approved_logins: set[str], now: datetime,
    actual_branch: str = "", actual_sha: str = "",
) -> Lease:
    """Fail closed on role, lease, revision, timestamp or checkout mismatch."""
    if now.tzinfo is None or operation not in ACTION_ROLE:
        raise StaleLease("Untrusted mutation context")
    if (type(proof.issue) is not int or proof.issue < 1
            or type(proof.epoch) is not int or proof.epoch < 1
            or type(proof.revision) is not int or proof.revision < 1
            or not authenticated_login or authenticated_login not in approved_logins
            or authenticated_login != proof.owner
            or proof.role not in ACTION_ROLE[operation]):
        raise StaleLease("Invalid authenticated role/identity/generation")
    lease = store.read(proof.issue)
    if (lease is None or lease.entity != proof.issue
            or lease.epoch != proof.epoch or lease.revision != proof.revision
            or lease.owner != proof.owner or lease.role != proof.role
            or lease.phase not in {"claimed", "repairing"}
            or lease.expires_at <= now or lease.heartbeat_at > now
            or lease.branch != proof.branch
            or lease.commit_sha != proof.commit_sha):
        raise StaleLease("Lease expired, replaced, blocked or superseded")
    if proof.branch and not proof.branch.startswith("factory/"):
        raise StaleLease("Unsafe worker branch")
    if proof.commit_sha and not SHA.fullmatch(proof.commit_sha):
        raise StaleLease("Invalid checkpoint SHA")
    if actual_branch and proof.branch != actual_branch:
        raise StaleLease("Worker branch differs from current checkout")
    if actual_sha and proof.commit_sha != actual_sha:
        raise StaleLease("Worker checkpoint differs from current head")
    # A trusted caller must re-read the same lease immediately before the
    # write. Later ref-CAS is still required when changing durable lease state.
    return lease


def acquire_bounded(
    store: LeaseStore, *, entity: int, owner: str, role: str,
    now: datetime, ttl: timedelta, max_active: int,
) -> Lease:
    """Bound claims using an atomic state-ref CAS, not an in-process mutex."""
    if type(max_active) is not int or not 1 <= max_active <= 32:
        raise ValueError("Invalid concurrent agent cap")
    if not hasattr(store, "read_all"):
        raise LeaseConflict("Global lease snapshot is required for admission")
    records = store.read_all()
    active = sum(lease.expires_at > now and lease.phase != "blocked"
                 and lease.entity != entity for lease in records.values())
    if active >= max_active:
        raise LeaseConflict("Concurrent agent limit reached")
    # Store.cas must use non-forced update from the immutable snapshot parent;
    # a concurrent claim to a distinct Issue rejects the losing CAS.
    return acquire(store, entity=entity, owner=owner, role=role, now=now, ttl=ttl)
