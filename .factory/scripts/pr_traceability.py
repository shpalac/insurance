#!/usr/bin/env python3
"""Trusted main-branch, idempotent PR acceptance traceability publisher.

Never checkout or execute PR code in this privileged workflow.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
from urllib import request
from pr_completion_gate import parse_intent
from validate_issue_manifest import extract_manifest, validate_body

MARKER = "<!-- FACTORY_PR_TRACE_V1 -->"


class TraceabilityError(ValueError):
    pass


def render(repo: str, pr: int, sha: str, run_id: int,
           refs: list[int], complete: list[int], bodies: dict) -> str:
    if not re.fullmatch(r"[a-f0-9]{40}", sha) or run_id < 1:
        raise TraceabilityError("Invalid CI evidence identity")
    url = f"https://github.com/{repo}/actions/runs/{run_id}"
    lines = [MARKER, "### CI acceptance traceability",
             f"PR #{pr} on immutable {sha}. CI evidence: {url}",
             "", "| Issue | AC | Target | Runner | Status | Run |",
             "|---|---|---|---|---|---|"]
    for n in refs:
        body = bodies.get(n, "")
        if validate_body(body, expected_issue_id=n):
            lines.append(f"| #{n} | - | - | - | INVALID MANIFEST | - |")
            continue
        for ac in extract_manifest(body)["acceptance_criteria"]:
            label = "PASS" if n in complete else "PARTIAL"
            lines.append(
                f"| #{n} | {ac['id']} | {n}/{ac['id']} "
                f"| {ac['runner_os']} | {label} | [CI]({url}) |"
            )
    lines.append("\nMerge alone does not close an issue; default-branch acceptance is required.")
    return "\n".join(lines)


class API:
    def __init__(self, repo: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
            raise TraceabilityError("Missing trusted GitHub identity")
        self.root = f"https://api.github.com/repos/{repo}"
        self.repo = repo
        self.token = token

    def call(self, method: str, path: str, data: dict | None = None):
        if not path.startswith("/") or "://" in path:
            raise TraceabilityError("Unsafe API path")
        payload = json.dumps(data).encode() if data is not None else None
        req = request.Request(self.root + path, method=method, data=payload, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        with request.urlopen(req, timeout=25) as res:
            raw = res.read()
        return json.loads(raw) if raw else {}

    def comments(self, number: int) -> list[dict]:
        results = []
        for page in range(1, 7):
            batch = self.call(
                "GET", f"/issues/{number}/comments?per_page=100&page={page}"
            )
            if not isinstance(batch, list):
                raise TraceabilityError("Unexpected GitHub comment payload")
            results.extend(batch)
            if len(batch) < 100:
                return results
        raise TraceabilityError("Incomplete comment history")


def publish(event: dict, api: API) -> str:
    run = event.get("workflow_run") or {}
    if (run.get("name") != "Factory selective CI" or
            run.get("event") != "pull_request" or
            run.get("conclusion") != "success"):
        return "skipped"
    linked = run.get("pull_requests") or []
    if len(linked) != 1 or type(linked[0].get("number")) is not int:
        return "no_pr"
    number = linked[0]["number"]
    pr = api.call("GET", f"/pulls/{number}")
    sha = run.get("head_sha")
    if not isinstance(sha, str) or pr.get("head", {}).get("sha") != sha:
        return "stale_sha"
    jobs = api.call("GET", f"/actions/runs/{run['id']}/jobs?per_page=100")
    if jobs.get("total_count", 0) > 100 or not all(
        any(j.get("name") == name and j.get("conclusion") == "success"
            for j in jobs.get("jobs", []))
        for name in ("issue-completion", "factory-gate-preflight")
    ):
        raise TraceabilityError("Missing completed mandatory checks")
    refs, complete = parse_intent(pr.get("body") or "")
    if not refs:
        return "no_refs"
    bodies = {}
    for n in refs:
        issue = api.call("GET", f"/issues/{n}")
        if issue.get("number") != n:
            raise TraceabilityError("GitHub Issue identity mismatch")
        bodies[n] = issue.get("body") or ""
    comment = render(api.repo, number, sha, run["id"], refs, complete, bodies)
    existing = next((c for c in api.comments(number)
                     if MARKER in (c.get("body") or "")
                     and c.get("user", {}).get("type") == "Bot"), None)
    if existing:
        if existing["body"] != comment:
            api.call("PATCH", f"/issues/comments/{existing['id']}", {"body": comment})
        return "updated"
    api.call("POST", f"/issues/{number}/comments", {"body": comment})
    return "created"


def main() -> int:
    try:
        api = API(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])
        data = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        print(publish(data, api))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as e:
        print("ERROR: trusted traceability could not be published:", type(e).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
