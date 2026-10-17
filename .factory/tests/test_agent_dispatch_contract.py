import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lease_state import InMemoryLeaseStore, acquire, StaleLease
from agent_dispatch_contract import build_envelope, dispatch, fence_worker_write, DispatchDenied

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)
class Transport:
    def __init__(self): self.calls=[]
    def submit(self, *, provider, envelope):
        self.calls.append((provider,envelope))
        return "ack"
class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.store=InMemoryLeaseStore()
        self.lease=acquire(self.store,entity=7,owner="worker",role="developer",now=NOW,ttl=timedelta(minutes=5))
        self.transport=Transport()
    def test_provider_neutral_transport(self):
        self.assertEqual(dispatch(store=self.store,issue=7,authenticated_login="worker",role="developer",approved_logins={"worker"},now=NOW,provider="custom-provider",transport=self.transport,enabled=True),"ack")
        self.assertEqual(self.transport.calls[0][0],"custom-provider")
    def test_disabled_fails_closed(self):
        with self.assertRaises(DispatchDenied):
            dispatch(store=self.store,issue=7,authenticated_login="worker",role="developer",approved_logins={"worker"},now=NOW,provider="custom-provider",transport=self.transport,enabled=False)
        self.assertEqual(self.transport.calls,[])
    def test_unapproved_worker_rejected(self):
        with self.assertRaises(DispatchDenied):
            build_envelope(lease=self.lease,authenticated_login="attacker",expected_role="developer",approved_logins={"worker"},now=NOW)
    def test_wrong_role_rejected(self):
        with self.assertRaises(DispatchDenied):
            build_envelope(lease=self.lease,authenticated_login="worker",expected_role="integrator",approved_logins={"worker"},now=NOW)
    def test_expired_lease_rejected(self):
        with self.assertRaises(DispatchDenied):
            build_envelope(lease=self.lease,authenticated_login="worker",expected_role="developer",approved_logins={"worker"},now=NOW+timedelta(minutes=6))
    def test_stale_revision_cannot_write(self):
        with self.assertRaises(StaleLease):
            fence_worker_write(store=self.store,issue=7,epoch=self.lease.epoch,revision=0,authenticated_login="worker",role="developer",now=NOW,approved_logins={"worker"})
    def test_public_prompt_not_forwarded(self):
        envelope=build_envelope(lease=self.lease,authenticated_login="worker",expected_role="developer",approved_logins={"worker"},now=NOW)
        self.assertEqual(set(envelope.payload()),{"issue","epoch","revision","role","owner","branch","commit_sha","checkpoint","idempotency_key"})
if __name__ == "__main__":
    unittest.main()
