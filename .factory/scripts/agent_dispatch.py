#!/usr/bin/env python3
"""Trusted, owner-gated provider-neutral dispatch for durable Factory leases.

This controller is only invoked by a workflow_run child that checks out main.
It never evaluates Issue text as code and never initializes the production lease
ref. Missing configuration, credentials, lease state, or canary evidence fails
closed without dispatching work.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib import error, request
from urllib.parse import urlsplit

import yaml

from agent_dispatch_contract import DispatchDenied, dispatch
from github_ref_leases import GitHubRefLeaseStore, StateError
from lease_state import LeaseConflict, StaleLease, complete, acquire
from orchestrator_loop import inspect_open, plan_next
from repair_canary_proof import LiveRepairProofMissing, verify_live_repair_proof

ROOT = Path(__file__).resolve().parents[2]
PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{1,48}$")
SHA = re.compile(r"^[a-f0-9]{40}$")
RECEIPT = re.compile(r"^[A-Za-z0-9_.:/-]{1,256}$")


class NoRedirect(request.HTTPRedirectHandler):
    """Never forward a role-scoped credential to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubReadAPI:
    """Read-only facade for helpers that consume a minimal get(path) client."""

    def __init__(self, store: GitHubRefLeaseStore):
        self.store = store

    def get(self, path: str) -> dict:
        return self.store.call("GET", path)


