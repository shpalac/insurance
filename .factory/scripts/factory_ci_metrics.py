#!/usr/bin/env python3
"""Read-only factory CI telemetry: exact run identity, lane timing and history.

This workflow is observational, not a substitute for GitHub branch rules.
It always reads trusted main code, never executes source from a candidate PR,
and refuses to report a truncated data sample as complete evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import statistics
import sys
from urllib import request

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[a-f0-9]{40}$")
REQUIRED = ("unit-tests", "factory-bootstrap-gate", "factory-gate-preflight",
            "issue-completion", "factory-trusted-admission")
LANES = ("impact", "policy", "issue-completion", "scanner", "factory",
         "docs", "macos", "windows", "acceptance-macos", "acceptance-windows",
         "factory-gate-preflight")


class MetricsError(ValueError):
    pass


def instant(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise MetricsError("Missing required timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetricsError("Malformed timestamp") from exc
    if parsed.tzinfo is None:
        raise MetricsError("Timestamp lacks an explicit timezone")
    return parsed


def seconds(start: str, end: str) -> float:
    amount = (instant(end) - instant(start)).total_seconds()
    if amount < 0:
        raise MetricsError("Negative CI interval")
    return round(amount, 3)


def percentile(samples: list[float], q: float) -> float | None:
    if not samples:
        return None
    if not 0 <= q <= 1 or any(not isinstance(x, (int, float)) or x < 0
                              for x in samples):
        raise MetricsError("Invalid percentile samples")
    ordered = sorted(samples)
    position = (len(ordered) - 1) * q
    before, after = int(position), min(int(position) + 1, len(ordered) - 1)
    return round(ordered[before] +
                 (ordered[after] - ordered[before]) * (position - before), 3)


def run_stats(run: dict, jobs: list[dict]) -> dict:
    if type(run.get("id")) is not int or not SHA.fullmatch(run.get("head_sha") or ""):
        raise MetricsError("Missing immutable workflow run identity")
    if run.get("name") != "Factory selective CI" or run.get("status") != "completed":
        raise MetricsError("Unfinished or wrong factory CI run")
    lanes = {}
    for job in jobs:
        name = job.get("name")
        if name not in LANES:
            continue
        value = {"status": job.get("status"), "conclusion": job.get("conclusion")}
        if value["status"] == "completed" and job.get("started_at") and job.get("completed_at"):
            value["duration_seconds"] = seconds(job["started_at"], job["completed_at"])
        lanes[name] = value
    queue = seconds(run["created_at"], run["run_started_at"]) if run.get("run_started_at") else None
    total = seconds(run["created_at"], run["updated_at"])
    return {"run_id": run["id"], "sha": run["head_sha"],
            "event": run.get("event"), "conclusion": run.get("conclusion"),
            "queue_delay_seconds": queue, "total_runtime_seconds": total,
            "lanes": lanes}


def build_report(current: dict, current_jobs: list[dict], history: list[tuple[dict, list[dict]]],
                 changed_paths: list[str], path_evidence: str, checks: list[dict]) -> dict:
    now = run_stats(current, current_jobs)
    samples = [now]
    seen = {now["run_id"]}
    for run, jobs in history:
        item = run_stats(run, jobs)
        if item["run_id"] not in seen:
            samples.append(item)
            seen.add(item["run_id"])
    lane_percentiles = {}
    for lane in LANES:
        durations = [item["lanes"][lane]["duration_seconds"] for item in samples
                     if lane in item["lanes"]
                     and "duration_seconds" in item["lanes"][lane]]
        lane_percentiles[lane] = {
            "n": len(durations),
            "p50_seconds": percentile(durations, 0.50),
            "p95_seconds": percentile(durations, 0.95),
        }
    contexts = {}
    for name in REQUIRED:
        matching = [c for c in checks if c.get("name") == name
                    and c.get("head_sha") == current["head_sha"]]
        contexts[name] = (
            sorted(matching, key=lambda x: x.get("completed_at") or "",
                   reverse=True)[0].get("conclusion") if matching else "pending"
        )
    if path_evidence not in ("github-pr-files", "github-commit-files", "unavailable"):
        raise MetricsError("Unrecognized changed-file provenance")
    if (not isinstance(changed_paths, list) or len(changed_paths) > 100
            or any(not isinstance(p, str) or not p or ".." in p.split("/")
                   for p in changed_paths)):
        raise MetricsError("Changed-file evidence is malformed")
    return {"schema_version": 1, "source": "github-actions-rest",
            "workflow": "Factory selective CI", "current": now,
            "changed_paths": sorted(changed_paths),
            "path_evidence": path_evidence, "paths_complete": path_evidence != "unavailable",
            "required_checks": contexts, "lanes": lane_percentiles,
            "history_runs": len(samples)}


class API:
    def __init__(self, repo: str, token: str):
        if not REPO.fullmatch(repo) or not token:
            raise MetricsError("Missing trusted GitHub identity")
        self.base = "https://api.github.com/repos/" + repo
        self.token = token

    def get(self, path: str):
        if not path.startswith("/") or "://" in path:
            raise MetricsError("Unsafe API request")
        req = request.Request(self.base + path, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json"})
        with request.urlopen(req, timeout=25) as response:
            return json.load(response)


def checked_jobs(api: API, run_id: int) -> list[dict]:
    page = api.get(f"/actions/runs/{run_id}/jobs?per_page=100")
    if page.get("total_count", 101) > 100 or not isinstance(page.get("jobs"), list):
        raise MetricsError("Truncated or missing hosted jobs")
    return page["jobs"]


def collect(api: API, event: dict) -> dict:
    source = event.get("workflow_run") or {}
    run_id = source.get("id")
    if type(run_id) is not int or run_id < 1:
        raise MetricsError("Missing completed run ID")
    current = api.get(f"/actions/runs/{run_id}")
    if (source.get("id") != current.get("id")
            or source.get("head_sha") != current.get("head_sha")
            or source.get("name") != current.get("name")):
        raise MetricsError("Webhook and authenticated API run disagree")
    jobs = checked_jobs(api, run_id)
    history_raw = api.get("/actions/workflows/ci-selective.yml/runs?per_page=15")
    if not isinstance(history_raw.get("workflow_runs"), list):
        raise MetricsError("Missing CI run history")
    history = []
    for candidate in history_raw["workflow_runs"]:
        if (candidate.get("status") == "completed"
                and candidate.get("name") == "Factory selective CI"
                and candidate.get("id") != run_id):
            history.append((candidate, checked_jobs(api, candidate["id"])))
    sha = current["head_sha"]
    refs = current.get("pull_requests") or source.get("pull_requests") or []
    changed, provenance = [], "unavailable"
    if len(refs) == 1:
        files = api.get(f"/pulls/{refs[0]['number']}/files?per_page=100")
        if isinstance(files, list) and len(files) < 100:
            changed = [row["filename"] for row in files]
            provenance = "github-pr-files"
    elif current.get("event") == "push":
        commit = api.get(f"/commits/{sha}")
        files = commit.get("files")
        if isinstance(files, list) and len(files) < 100:
            changed = [row["filename"] for row in files]
            provenance = "github-commit-files"
    checks = api.get(f"/commits/{sha}/check-runs?per_page=100")
    if checks.get("total_count", 101) > 100:
        raise MetricsError("Check-run evidence is truncated")
    return build_report(current, jobs, history, changed, provenance,
                        checks.get("check_runs") or [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        report = collect(API(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]), event)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True))
        print(json.dumps({"schema_version": 1, "run_id": report["current"]["run_id"],
                          "p50_p95_lanes": len(report["lanes"])}))
        return 0
    except (OSError, MetricsError, ValueError, KeyError, TypeError) as exc:
        print("ERROR: read-only CI telemetry incomplete: " + type(exc).__name__,
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
