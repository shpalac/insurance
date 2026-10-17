#!/usr/bin/env python3
"""Trusted-main GitHub-only CI repair scheduler, explicitly disabled by default.

This controller never executes Issue/PR instructions, modifies tests, pushes
branches or merges. Only an authorized external backend can act on its
SHA/epoch-bound repository_dispatch envelope after durable lease CAS.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib import error

import yaml
from github_ref_leases import GitHubRefLeaseStore
from lease_fencing import WorkerProof
from repair_recovery import identify_failure, reserve_repair
from repair_canary_proof import LiveRepairProofMissing, verify_live_repair_proof
from pr_merge_coordinator import API

ROOT = Path(__file__).resolve().parents[2]
REF = re.compile(r"(?m)^Refs #([1-9][0-9]*)\s*$")


def main() -> int:
    if (os.getenv("FACTORY_REPAIR_ENABLED") != "true"
            or not os.getenv("FACTORY_REPAIR_APP_TOKEN")):
        print(json.dumps({"status": "disabled",
            "reason": "Owner-controlled CI repair backend or App token not enabled"}))
        return 0
    try:
        config = yaml.safe_load((ROOT/".factory/config.yaml").read_text())
        if config["orchestration"]["enabled"] is not True:
            raise ValueError("Factory orchestration is not approved")
        allowed = set(config["orchestration"].get("approved_agent_logins") or [])
        if not allowed:
            raise ValueError("No authorized agent identity")
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        run = event["workflow_run"]
        if run.get("name") != "Factory selective CI" or                 run.get("event") != "pull_request" or run.get("conclusion") != "failure":
            return 0
        refs = run.get("pull_requests") or []
        if len(refs) != 1:
            raise ValueError("Ambiguous candidate PR")
        repo = os.environ["GITHUB_REPOSITORY"]
        api = API(repo, os.environ["FACTORY_REPAIR_APP_TOKEN"])
        # Fail closed until every prerequisite and this controller are audited
        # and fully integrated on the protected default branch.
        for prerequisite in (43,44,45,46):
            if api.get(f"/issues/{prerequisite}").get("state") != "closed":
                print("DISABLED: repair factory prerequisites are not complete")
                return 0
        main_sha = api.get("/branches/main")["commit"]["sha"]
        try:
            verify_live_repair_proof(api, main_sha)
        except LiveRepairProofMissing:
            print(json.dumps({"status": "disabled",
                              "reason": "live_repair_canary_not_verified"}))
            return 0
        pr = api.get(f"/pulls/{refs[0]['number']}")
        if ((pr.get("head",{}).get("repo") or {}).get("full_name","").lower()
                != repo.lower()):
            raise ValueError("Untrusted fork PR")
        issue_refs = REF.findall(pr.get("body") or "")
        if len(issue_refs) != 1:
            raise ValueError("Repair dispatch requires one unambiguous Issue")
        issue = int(issue_refs[0])
        jobs = api.get(f"/actions/runs/{run['id']}/jobs?per_page=100")
        if jobs.get("total_count",101) > 100:
            raise ValueError("Truncated failure evidence")
        store = GitHubRefLeaseStore(repo, os.environ["FACTORY_REPAIR_APP_TOKEN"],
                                   write_enabled=True)
        lease = store.read(issue)
        if lease is None or lease.role != "ci-engineer":
            raise ValueError("CI repair role lease not available")
        decision = identify_failure(
            run=run,jobs=jobs["jobs"],pr=pr,
            attempts=lease.attempts)
        if decision.action != "dispatch":
            print(json.dumps({"status":"blocked","reason":decision.reason}))
            return 0
        fence = WorkerProof(issue,lease.epoch,lease.revision,lease.owner,
                            lease.role,lease.branch,lease.commit_sha)
        reserved = reserve_repair(
            store,proof=fence,result=decision,
            authenticated_login=lease.owner,approved_logins=allowed,
            now=datetime.now(timezone.utc))
        payload = {"issue":issue,"run_id":decision.run_id,
                   "head_sha":decision.sha,"failed_jobs":list(decision.failed_jobs),
                   "idempotency_key":decision.idempotency_key,
                   "epoch":reserved.epoch,"revision":reserved.revision,
                   "branch":reserved.branch,"role":reserved.role}
        api.call("POST","/dispatches",{
            "event_type":"factory-ci-repair","client_payload":payload})
        print(json.dumps({"status":"dispatched","issue":issue,
                          "run_id":decision.run_id,
                          "sha":decision.sha,"revision":reserved.revision}))
        return 0
    except (OSError,KeyError,TypeError,ValueError,error.HTTPError) as exc:
        print("ERROR: CI repair dispatch blocked (" + type(exc).__name__ + ")",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
