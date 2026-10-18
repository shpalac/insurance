"""AC-2: resume from immutable lease checkpoints without duplicate claims."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from agent_dispatch_contract import build_envelope
from github_ref_leases import deserialize, serialize
from lease_state import (
    InMemoryLeaseStore, LeaseConflict, StaleLease, acquire, checkpoint, complete, heartbeat,
)

SHA = "a" * 40
UPDATED_SHA = "b" * 40

def emit():
    path = ROOT / "reports" / "ac-2.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", tests="1", failures="0", errors="0",
                       skipped="0", assertions="13")
    ET.SubElement(suite, "testcase", classname="Issue45AC2",
                  name="test_ac_2_checkpoint_survives_resume_and_completion_is_once")
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)

class Acceptance(unittest.TestCase):
    def test_ac_2_checkpoint_survives_resume_and_completion_is_once(self):
        now = datetime(2026, 10, 18, tzinfo=timezone.utc)
        store = InMemoryLeaseStore()
        first = acquire(store, entity=45, owner="approved-worker", role="developer",
                        now=now, ttl=timedelta(minutes=30))
        saved = checkpoint(
            store, entity=45, epoch=first.epoch, owner=first.owner, now=now,
            branch="factory/issue-45-worker", sha=SHA, diff="initial safe patch",
        )

        before_heartbeat = build_envelope(
            lease=saved, authenticated_login="approved-worker",
            expected_role="developer", approved_logins={"approved-worker"},
            now=now + timedelta(seconds=30),
        )
        renewed = heartbeat(
            store, entity=45, epoch=saved.epoch, owner=saved.owner,
            now=now + timedelta(minutes=1), ttl=timedelta(minutes=30),
        )
        checkpointed = checkpoint(
            store, entity=45, epoch=saved.epoch, owner=saved.owner,
            now=now + timedelta(minutes=1, seconds=30),
            branch="factory/issue-45-worker", sha=UPDATED_SHA,
            diff="second safe patch",
        )

        # Simulate a new controller process loading the exact durable snapshot.
        restored = deserialize(serialize(store.read(45)))
        self.assertEqual(restored.revision, checkpointed.revision)
        self.assertEqual(restored.epoch, saved.epoch)
        self.assertEqual(restored.branch, "factory/issue-45-worker")
        self.assertEqual(restored.commit_sha, UPDATED_SHA)
        envelope = build_envelope(
            lease=restored, authenticated_login="approved-worker",
            expected_role="developer", approved_logins={"approved-worker"},
            now=now + timedelta(minutes=2),
        )
        self.assertEqual(envelope.checkpoint, UPDATED_SHA)
        self.assertEqual(envelope.branch, "factory/issue-45-worker")
        self.assertEqual(envelope.commit_sha, UPDATED_SHA)
        self.assertEqual(envelope.idempotency_key, before_heartbeat.idempotency_key)
        self.assertGreater(envelope.revision, before_heartbeat.revision)
        with self.assertRaises(LeaseConflict):
            acquire(store, entity=45, owner="second-worker", role="developer",
                    now=now + timedelta(minutes=2), ttl=timedelta(minutes=30))

        finished = complete(
            store, entity=45, epoch=saved.epoch, owner=saved.owner,
            now=now + timedelta(minutes=3),
        )
        self.assertEqual(finished.phase, "completed")
        self.assertEqual(store.read_all()[45].phase, "completed")
        with self.assertRaises(StaleLease):
            complete(
                store, entity=45, epoch=saved.epoch, owner=saved.owner,
                now=now + timedelta(minutes=3),
            )
        emit()

if __name__ == "__main__":
    unittest.main()
