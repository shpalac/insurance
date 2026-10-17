#!/usr/bin/env python3
"""Trusted metadata-only Issue preflight. Does not execute Issue-authored code.

Preflight labels are distinct from agent-authorized readiness, so an
ordinary contributor never receives a worker lease from preflight alone.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib import request, parse, error
from validate_issue_manifest import validate_body

READY = "preflight:ready"
BLOCKED = "preflight:blocked"
MARKER = "<!-- FACTORY_EXECUTABLE_ISSUE_PREFLIGHT_V1 -->"
ROOT = Path(__file__).resolve().parents[2]

def evaluate(event: dict) -> dict:
    if event.get("action") not in {"opened", "edited", "reopened"}:
        return {"skip": True, "errors": ["Unsupported Issue event"]}
    issue = event.get("issue") or {}
    n = issue.get("number")
    if type(n) is not int or n < 1 or issue.get("pull_request"):
        return {"skip": True, "errors": ["Not a standalone Issue"]}
    body = issue.get("body") or ""
    errors = validate_body(body, root=ROOT, expected_issue_id=n)
    return {"skip": False, "issue": n, "valid": not errors,
            "errors": [str(x)[:300] for x in errors[:20]],
            "body_sha256": hashlib.sha256(body.encode()).hexdigest()}

def report(d: dict) -> str:
    if d.get("skip"):
        raise ValueError("Cannot report skipped events")
    safe = [str(x).replace(chr(96), "'").replace("<", "&lt;").replace("\n", " ")[:300]
            for x in d["errors"]]
    return (f"{MARKER}\n### Executable Issue preflight: "
            f"{'VALID' if d['valid'] else 'BLOCKED'}\n"
            f"Manifest revision: {d['body_sha256']}\n"
            + ("\n".join("- " + x for x in safe) if safe
               else "All structural acceptance checks passed.")
            + "\n\nNo Issue-authored commands executed. "
              "Preflight is not agent role authorization.")

def label_delta(current: set[str], valid: bool) -> tuple[set[str],set[str]]:
    target = READY if valid else BLOCKED
    opposite = BLOCKED if valid else READY
    return ({target} - current, {opposite} & current)

class API:
    def __init__(self, repo: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
            raise ValueError("Authenticated repository required")
        self.root = "https://api.github.com/repos/" + repo
        self.token = token
    def call(self, method: str, path: str, data=None):
        if not path.startswith("/") or "://" in path:
            raise ValueError("Invalid relative API endpoint")
        body = json.dumps(data).encode() if data is not None else None
        headers = {"Authorization": "Bearer " + self.token,
                   "Accept": "application/vnd.github+json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        with request.urlopen(request.Request(self.root + path, method=method,
                            headers=headers, data=body), timeout=25) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    def get(self, path: str):
        return self.call("GET", path)

def publish(api: API, d: dict) -> dict:
    if d.get("skip"):
        return {"status": "skipped"}
    n = d["issue"]
    issue = api.get(f"/issues/{n}")
    if issue.get("state") != "open" or issue.get("pull_request"):
        return {"status": "skipped_closed"}
    if hashlib.sha256((issue.get("body") or "").encode()).hexdigest() != d["body_sha256"]:
        raise ValueError("Issue body changed after preflight evaluation")
    existing = {x["name"] for x in issue.get("labels", [])}
    add, remove = label_delta(existing, d["valid"])
    for label in sorted(add):
        try:
            api.call("POST", "/labels", {
                "name": label,
                "color": "C2E0C6" if label == READY else "D93F0B",
                "description": "Executable Issue structure validation only"})
        except error.HTTPError as exc:
            if exc.code != 422:
                raise
        api.call("POST", f"/issues/{n}/labels", {"labels": [label]})
    for label in sorted(remove):
        try:
            api.call("DELETE", f"/issues/{n}/labels/{parse.quote(label,safe='')}")
        except error.HTTPError as exc:
            if exc.code != 404:
                raise
    comments = api.get(f"/issues/{n}/comments?per_page=100")
    if not isinstance(comments,list) or len(comments) >= 100:
        raise ValueError("Unproven bot comment dedup")
    bot = next((c for c in comments if MARKER in c.get("body","")
                and c.get("user",{}).get("type") == "Bot"),None)
    message = report(d)
    if bot is None:
        api.call("POST", f"/issues/{n}/comments", {"body": message})
    elif bot.get("body") != message:
        api.call("PATCH", f"/issues/comments/{bot['id']}", {"body": message})
    return {"status": "ready" if d["valid"] else "blocked",
            "errors": d["errors"], "added": sorted(add), "removed": sorted(remove)}

def main() -> int:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        decision = evaluate(event)
        if decision.get("skip"):
            print("SKIP: non-Issue event")
            return 0
        result = publish(API(os.environ["GITHUB_REPOSITORY"],
                            os.environ["GITHUB_TOKEN"]),decision)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (ValueError,TypeError,KeyError,OSError,error.HTTPError) as exc:
        print("ERROR: Issue preflight blocked",type(exc).__name__,file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
