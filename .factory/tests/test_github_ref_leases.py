"""GitHub CAS state is immutable, non-forcing and fenced under test."""

import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from github_ref_leases import (
    GitHubRefLeaseStore, StateError, serialize, deserialize,
)
from lease_state import Lease, acquire, LeaseConflict

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)
TTL = timedelta(minutes=30)
OLD = "a" * 40
TREE = "b" * 40
NEW_TREE = "c" * 40
NEW = "d" * 40


class MockGitHubStore(GitHubRefLeaseStore):
    def __init__(self):
        super().__init__("shpalac/insurance", "dummy", write_enabled=True)
        self.ref = OLD
        self.state = {"version": 1, "leases": {}}
        self.actions = []
        self.conflict = False

    def call(self, method, path, payload=None):
        self.actions.append((method, path, payload))
        if method == "GET" and path == "/git/ref/heads/factory-lease-state":
            return {"object": {"sha": self.ref}}
        if method == "GET" and path.startswith("/git/commits/"):
            return {"tree": {"sha": TREE}}
        if method == "GET" and path.startswith("/contents/"):
            return {"encoding": "base64", "content": base64.b64encode(
                json.dumps(self.state).encode()
            ).decode()}
        if method == "POST" and path == "/git/trees":
            self.staged = json.loads(payload["tree"][0]["content"])
            return {"sha": NEW_TREE}
        if method == "POST" and path == "/git/commits":
            if payload["parents"] != [OLD]:
                raise AssertionError("Stale parent")
            return {"sha": NEW}
        if method == "PATCH" and path.startswith("/git/refs/heads/"):
            if payload["force"] is not False:
                raise AssertionError("Force update prohibited")
            if self.conflict:
                raise HTTPError("https://example.com", 422, "non-fast-forward", {}, None)
            self.state = self.staged
            self.ref = NEW
            return {"object": {"sha": NEW}}
        raise AssertionError((method, path))


class GitHubLeaseTests(unittest.TestCase):
    def example(self, revision=1):
        return Lease(
            entity=142, epoch=1, revision=revision, owner="developer-1",
            role="developer", phase="claimed",
            expires_at=NOW + TTL, heartbeat_at=NOW,
        )

    def test_round_trip_lease_state_without_losing_fence(self):
        initial = self.example()
        self.assertEqual(deserialize(serialize(initial)), initial)
        broken = serialize(initial)
        broken["expires_at"] = "2026-10-17T11:30:00"
        with self.assertRaises(StateError):
            deserialize(broken)

    def test_first_acquisition_uses_exact_parent_and_nonforced_ref(self):
        store = MockGitHubStore()
        result = acquire(store, entity=142, owner="developer-1",
                         role="developer", now=NOW, ttl=TTL)
        self.assertEqual(result.revision, 1)
        self.assertEqual(store.read(142), result)
        updates = [action for action in store.actions if action[0] == "PATCH"]
        self.assertEqual(len(updates), 1)
        self.assertFalse(updates[0][2]["force"])

    def test_revision_mismatch_rejected_without_mutating_remote(self):
        store = MockGitHubStore()
        self.assertFalse(store.cas(142, 9, self.example()))
        self.assertFalse(any(a[0] == "POST" for a in store.actions))

    def test_remote_nonfastforward_race_fails_cas(self):
        store = MockGitHubStore()
        store.conflict = True
        self.assertFalse(store.cas(142, 0, self.example()))
        self.assertNotIn("142", store.state["leases"])

    def test_write_disabled_by_default(self):
        store = GitHubRefLeaseStore("shpalac/insurance", "dummy")
        with self.assertRaises(StateError):
            store.cas(142, 0, self.example())


if __name__ == "__main__":
    unittest.main()
