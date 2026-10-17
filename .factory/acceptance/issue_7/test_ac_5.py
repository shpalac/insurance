"""AC-5: public Issue prompt text is never executed or forwarded as a command."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from lease_state import InMemoryLeaseStore, acquire
from agent_dispatch_contract import build_envelope
from validate_issue_manifest import _safe_command
NOW=datetime(2026,10,17,tzinfo=timezone.utc)

class PromptInjectionAcceptance(unittest.TestCase):
    def test_ac_5_shell_injection_in_illustrative_command_is_rejected(self):
        self.assertFalse(_safe_command("python -m unittest; echo injected"))
        self.assertFalse(_safe_command("python -c print(secret)"))

    def test_ac_5_dispatch_payload_contains_only_fenced_checkpoint_fields(self):
        store=InMemoryLeaseStore()
        lease=acquire(store,entity=7,owner="worker",role="developer",now=NOW,ttl=timedelta(minutes=5))
        envelope=build_envelope(lease=lease,authenticated_login="worker",expected_role="developer",approved_logins={"worker"},now=NOW)
        self.assertEqual(set(envelope.payload()),{"issue","epoch","revision","role","owner","branch","commit_sha","checkpoint","idempotency_key"})
        self.assertNotIn("prompt",envelope.payload())
