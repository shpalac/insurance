#!/usr/bin/env python3
"""Fail-closed attestation of a real end-to-end agent repair canary on main.

The canary must use an actual failing PR, a separately authenticated and
lease-fenced worker repair, a new commit, and all required checks rerun.
A successful disabled dispatcher run cannot satisfy this contract.
"""
from __future__ import annotations

class LiveRepairProofMissing(ValueError):
    pass

CANARY = "Factory live CI repair end-to-end canary"
JOBS = ("inject-failing-test", "lease-fenced-repair", "verify-repaired-head",
        "required-checks-new-head")

def verify_live_repair_proof(api, sha: str) -> dict:
    runs = api.get(f"/actions/runs?head_sha={sha}&event=push&per_page=100")
    if runs.get("total_count", 101) > 100:
        raise LiveRepairProofMissing("Live repair canary run list truncated")
    completed = [r for r in runs.get("workflow_runs", []) if
                 r.get("name") == CANARY and r.get("head_sha") == sha
                 and r.get("event") == "push" and
                 r.get("status") == "completed" and
                 r.get("conclusion") == "success"]
    if not completed:
        raise LiveRepairProofMissing("No successful owner-authorized live repair canary on main")
    run = max(completed, key=lambda x: x["id"])
    jobs = api.get(f"/actions/runs/{run['id']}/jobs?per_page=100")
    if jobs.get("total_count", 101) > 100:
        raise LiveRepairProofMissing("Live repair canary jobs truncated")
    for name in JOBS:
        qualified = [j for j in jobs.get("jobs", []) if
                     j.get("name") == name and j.get("status") == "completed"
                     and j.get("conclusion") == "success"]
        if len(qualified) != 1:
            raise LiveRepairProofMissing("Missing independent live repair stage: " + name)
    return {"head_sha": sha, "run_id": run["id"], "source": CANARY}
