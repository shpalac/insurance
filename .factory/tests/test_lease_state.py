"""CAS lease collision, fencing, recovery and oscillation regression tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from lease_state import (  # noqa: E402
    InMemoryLeaseStore, LeaseConflict, StaleLease,
    acquire, authorize, checkpoint, heartbeat,
)
from orchestrator_loop import prioritize  # noqa: E402

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)
TTL = timedelta(minutes=30)


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryLeaseStore()

    def take(self, owner="developer-a", now=NOW):
        return acquire(
            self.store, entity=142, owner=owner,
            role="developer", now=now, ttl=TTL,
        )

    def test_first_claim_fences_second(self):
        lease = self.take()
        self.assertEqual(lease.epoch, 1)
        with self.assertRaises(LeaseConflict):
            self.take("developer-b")

    def test_concurrent_claim_has_one_winner(self):
        def claim(agent):
            try:
                return self.take(agent)
            except LeaseConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(claim, ("a", "b")))
        self.assertEqual(sum(value is not None for value in responses), 1)

    def test_expired_lease_recovers_with_higher_epoch(self):
        first = self.take()
        second = self.take("developer-b", now=NOW + TTL + timedelta(seconds=1))
        self.assertEqual(second.epoch, first.epoch + 1)

    def test_stale_heartbeat_is_rejected(self):
        first = self.take()
        self.take("developer-b", now=NOW + TTL + timedelta(seconds=1))
        with self.assertRaises(StaleLease):
            heartbeat(
                self.store, entity=142, epoch=first.epoch,
                owner=first.owner, now=NOW + TTL + timedelta(seconds=2),
                ttl=TTL,
            )

    def test_valid_heartbeat_extends_expiry(self):
        first = self.take()
        updated = heartbeat(
            self.store, entity=142, epoch=first.epoch,
            owner=first.owner, now=NOW + timedelta(minutes=5), ttl=TTL,
        )
        self.assertGreater(updated.expires_at, first.expires_at)

    def test_checkpoint_keeps_branch_when_lease_transfers(self):
        first = self.take()
        saved = checkpoint(
            self.store, entity=142, epoch=first.epoch,
            owner=first.owner, now=NOW, branch="factory/issue-142",
            sha="a" * 40, diff="first patch",
        )
        resumed = self.take("developer-b", now=NOW + TTL + timedelta(seconds=1))
        self.assertEqual(resumed.branch, saved.branch)
        self.assertEqual(resumed.commit_sha, saved.commit_sha)

    def test_same_diff_hash_blocks_oscillation(self):
        lease = self.take()
        first = checkpoint(
            self.store, entity=142, epoch=lease.epoch,
            owner=lease.owner, now=NOW, branch="factory/issue-142",
            sha="a" * 40, diff="one",
        )
        second = checkpoint(
            self.store, entity=142, epoch=lease.epoch,
            owner=lease.owner, now=NOW, branch="factory/issue-142",
            sha="b" * 40, diff="one",
        )
        self.assertEqual(first.phase, "repairing")
        self.assertEqual(second.phase, "blocked")

    def test_budget_blocks_fourth_attempt(self):
        lease = self.take()
        for idx in range(4):
            current = checkpoint(
                self.store, entity=142, epoch=lease.epoch,
                owner=lease.owner, now=NOW, branch="factory/issue-142",
                sha="a" * 40, diff=str(idx),
            )
        self.assertEqual(current.phase, "blocked")

    def test_allowlist_and_identity_are_enforced(self):
        lease = self.take()
        self.assertTrue(authorize(
            lease, user=lease.owner, epoch=lease.epoch, role=lease.role,
            now=NOW, approved_logins={lease.owner},
        ))
        self.assertFalse(authorize(
            lease, user="attacker", epoch=lease.epoch, role=lease.role,
            now=NOW, approved_logins={lease.owner},
        ))
        self.assertFalse(authorize(
            lease, user=lease.owner, epoch=0, role=lease.role,
            now=NOW, approved_logins={lease.owner},
        ))

    def test_prioritize_failing_pr_before_ready_issue(self):
        ordered = prioritize([
            {"kind": "ready-issue", "number": 2},
            {"kind": "failing-pr", "number": 7},
            {"kind": "main-regression", "number": 10},
        ])
        self.assertEqual([x["number"] for x in ordered], [10, 7, 2])


if __name__ == "__main__":
    unittest.main()
