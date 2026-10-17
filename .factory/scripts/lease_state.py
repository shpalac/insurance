#!/usr/bin/env python3
"""Lease state machine for an external, role-assigned LLM dispatcher.

State is durable in GitHub. CAS implementations MUST reject stale revisions
and use a non-force fast-forward of a dedicated state branch. Local tests use
an atomic in-memory adapter; no agent code or GitHub mutations occur here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
from threading import Lock
from typing import Protocol


class LeaseConflict(RuntimeError):
    pass


class StaleLease(RuntimeError):
    pass


@dataclass(frozen=True)
class Lease:
    entity: int
    epoch: int
    revision: int
    owner: str
    role: str
    phase: str
    expires_at: datetime
    heartbeat_at: datetime
    branch: str = ""
    commit_sha: str = ""
    attempts: int = 0
    diff_hashes: tuple[str, ...] = ()


class LeaseStore(Protocol):
    def read(self, entity: int) -> Lease | None: ...
    def cas(self, entity: int, previous_revision: int, new: Lease) -> bool: ...


class InMemoryLeaseStore:
    """Atomic reference implementation for deterministic concurrency tests."""

    def __init__(self):
        self._states: dict[int, Lease] = {}
        self._lock = Lock()

    def read(self, entity: int) -> Lease | None:
        with self._lock:
            return self._states.get(entity)

    def cas(self, entity: int, previous_revision: int, new: Lease) -> bool:
        with self._lock:
            previous = self._states.get(entity)
            revision = previous.revision if previous else 0
            if revision != previous_revision or new.revision != revision + 1:
                return False
            self._states[entity] = new
            return True


def acquire(
    store: LeaseStore, *, entity: int, owner: str, role: str,
    now: datetime, ttl: timedelta,
) -> Lease:
    if entity < 1 or not owner or role not in {
        "planner", "validator", "developer", "reviewer",
        "ci-engineer", "integrator", "maintainer"
    }:
        raise ValueError("Invalid lease identity or role")
    if now.tzinfo is None or ttl.total_seconds() <= 0:
        raise ValueError("UTC-aware now and positive TTL required")
    current = store.read(entity)
    if current is not None and current.phase == "blocked":
        raise LeaseConflict("Blocked lease requires independent replan")
    if current is not None and current.expires_at > now:
        raise LeaseConflict(f"Active lease held by {current.owner}")
    previous_revision = current.revision if current else 0
    new = Lease(
        entity=entity, epoch=(current.epoch + 1 if current else 1),
        revision=previous_revision + 1, owner=owner, role=role,
        phase="claimed", expires_at=now + ttl, heartbeat_at=now,
        branch=(current.branch if current else ""),
        commit_sha=(current.commit_sha if current else ""),
        attempts=(current.attempts if current else 0),
        diff_hashes=(current.diff_hashes if current else ()),
    )
    if not store.cas(entity, previous_revision, new):
        raise LeaseConflict("Concurrent lease revision lost compare-and-swap")
    return new


def _require_current(
    store: LeaseStore, *, entity: int, epoch: int, owner: str, now: datetime
) -> Lease:
    current = store.read(entity)
    if (current is None or current.epoch != epoch
            or current.owner != owner or current.expires_at <= now
            or current.phase == "blocked"):
        raise StaleLease("Worker lease expired, transferred, or revoked")
    return current


def heartbeat(
    store: LeaseStore, *, entity: int, epoch: int, owner: str,
    now: datetime, ttl: timedelta,
) -> Lease:
    current = _require_current(
        store, entity=entity, epoch=epoch, owner=owner, now=now
    )
    new = replace(
        current, revision=current.revision + 1,
        heartbeat_at=now, expires_at=now + ttl
    )
    if not store.cas(entity, current.revision, new):
        raise StaleLease("Heartbeat lost CAS race")
    return new


def checkpoint(
    store: LeaseStore, *, entity: int, epoch: int, owner: str,
    now: datetime, branch: str, sha: str, diff: str,
    max_repairs: int = 3,
) -> Lease:
    current = _require_current(
        store, entity=entity, epoch=epoch, owner=owner, now=now
    )
    if not branch.startswith("factory/"):
        raise ValueError("Only factory branches may be assigned")
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Checkpoint requires a full SHA-1 commit reference")
    normalized_hash = hashlib.sha256(
        diff.strip().encode("utf-8")
    ).hexdigest()
    repeated = normalized_hash in current.diff_hashes
    attempts = current.attempts + 1
    blocked = repeated or attempts >= max_repairs
    new = replace(
        current, revision=current.revision + 1,
        branch=branch, commit_sha=sha, attempts=attempts,
        phase=("blocked" if blocked else "repairing"),
        diff_hashes=(*current.diff_hashes, normalized_hash),
    )
    if not store.cas(entity, current.revision, new):
        raise StaleLease("Checkpoint lost CAS race")
    return new


def authorize(
    lease: Lease, *, user: str, epoch: int, role: str,
    now: datetime, approved_logins: set[str],
) -> bool:
    """An assignment envelope is not itself proof of authenticated identity."""
    return (
        user in approved_logins and user == lease.owner
        and epoch == lease.epoch and role == lease.role
        and lease.expires_at > now and lease.phase != "blocked"
    )
