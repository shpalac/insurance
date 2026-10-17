#!/usr/bin/env python3
"""Verify actual hosted canary jobs for an immutable current-main commit.

A passing ordinary unittest never substitutes for a real GitHub Actions
two-worker ref race. Missing, incomplete or off-SHA canaries fail closed.
"""
from __future__ import annotations


class HostedLeaseCanaryMissing(ValueError):
    pass


def verify_live_lease_canary(api, sha: str) -> dict:
    runs = api.get(f"/actions/runs?head_sha={sha}&event=push&per_page=100")
    if runs.get("total_count", 101) > 100:
        raise HostedLeaseCanaryMissing("Hosted canary run list truncated")
    matches = [r for r in runs.get("workflow_runs", [])
               if r.get("name") == "Factory isolated lease CAS canary"
               and r.get("head_sha") == sha
               and r.get("event") == "push"
               and r.get("conclusion") == "success"
               and r.get("status") == "completed"]
    if not matches:
        raise HostedLeaseCanaryMissing("Actual hosted lease CAS race not successful on main SHA")
    run = max(matches, key=lambda r: r["id"])
    jobs = api.get(f"/actions/runs/{run['id']}/jobs?per_page=100")
    if jobs.get("total_count", 101) > 100:
        raise HostedLeaseCanaryMissing("Hosted canary job list truncated")
    names = ("initialize", "race (one)", "race (two)", "verify-single-winner")
    for name in names:
        qualifying = [job for job in jobs.get("jobs", [])
                      if job.get("name") == name
                      and job.get("status") == "completed"
                      and job.get("conclusion") == "success"]
        if len(qualifying) != 1:
            raise HostedLeaseCanaryMissing("Missing true independent worker and verification job")
    return {"run_id": run["id"], "head_sha": sha, "workers": 2,
            "source": "github_hosted_isolated_lease_canary"}
