"""AC-1: authenticated, idempotent provider-neutral dispatch."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from agent_dispatch import WebhookBackend
from agent_dispatch_contract import DispatchDenied, dispatch
from lease_state import InMemoryLeaseStore, acquire, heartbeat

def emit():
    path = ROOT / "reports" / "ac-1.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", tests="1", failures="0", errors="0",
                       skipped="0", assertions="21")
    ET.SubElement(suite, "testcase", classname="Issue45AC1",
                  name="test_ac_1_dispatch_is_allowlisted_and_idempotent")
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)

class FakeBackend:
    def __init__(self):
        self.attempts = 0
        self.accepted = {}

    def submit(self, *, provider, envelope):
        self.attempts += 1
        key = envelope["idempotency_key"]
        if key not in self.accepted:
            self.accepted[key] = (provider, dict(envelope))
        return "receipt-" + key[:12]

class FakeResponse:
    status = 202

    def __init__(self, value):
        self.value = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.value

class FakeOpener:
    def __init__(self):
        self.request = None

    def open(self, req, timeout):
        self.request = req
        payload = json.loads(req.data)
        return FakeResponse({
            "receipt": "receipt-http-1",
            "idempotency_key": payload["envelope"]["idempotency_key"],
        })

class Acceptance(unittest.TestCase):
    def test_ac_1_dispatch_is_allowlisted_and_idempotent(self):
        now = datetime(2026, 10, 18, tzinfo=timezone.utc)
        store = InMemoryLeaseStore()
        acquire(store, entity=45, owner="approved-worker", role="planner",
                now=now, ttl=timedelta(minutes=30))
        backend = FakeBackend()
        kwargs = {
            "store": store, "issue": 45,
            "authenticated_login": "approved-worker", "role": "planner",
            "approved_logins": {"approved-worker"}, "now": now,
            "provider": "generic_gateway",
            "configured_providers": {"generic_gateway"},
            "transport": backend, "enabled": True,
        }
        first = dispatch(**kwargs)
        heartbeat(store, entity=45, epoch=1, owner="approved-worker",
                  now=now + timedelta(minutes=1), ttl=timedelta(minutes=30))
        kwargs["now"] = now + timedelta(minutes=1)
        second = dispatch(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(backend.attempts, 2)
        self.assertEqual(len(backend.accepted), 1)
        provider, envelope = next(iter(backend.accepted.values()))
        self.assertEqual(provider, "generic_gateway")
        self.assertEqual(envelope["issue"], 45)
        self.assertEqual(envelope["role"], "planner")
        self.assertEqual(envelope["owner"], "approved-worker")
        self.assertEqual(len(envelope["idempotency_key"]), 64)
        self.assertNotIn("role_token", envelope)
        with self.assertRaises(DispatchDenied):
            dispatch(**dict(kwargs, provider="unconfigured_provider"))
        with self.assertRaises(DispatchDenied):
            dispatch(**dict(kwargs, configured_providers=set()))
        with self.assertRaises(DispatchDenied):
            dispatch(**dict(kwargs, enabled=False))
        self.assertEqual(backend.attempts, 2)

        opener = FakeOpener()
        role_token = "role-scoped-secret"
        receipt = WebhookBackend(
            "https://gateway.example.test/dispatch", role_token, opener=opener
        ).submit(provider="generic_gateway", envelope=envelope)
        self.assertEqual(receipt, "receipt-http-1")
        self.assertEqual(opener.request.get_header("Authorization"),
                         "Bearer " + role_token)
        self.assertEqual(opener.request.get_header("Idempotency-key"),
                         envelope["idempotency_key"])
        self.assertNotIn(role_token.encode(), opener.request.data)
        with self.assertRaises(DispatchDenied):
            WebhookBackend("http://gateway.example.test/dispatch", role_token)
        with self.assertRaises(DispatchDenied):
            WebhookBackend("https://gateway.example.test/dispatch", "")
        config = yaml.safe_load((ROOT / ".factory/config.yaml").read_text())
        self.assertFalse(config["orchestration"]["enabled"])
        self.assertEqual(config["orchestration"]["agent_providers"], [])
        emit()

if __name__ == "__main__":
    unittest.main()
