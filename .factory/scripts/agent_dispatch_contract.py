"""Provider-neutral, fenced dispatch envelope and durable checkpoint contract.

External workers cannot gain GitHub permissions from an Issue prompt. A trusted
controller must separately authenticate a role identity, verify an active lease
and configure transport credentials outside this public repository.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Protocol

from lease_state import LeaseStore, Lease, StaleLease, authorize

SHA = re.compile(r"^[a-f0-9]{40}$")
ROLES = frozenset({"planner", "validator", "developer", "ci-engineer", "integrator"})


class DispatchDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class DispatchEnvelope:
    issue: int
    epoch: int
    revision: int
    role: str
    owner: str
    branch: str
    commit_sha: str
    checkpoint: str
    idempotency_key: str

    def payload(self) -> dict:
        return {
            "issue": self.issue, "epoch": self.epoch,
            "revision": self.revision, "role": self.role,
            "owner": self.owner, "branch": self.branch,
            "commit_sha": self.commit_sha, "checkpoint": self.checkpoint,
            "idempotency_key": self.idempotency_key,
        }


class Backend(Protocol):
    """External gateway contract.

    Implementations must durably deduplicate by envelope["idempotency_key"].
    Repeated submissions with the same key return the original receipt and
    must not create a second worker, branch, pull request, or status update.
    """
    def submit(self, *, provider: str, envelope: dict) -> str: ...


def build_envelope(
    *, lease: Lease, authenticated_login: str, expected_role: str,
    approved_logins: set[str], now: datetime,
) -> DispatchEnvelope:
    if expected_role not in ROLES:
        raise DispatchDenied("Role not permitted for dispatch")
    if not authorize(lease, user=authenticated_login,
                     epoch=lease.epoch, role=expected_role,
                     now=now, approved_logins=approved_logins):
        raise DispatchDenied("Identity and lease fencing required")
    if lease.phase not in ("claimed", "repairing"):
        raise DispatchDenied("Worker lease is not runnable")
    if lease.branch and not lease.branch.startswith("factory/"):
        raise DispatchDenied("Worker branch is outside allowed namespace")
    if lease.commit_sha and not SHA.fullmatch(lease.commit_sha):
        raise DispatchDenied("Checkpoint SHA invalid")
    item = {
        "issue": lease.entity, "epoch": lease.epoch,
        "revision": lease.revision, "role": lease.role,
        "owner": lease.owner, "branch": lease.branch,
        "commit_sha": lease.commit_sha,
    }
    key = hashlib.sha256(json.dumps(
        item, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    return DispatchEnvelope(
        issue=lease.entity, epoch=lease.epoch, revision=lease.revision,
        role=lease.role, owner=lease.owner, branch=lease.branch,
        commit_sha=lease.commit_sha, checkpoint=lease.commit_sha,
        idempotency_key=key,
    )


def dispatch(
    *, store: LeaseStore, issue: int, authenticated_login: str,
    role: str, approved_logins: set[str], now: datetime,
    provider: str, configured_providers: set[str],
    transport: Backend, enabled: bool,
) -> str:
    """Dispatch only via a trusted injected transport, never from Issue text."""
    if not enabled:
        raise DispatchDenied("Autonomous dispatch is not enabled by the owner")
    if (not re.fullmatch(r"[a-z][a-z0-9_-]{1,48}", provider)
            or not isinstance(configured_providers, set)
            or not configured_providers
            or any(not isinstance(item, str)
                   or not re.fullmatch(r"[a-z][a-z0-9_-]{1,48}", item)
                   for item in configured_providers)
            or provider not in configured_providers):
        raise DispatchDenied("Provider is not in the owner-configured allowlist")
    lease = store.read(issue)
    if lease is None:
        raise DispatchDenied("No acquired durable lease")
    envelope = build_envelope(
        lease=lease, authenticated_login=authenticated_login,
        expected_role=role, approved_logins=approved_logins, now=now,
    )
    result = transport.submit(provider=provider, envelope=envelope.payload())
    if not isinstance(result, str) or not result:
        raise DispatchDenied("Transport did not acknowledge dispatch")
    return result


def fence_worker_write(
    *, store: LeaseStore, issue: int, epoch: int, revision: int,
    authenticated_login: str, role: str, now: datetime,
    approved_logins: set[str],
) -> None:
    """Called immediately before an owner's privileged mutation on GitHub."""
    lease = store.read(issue)
    if not lease or lease.epoch != epoch or lease.revision != revision:
        raise StaleLease("Worker envelope is stale after lease takeover")
    build_envelope(
        lease=lease, authenticated_login=authenticated_login,
        expected_role=role, approved_logins=approved_logins, now=now,
    )
