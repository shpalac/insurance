#!/usr/bin/env python3
"""Independent, fail-closed online attestation for Issue #48.

An ordinary acceptance test or a completed but disabled dispatcher is never
proof of an autonomous two-Issue software-factory delivery. Only a real hosted
run, its independently successful stages, and a durable artifact can qualify.
"""
from __future__ import annotations

import re

SHA = re.compile(r"^[a-f0-9]{40}$")
DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
WORKFLOW = "Factory two-issue autonomous delivery canary"
ARTIFACT = "factory-two-issue-live-evidence"
STAGES = (
    "real-first-issue",
    "fault-recovery",
    "negative-admission",
    "real-second-issue",
    "verify-independent-evidence",
)


class LiveTwoIssueCanaryMissing(ValueError):
    pass


def _page(api, path: str, key: str) -> list[dict]:
    page = api.get(path)
    if (not isinstance(page, dict)
            or type(page.get("total_count")) is not int
            or page["total_count"] > 100
            or not isinstance(page.get(key), list)):
        raise LiveTwoIssueCanaryMissing("Hosted evidence page missing or truncated")
    return page[key]


def verify_live_two_issue_canary(api, sha: str) -> dict:
    """Require a real, all-stage hosted integration run on current trusted main.

    This proof cannot be supplied by issue text, a candidate PR, a standalone
    unittest, a workflow skipped by GitHub, or an artifact lacking a digest.
    """
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise LiveTwoIssueCanaryMissing("Invalid immutable default-branch SHA")
    if api.get("/git/ref/heads/main").get("object", {}).get("sha") != sha:
        raise LiveTwoIssueCanaryMissing("Default branch moved during attestation")
    if api.get("/issues/47").get("state") != "closed":
        raise LiveTwoIssueCanaryMissing("Guarded integrator dependency #47 is incomplete")

    runs = _page(
        api, f"/actions/runs?head_sha={sha}&event=workflow_dispatch&per_page=100",
        "workflow_runs",
    )
    qualifying = [
        r for r in runs if r.get("name") == WORKFLOW
        and r.get("head_sha") == sha and r.get("head_branch") == "main"
        and r.get("event") == "workflow_dispatch"
        and r.get("status") == "completed" and r.get("conclusion") == "success"
        and type(r.get("id")) is int
    ]
    if len(qualifying) != 1:
        raise LiveTwoIssueCanaryMissing(
            "Expected one successful, exact-main, real two-Issue hosted canary"
        )
    run = qualifying[0]
    jobs = _page(api, f"/actions/runs/{run['id']}/jobs?per_page=100", "jobs")
    for name in STAGES:
        matches = [
            j for j in jobs if j.get("name") == name
            and j.get("status") == "completed"
            and j.get("conclusion") == "success"
        ]
        if len(matches) != 1:
            raise LiveTwoIssueCanaryMissing("Missing successful independent stage: " + name)
    artifacts = _page(
        api, f"/actions/runs/{run['id']}/artifacts?per_page=100", "artifacts",
    )
    proven = [
        a for a in artifacts if a.get("name") == ARTIFACT
        and a.get("expired") is False and type(a.get("id")) is int
        and isinstance(a.get("digest"), str)
        and DIGEST.fullmatch(a["digest"])
    ]
    if len(proven) != 1:
        raise LiveTwoIssueCanaryMissing("No immutable nonexpired live evidence artifact")
    return {
        "main_sha": sha, "run_id": run["id"],
        "artifact_id": proven[0]["id"],
        "artifact_digest": proven[0]["digest"],
        "stages": list(STAGES),
        "source": WORKFLOW,
    }
