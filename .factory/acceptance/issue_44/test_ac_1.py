"""Claim race on two independent API clients backed by one isolated ref."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
from threading import Barrier,Lock
import unittest
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from github_ref_leases import GitHubRefLeaseStore
from lease_state import acquire,LeaseConflict
from lease_canary_proof import verify_live_lease_canary,HostedLeaseCanaryMissing

class Remote:
    def __init__(self):
        self.ref="a"*40
        self.states={self.ref:{"version":1,"leases":{}}}
        self.derived={}
        self.index=0
        self.lock=Lock()
        self.barrier=Barrier(2,timeout=10)
    def call(self,method,path,payload=None):
        if method=="GET" and path=="/git/ref/heads/factory-lease-canary-900":
            with self.lock: sha=self.ref
            self.barrier.wait()
            return {"object":{"sha":sha}}
        if method=="GET" and path.startswith("/git/commits/"):
            return {"tree":{"sha":"b"*40}}
        if method=="GET" and path.startswith("/contents/"):
            sha=path.split("ref=")[1]
            state=self.states[sha]
            return {"encoding":"base64","content":base64.b64encode(json.dumps(state).encode()).decode()}
        if method=="POST" and path=="/git/trees":
            with self.lock:
                self.index+=1; key=f"{self.index:040x}"
                self.derived[key]=json.loads(payload["tree"][0]["content"])
            return {"sha":key}
        if method=="POST" and path=="/git/commits":
            with self.lock:
                self.index+=1; sha=f"{self.index:040x}"
                self.derived[sha]=(payload["parents"][0],self.derived[payload["tree"]])
            return {"sha":sha}
        if method=="PATCH" and path=="/git/refs/heads/factory-lease-canary-900":
            self_ref=self
            with self.lock:
                parent,state=self.derived[payload["sha"]]
                if payload["force"] is not False or self_ref.ref!=parent:
                    raise HTTPError("https://api.github.com",422,"non-fast-forward",{},None)
                self.states[payload["sha"]]=state
                self.ref=payload["sha"]
            return {"object":{"sha":payload["sha"]}}
        raise AssertionError((method,path))

class Client(GitHubRefLeaseStore):
    def __init__(self,remote):
        super().__init__("shpalac/insurance","fake",branch="factory-lease-canary-900",write_enabled=True)
        self.remote=remote
    def call(self,method,path,payload=None):
        return self.remote.call(method,path,payload)

class Acceptance(unittest.TestCase):
    def test_ac_1_two_clients_one_nonforced_winner(self):
        remote=Remote()
        now=datetime(2026,10,18,tzinfo=timezone.utc)
        def claim(name):
            try:
                return acquire(Client(remote),entity=900,owner=name,role="developer",
                               now=now,ttl=timedelta(minutes=30))
            except LeaseConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(claim,("one","two")))
        self.assertEqual(sum(x is not None for x in results),1)
        self.assertEqual(len(remote.states[remote.ref]["leases"]),1)
        self.assertEqual(remote.states[remote.ref]["leases"]["900"]["revision"],1)
        workflow=(ROOT/".github/workflows/factory-lease-canary.yml").read_text()
        self.assertIn("matrix:",workflow)
        self.assertIn("contender: [one, two]",workflow)
        self.assertIn("verify-single-winner:",workflow)
        class MissingAPI:
            def get(self,path):return {"total_count":0,"workflow_runs":[]}
        with self.assertRaises(HostedLeaseCanaryMissing):
            verify_live_lease_canary(MissingAPI(),"a"*40)
