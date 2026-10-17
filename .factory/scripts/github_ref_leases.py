#!/usr/bin/env python3
"""Git ref compare-and-fast-forward implementation of the lease store protocol.

Deliberately does NOT create the state branch, dispatch an LLM, or enable the
orchestrator. Write capability is opt-in and must run only in trusted code.
"""
from __future__ import annotations

import base64
from dataclasses import asdict
from datetime import datetime
import json
import re
from urllib import error, request

from lease_state import Lease, LeaseStore

SHA = re.compile(r"^[a-f0-9]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class StateError(RuntimeError):
    pass


def serialize(lease: Lease) -> dict:
    record = asdict(lease)
    record["expires_at"] = lease.expires_at.isoformat()
    record["heartbeat_at"] = lease.heartbeat_at.isoformat()
    record["diff_hashes"] = list(lease.diff_hashes)
    return record


def deserialize(data: dict) -> Lease:
    try:
        if not isinstance(data, dict) or set(data) != {
            "entity", "epoch", "revision", "owner", "role", "phase",
            "expires_at", "heartbeat_at", "branch", "commit_sha",
            "attempts", "diff_hashes",
        }:
            raise StateError("Unexpected lease state fields")
        if any(type(data[k]) is not int or data[k] < 0
               for k in ("entity", "epoch", "revision", "attempts")):
            raise StateError("Invalid lease counters")
        if any(not isinstance(data[k], str) for k in ("owner", "role", "phase",
                                                      "branch", "commit_sha")):
            raise StateError("Invalid lease string values")
        expires = datetime.fromisoformat(data["expires_at"])
        heartbeat = datetime.fromisoformat(data["heartbeat_at"])
        if expires.tzinfo is None or heartbeat.tzinfo is None:
            raise StateError("Timestamps require explicit timezone")
        diffs = data["diff_hashes"]
        if not isinstance(diffs, list) or any(
            not isinstance(x, str) or len(x) != 64 for x in diffs
        ):
            raise StateError("Invalid checkpoint diff hashes")
        return Lease(
            entity=data["entity"], epoch=data["epoch"],
            revision=data["revision"], owner=data["owner"],
            role=data["role"], phase=data["phase"], expires_at=expires,
            heartbeat_at=heartbeat, branch=data["branch"],
            commit_sha=data["commit_sha"], attempts=data["attempts"],
            diff_hashes=tuple(diffs),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StateError("Malformed lease record") from exc


class GitHubRefLeaseStore:
    """Remote immutable-snapshot lease CAS using one Git branch as the lock."""

    FILE = ".factory/lease-state.json"

    def __init__(self, repo: str, token: str, *, branch: str = "factory-lease-state",
                 write_enabled: bool = False):
        if not REPO.fullmatch(repo) or not token:
            raise ValueError("Authenticated repository identity required")
        if not re.fullmatch(r"[a-zA-Z0-9_/-]+", branch) or branch.startswith("/"):
            raise ValueError("Unsafe lease branch")
        self.repo = repo
        self.token = token
        self.branch = branch
        self.write_enabled = write_enabled

    def call(self, method: str, path: str, payload: dict | None = None):
        if not path.startswith("/") or "://" in path:
            raise StateError("Unsafe GitHub API path")
        body = json.dumps(payload).encode() if payload is not None else None
        req = request.Request(
            f"https://api.github.com/repos/{self.repo}{path}",
            data=body, method=method, headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with request.urlopen(req, timeout=25) as response:
            data = response.read()
        return json.loads(data) if data else {}

    def snapshot(self):
        ref = self.call("GET", f"/git/ref/heads/{self.branch}")
        sha = ref.get("object", {}).get("sha")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise StateError("Missing valid immutable lease ref")
        commit = self.call("GET", f"/git/commits/{sha}")
        tree = commit.get("tree", {}).get("sha")
        if not isinstance(tree, str) or not SHA.fullmatch(tree):
            raise StateError("Missing immutable lease state tree")
        # Exact SHA, never moving branch ref, to avoid mismatched state reads.
        file = self.call("GET", f"/contents/{self.FILE}?ref={sha}")
        if file.get("encoding") != "base64":
            raise StateError("Missing/unsupported lease state object")
        # GitHub Contents API wraps base64 at newline boundaries.
        encoded = "".join(file["content"].split())
        decoded = base64.b64decode(encoded, validate=True)
        data = json.loads(decoded)
        if data.get("version") != 1 or not isinstance(data.get("leases"), dict):
            raise StateError("Unexpected versioned lease map")
        return sha, tree, data

    def initialize_isolated(self) -> bool:
        """Create a fresh orphan test ref only; never initialize production implicitly.

        Returns False when the exact isolated ref already exists. Leaves the
        write-disabled production branch untouched.
        """
        if not self.write_enabled or not re.fullmatch(
            r"factory-lease-canary-[1-9][0-9]*", self.branch
        ):
            raise StateError("Isolated canary write capability is not enabled")
        body = json.dumps({"version": 1, "leases": {}}, sort_keys=True)
        tree = self.call("POST", "/git/trees", {"tree": [{
            "path": self.FILE, "mode": "100644", "type": "blob",
            "content": body,
        }]})
        tree_sha = tree.get("sha")
        if not isinstance(tree_sha, str) or not SHA.fullmatch(tree_sha):
            raise StateError("Unable to initialize canary tree")
        commit = self.call("POST", "/git/commits", {
            "message": "factory: initialize isolated lease canary",
            "tree": tree_sha, "parents": [],
        })
        sha = commit.get("sha")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise StateError("Unable to initialize canary commit")
        try:
            self.call("POST", "/git/refs", {
                "ref": f"refs/heads/{self.branch}", "sha": sha,
            })
        except error.HTTPError as exc:
            if exc.code == 422:
                self.snapshot()  # Must be readable and structurally valid.
                return False
            raise
        return True

    def read_all(self) -> dict[int, Lease]:
        """Read a complete lease map from one immutable ref snapshot."""
        _, _, state = self.snapshot()
        if len(state["leases"]) > 10000:
            raise StateError("Lease capacity bound exceeded")
        leases = {}
        for raw, entry in state["leases"].items():
            if not isinstance(raw, str) or not re.fullmatch(r"[1-9][0-9]*", raw):
                raise StateError("Unsafe lease entity key")
            lease = deserialize(entry)
            if lease.entity != int(raw):
                raise StateError("Entity differs from lease map key")
            leases[int(raw)] = lease
        return leases

    def read(self, entity: int) -> Lease | None:
        if type(entity) is not int or entity < 1:
            raise ValueError("Invalid Issue identity")
        _, _, state = self.snapshot()
        record = state["leases"].get(str(entity))
        lease = deserialize(record) if record is not None else None
        if lease and lease.entity != entity:
            raise StateError("Lease entity mismatch")
        return lease

    def cas(self, entity: int, previous_revision: int, new: Lease) -> bool:
        if not self.write_enabled:
            raise StateError("Lease mutations disabled until owner activation")
        if type(entity) is not int or entity < 1 or new.entity != entity:
            raise ValueError("Invalid lease identity")
        previous_sha, tree_sha, state = self.snapshot()
        current = state["leases"].get(str(entity))
        previous = deserialize(current) if current else None
        current_revision = previous.revision if previous else 0
        if current_revision != previous_revision or new.revision != current_revision + 1:
            return False
        updated = dict(state)
        updated["leases"] = dict(state["leases"])
        updated["leases"][str(entity)] = serialize(new)
        body = json.dumps(updated, sort_keys=True, separators=(",", ":"))
        tree = self.call("POST", "/git/trees", {
            "base_tree": tree_sha,
            "tree": [{
                "path": self.FILE, "mode": "100644",
                "type": "blob", "content": body,
            }],
        })
        next_tree = tree.get("sha")
        if not isinstance(next_tree, str) or not SHA.fullmatch(next_tree):
            raise StateError("GitHub did not create an immutable tree")
        commit = self.call("POST", "/git/commits", {
            "message": f"factory: lease Issue #{entity} revision {new.revision}",
            "tree": next_tree, "parents": [previous_sha],
        })
        next_sha = commit.get("sha")
        if not isinstance(next_sha, str) or not SHA.fullmatch(next_sha):
            raise StateError("GitHub did not create lease snapshot commit")
        try:
            self.call("PATCH", f"/git/refs/heads/{self.branch}", {
                "sha": next_sha, "force": False,
            })
        except error.HTTPError as exc:
            if exc.code in (409, 422):
                return False
            raise
        return True