class WebhookBackend:
    """Provider-neutral HTTPS gateway with durable idempotency-key semantics."""

    def __init__(self, endpoint: str, role_token: str, opener=None):
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.fragment):
            raise DispatchDenied("External backend endpoint must be a plain HTTPS URL")
        if not role_token or any(c in role_token for c in "\r\n"):
            raise DispatchDenied("Role-scoped backend credential is not configured")
        self.endpoint = endpoint
        self.role_token = role_token
        self.opener = opener or request.build_opener(NoRedirect())

    def submit(self, *, provider: str, envelope: dict) -> str:
        key = envelope.get("idempotency_key") if isinstance(envelope, dict) else None
        if not PROVIDER.fullmatch(provider) or not isinstance(key, str) or not re.fullmatch(
            r"[a-f0-9]{64}", key
        ):
            raise DispatchDenied("Invalid provider or idempotency envelope")
        body = json.dumps(
            {"provider": provider, "envelope": envelope},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        req = request.Request(
            self.endpoint, data=body, method="POST",
            headers={
                "Authorization": "Bearer " + self.role_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Idempotency-Key": key,
            },
        )
        try:
            with self.opener.open(req, timeout=15) as response:
                if response.status not in (200, 201, 202):
                    raise DispatchDenied("External backend did not accept dispatch")
                result = json.loads(response.read())
        except (error.HTTPError, error.URLError, TimeoutError, OSError, ValueError) as exc:
            # Never include response bodies, endpoint URLs, or credentials in logs.
            raise DispatchDenied("External backend dispatch was not verified") from exc
        receipt = result.get("receipt") if isinstance(result, dict) else None
        if (not isinstance(receipt, str) or not RECEIPT.fullmatch(receipt)
                or result.get("idempotency_key") != key):
            raise DispatchDenied("External backend returned an invalid receipt")
        return receipt


def _workflow_is_trusted(event: dict) -> bool:
    run = event.get("workflow_run") if isinstance(event, dict) else None
    return (
        isinstance(run, dict)
        and run.get("name") == "Factory orchestration diagnostics"
        and run.get("event") in {"issues", "schedule"}
        and run.get("head_branch") == "main"
        and run.get("conclusion") == "success"
    )


def main() -> int:
    if os.getenv("FACTORY_AGENT_DISPATCH_ENABLED") != "true":
        print(json.dumps({"status": "disabled", "reason": "owner_flag_off"}))
        return 0

    app_token = os.getenv("FACTORY_AGENT_DISPATCH_APP_TOKEN", "")
    provider = os.getenv("FACTORY_AGENT_PROVIDER", "")
    endpoint = os.getenv("FACTORY_AGENT_ENDPOINT", "")
    owner = os.getenv("FACTORY_AGENT_LOGIN", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    event_path = os.getenv("GITHUB_EVENT_PATH", "")
    if not all((app_token, provider, endpoint, owner, repo, event_path)):
        print(json.dumps({"status": "disabled", "reason": "required_owner_configuration_missing"}))
        return 0

    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        if not _workflow_is_trusted(event):
            print(json.dumps({"status": "disabled", "reason": "untrusted_trigger"}))
            return 0

        config = yaml.safe_load(
            (ROOT / ".factory/config.yaml").read_text(encoding="utf-8")
        )
        orchestration = config["orchestration"]
        if orchestration.get("enabled") is not True:
            print(json.dumps({"status": "disabled", "reason": "orchestration_flag_off"}))
            return 0
        approved = set(orchestration.get("approved_agent_logins") or [])
        providers = set(orchestration.get("agent_providers") or [])
        if owner not in approved or provider not in providers:
            print(json.dumps({"status": "disabled", "reason": "identity_or_provider_not_approved"}))
            return 0

        main_sha = event["workflow_run"].get("head_sha", "")
        if not SHA.fullmatch(main_sha):
            raise DispatchDenied("Trusted workflow has no immutable main SHA")
        store = GitHubRefLeaseStore(repo, app_token, write_enabled=True)
        now = datetime.now(timezone.utc)

        # An already-closed issue releases its active lease via the same CAS
        # state store. A truncated issue list or unreadable state never implies
        # that a lease is complete.
        items = inspect_open(repo, app_token)
        open_issues = {item["number"] for item in items if not item.get("is_pr")}
        leases = store.read_all()
        for number, lease in leases.items():
            if (number in open_issues or lease.phase in {"blocked", "completed"}
                    or lease.expires_at <= now):
                continue
            issue = store.call("GET", f"/issues/{number}")
            if issue.get("state") == "closed":
                try:
                    complete(
                        store, entity=number, epoch=lease.epoch,
                        owner=lease.owner, now=now,
                    )
                except (LeaseConflict, StaleLease, ValueError):
                    # Another trusted worker changed the revision; refresh below.
                    pass
        leases = store.read_all()

        # The external runtime must independently pass the live canary for the
        # exact current main SHA before any issue is claimed or dispatched.
        current = store.call("GET", "/branches/main").get("commit", {}).get("sha")
        if current != main_sha:
            print(json.dumps({"status": "idle", "reason": "main_moved_during_dispatch"}))
            return 0
        try:
            verify_live_repair_proof(GitHubReadAPI(store), main_sha)
        except LiveRepairProofMissing:
            print(json.dumps({"status": "disabled", "reason": "live_canary_not_verified"}))
            return 0

        plan = plan_next(
            items, leases, now=now,
            max_concurrent=orchestration["max_concurrent_agents"],
        )
        if plan is None:
            print(json.dumps({"status": "idle", "reason": "no_eligible_queue_item"}))
            return 0

        if plan.get("resume"):
            lease = leases.get(plan["issue"])
            if lease is None or lease.owner not in approved:
                print(json.dumps({"status": "disabled",
                                  "reason": "resume_lease_identity_not_approved"}))
                return 0
            dispatch_owner = lease.owner
            role = lease.role
        else:
            lease = None
            dispatch_owner = owner
            role = plan["role"]

        role_secret = "FACTORY_AGENT_TOKEN_" + role.upper().replace("-", "_")
        role_token = os.getenv(role_secret, "")
        if not role_token:
            print(json.dumps({"status": "disabled", "reason": "role_scoped_credential_missing"}))
            return 0
        transport = WebhookBackend(endpoint, role_token)

        if lease is None:
            lease = acquire(
                store, entity=plan["issue"], owner=dispatch_owner, role=role,
                now=now,
                ttl=timedelta(minutes=config["limits"]["lease_ttl_minutes"]),
            )
        receipt = dispatch(
            store=store, issue=plan["issue"], authenticated_login=dispatch_owner,
            role=role, approved_logins=approved, now=now,
            provider=provider, configured_providers=providers,
            transport=transport, enabled=True,
        )
        print(json.dumps({
            "status": "dispatched", "issue": lease.entity,
            "source_number": plan["source_number"], "kind": plan["kind"],
            "role": role, "epoch": lease.epoch, "revision": lease.revision,
            "receipt": receipt,
        }, sort_keys=True))
        return 0
    except LeaseConflict:
        print(json.dumps({"status": "idle", "reason": "lease_claim_conflict"}))
        return 0
    except (OSError, KeyError, TypeError, ValueError, error.HTTPError, StateError,
            DispatchDenied) as exc:
        print(json.dumps({
            "status": "blocked", "reason": type(exc).__name__,
        }), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
