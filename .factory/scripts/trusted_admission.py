#!/usr/bin/env python3
"""Trusted control-plane admission check for the immutable PR head.

Runs ONLY from main in a workflow_run job. Never checks out or evaluates
candidate code and never executes Issue/PR text as instructions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from urllib import request

SHA = re.compile(r"^[a-f0-9]{40}$")
AUTH = re.compile(r"^FACTORY-OWNER-AUTH sha=([a-f0-9]{40}) reason=(.{12,300})$")
REQUIRED = ("issue-completion", "factory-gate-preflight")


def protected(path: str) -> bool:
    return (path.startswith((".github/workflows/", ".factory/"))
            or path in {"AGENTS.md", "SECURITY.md"})


def owner_authorized(comments: list[dict], owner: str, head_sha: str) -> bool:
    for item in comments:
        if (item.get("user") or {}).get("login", "").lower() != owner.lower():
            continue
        match = AUTH.fullmatch((item.get("body") or "").strip())
        if match and match.group(1) == head_sha:
            return True
    return False


def admission_blockers(pr: dict, run: dict, jobs: list[dict],
                       paths: list[str], comments: list[dict], owner: str) -> list[str]:
    errors = []
    head = (pr.get("head") or {}).get("sha")
    if not isinstance(head, str) or not SHA.fullmatch(head):
        return ["Invalid authoritative GitHub head SHA"]
    if (run.get("head_sha") != head
            or run.get("event") != "pull_request"
            or run.get("conclusion") != "success"):
        errors.append("Selective CI run is failed, stale, or not a PR event")
    if pr.get("state") != "open" or pr.get("draft"):
        errors.append("PR not open or is draft")
    if pr.get("base", {}).get("ref") != "main":
        errors.append("PR does not target main")
    if pr.get("mergeable") is not True:
        errors.append("Mergeability is not authoritatively proven")
    for name in REQUIRED:
        if not any(j.get("name") == name and j.get("conclusion") == "success"
                   and j.get("status") == "completed" for j in jobs):
            errors.append("Required completed CI job missing or failed: " + name)
    if not isinstance(paths, list) or not paths or len(paths) >= 100:
        errors.append("PR changed-file evidence missing or truncated")
    elif any(protected(p) for p in paths):
        if not owner_authorized(comments, owner, head):
            errors.append("Protected paths need owner-authored, exact-head approval")
    return errors


class API:
    def __init__(self, repo: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
            raise ValueError("Missing trusted repository or token")
        self.base = "https://api.github.com/repos/" + repo
        self.token = token

    def call(self, method: str, path: str, payload: dict | None = None):
        if not path.startswith("/") or "://" in path:
            raise ValueError("Unsafe GitHub API path")
        data = json.dumps(payload).encode() if payload is not None else None
        req = request.Request(self.base + path, data=data, method=method,
                              headers={
                                  "Authorization": "Bearer " + self.token,
                                  "Accept": "application/vnd.github+json",
                                  "Content-Type": "application/json",
                                  "X-GitHub-Api-Version": "2022-11-28",
                              })
        with request.urlopen(req, timeout=25) as response:
            return json.load(response)


def handle(event: dict, api: API, owner: str) -> dict:
    run = event.get("workflow_run") or {}
    if run.get("name") != "Factory selective CI" or run.get("event") != "pull_request":
        return {"status": "skipped", "errors": []}
    links = run.get("pull_requests") or []
    if len(links) != 1 or type(links[0].get("number")) is not int:
        return {"status": "blocked", "errors": ["Missing unambiguous PR number"]}
    n = links[0]["number"]
    pr = api.call("GET", f"/pulls/{n}")
    jobs = api.call("GET", f"/actions/runs/{run['id']}/jobs?per_page=100")
    files = api.call("GET", f"/pulls/{n}/files?per_page=100")
    comments = api.call("GET", f"/issues/{n}/comments?per_page=100")
    errors = admission_blockers(
        pr, run, jobs.get("jobs", []) if jobs.get("total_count", 101) <= 100 else [],
        [item.get("filename", "") for item in files] if len(files) < 100 else [],
        comments if len(comments) < 100 else [], owner,
    )
    # A trusted GitHub App check is attached to the PR head, not main.
    sha = (pr.get("head") or {}).get("sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        return {"status": "blocked", "errors": ["Invalid PR SHA"]}
    conclusion = "failure" if errors else "success"
    api.call("POST", "/check-runs", {
        "name": "factory-trusted-admission",
        "head_sha": sha,
        "status": "completed",
        "conclusion": conclusion,
        "details_url": run.get("html_url"),
        "output": {
            "title": "Factory trusted merge admission",
            "summary": ("Verified trusted-main CI and scoped authorization"
                        if not errors else
                        "BLOCKED: " + "; ".join(errors)[:1000]),
        },
    })
    return {"status": conclusion, "errors": errors}


def main() -> int:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        api = API(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])
        result = handle(event, api, os.environ["GITHUB_REPOSITORY_OWNER"])
        print(result["status"])
        for problem in result["errors"]:
            print("BLOCKED:", problem)
        return 0 if result["status"] in {"success", "skipped"} else 1
    except (KeyError, TypeError, ValueError, OSError) as exc:
        print("ERROR: trusted admission unavailable: " + type(exc).__name__,
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
