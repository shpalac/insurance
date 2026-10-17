"""AC-6: dispatch uses an injected provider-neutral backend."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from lease_state import InMemoryLeaseStore, acquire
from agent_dispatch_contract import dispatch, DispatchDenied
NOW=datetime(2026,10,17,tzinfo=timezone.utc)

class Transport:
    def __init__(self): self.calls=[]
    def submit(self,*,provider,envelope):
        self.calls.append((provider,envelope))
        return "ack"

class ProviderNeutralAcceptance(unittest.TestCase):
    def test_ac_6_custom_provider_is_injected_without_provider_specific_sdk(self):
        store=InMemoryLeaseStore()
        acquire(store,entity=7,owner="worker",role="developer",now=NOW,ttl=timedelta(minutes=5))
        transport=Transport()
        result=dispatch(store=store,issue=7,authenticated_login="worker",role="developer",approved_logins={"worker"},now=NOW,provider="custom-provider",transport=transport,enabled=True)
        self.assertEqual(result,"ack")
        self.assertEqual(transport.calls[0][0],"custom-provider")

    def test_ac_6_dispatch_disabled_until_owner_enables_it(self):
        store=InMemoryLeaseStore()
        acquire(store,entity=7,owner="worker",role="developer",now=NOW,ttl=timedelta(minutes=5))
        transport=Transport()
        with self.assertRaises(DispatchDenied):
            dispatch(store=store,issue=7,authenticated_login="worker",role="developer",approved_logins={"worker"},now=NOW,provider="custom-provider",transport=transport,enabled=False)
        self.assertEqual(transport.calls,[])
