#!/usr/bin/env python3
"""Read-only GitHub lease watchdog, with a separate idempotent comment publisher.

No lease modifications, merges, check approvals, branch pushes or agent
dispatch. A missing lease-state branch produces an explicit unavailable report.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib import error, request, parse

MARKER = "<!-- FACTORY_STALL_WATCH_V1 -->"
PHASES = {"claimed", "implementing", "repairing", "reviewing", "validating"}
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def instant(value: str) -> datetime:
    x = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if x.tzinfo is None:
        raise ValueError("Stall timestamp must be timezone aware")
    return x.astimezone(timezone.utc)


def detect(issue: int, lease: dict, activity: list[str], now: datetime,
           threshold_minutes: int = 45) -> dict:
    if (type(issue) is not int or issue < 1 or threshold_minutes < 15
            or threshold_minutes > 1440 or now.tzinfo is None
            or type(lease.get("entity")) is not int or lease["entity"] != issue):
        raise ValueError("Invalid lease or threshold")
    if lease.get("phase") not in PHASES:
        return {"issue": issue, "stalled": False, "reason": "not_claimed",
                "idle_seconds": 0}
    raw = [lease["heartbeat_at"], *activity]
    latest = max(instant(x) for x in raw)
    idle = max(0, round((now.astimezone(timezone.utc) - latest).total_seconds()))
    return {"issue": issue, "stalled": idle >= threshold_minutes * 60,
            "latest_activity_at": latest.isoformat(),
            "observed_at": now.astimezone(timezone.utc).isoformat(),
            "idle_seconds": idle, "threshold_minutes": threshold_minutes,
            "owner": str(lease.get("owner", ""))[:80],
            "epoch": lease.get("epoch"), "phase": lease["phase"]}


def comment_decision(previous: list[dict], status: dict) -> tuple[str, int | None, str]:
    """Only bot-authored sticky status is updated; never delete comments."""
    note = (f"{MARKER}\n### Factory worker idle watch\n"
            f"Issue #{status['issue']}; {'STALLED' if status['stalled'] else 'ACTIVE'}\n"
            f"Last activity: {status.get('latest_activity_at','not recorded')}\n"
            f"Observed: {status.get('observed_at','not recorded')}\n"
            f"Idle seconds: {status['idle_seconds']}\n"
            f"Threshold minutes: {status.get('threshold_minutes',45)}\n"
            "Informational only. No lease or code was modified.")
    bot = next((x for x in previous if MARKER in x.get("body", "")
                and x.get("user", {}).get("type") == "Bot"), None)
    if bot is not None:
        # A re-run at a new clock time need not overwrite unchanged status
        # unless its idle count or state changed; same payload is exactly once.
        if bot.get("body") == note:
            return ("noop", bot["id"], note)
        return ("update", bot["id"], note)
    return ("create", None, note)


class API:
    def __init__(self, repo: str, token: str):
        if not REPO.fullmatch(repo) or not token:
            raise ValueError("Invalid authorized repository")
        self.root = "https://api.github.com/repos/" + repo
        self.token = token

    def call(self, method: str, path: str, data=None):
        if not path.startswith("/") or "://" in path:
            raise ValueError("Invalid API path")
        body = json.dumps(data).encode() if data is not None else None
        headers = {"Authorization": "Bearer " + self.token,
                   "Accept": "application/vnd.github+json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        with request.urlopen(request.Request(self.root + path,method=method,
                              data=body,headers=headers),timeout=25) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}

    def get(self, path: str):
        return self.call("GET", path)


def scan(api: API, now: datetime, threshold: int) -> dict:
    try:
        state = api.get("/contents/.factory/lease-state.json?ref=factory-lease-state")
    except error.HTTPError as exc:
        if exc.code == 404:
            return {"version": 1, "status": "lease_state_unavailable",
                    "observed_at": now.isoformat(), "records": []}
        raise
    if state.get("encoding") != "base64":
        raise ValueError("Unsupported durable lease state")
    payload = json.loads(base64.b64decode(state["content"]))
    if payload.get("version") != 1 or not isinstance(payload.get("leases"), dict):
        raise ValueError("Invalid lease snapshot")
    records = []
    for key, lease in sorted(payload["leases"].items(), key=lambda x: int(x[0])):
        issue = int(key)
        if lease.get("phase") not in PHASES:
            continue
        # Bound current Issue and linked PR fetches; never accept dynamic
        # executable code or event commands from Issue text.
        x = api.get(f"/issues/{issue}")
        if x.get("state") != "open":
            continue
        activity = []
        branch = lease.get("branch") or ""
        if branch.startswith("factory/"):
            try:
                b = api.get(f"/branches/{parse.quote(branch,safe='/')}")
                stamp = ((b.get("commit") or {}).get("commit") or {}).get("committer",{}).get("date")
                if stamp:
                    activity.append(stamp)
            except error.HTTPError as exc:
                if exc.code != 404:
                    raise
        prs = api.get(f"/pulls?state=open&head={api.root.split('/repos/')[1].split('/')[0]}:{parse.quote(branch)}&per_page=20") if branch else []
        if len(prs) >= 20:
            raise ValueError("PR activity truncated")
        for pr in prs:
            if pr.get("updated_at"):
                activity.append(pr["updated_at"])
        records.append(detect(issue, lease, activity, now, threshold))
    return {"version": 1, "status": "ok", "observed_at": now.isoformat(),
            "records": records}


def publish(api: API, data: dict) -> dict:
    if data.get("version") != 1 or data.get("status") not in ("ok", "lease_state_unavailable"):
        raise ValueError("Unsupported watchdog report")
    outcomes = []
    for status in data["records"]:
        if not status.get("stalled"):
            continue
        issue = status["issue"]
        comments = api.get(f"/issues/{issue}/comments?per_page=100")
        if not isinstance(comments, list) or len(comments) >= 100:
            raise ValueError("Cannot prove deduplicated comment")
        action, cid, message = comment_decision(comments, status)
        if action == "create":
            api.call("POST", f"/issues/{issue}/comments", {"body": message})
        if action == "update":
            api.call("PATCH", f"/issues/comments/{cid}", {"body": message})
        outcomes.append({"issue": issue, "action": action})
    return {"posted": outcomes}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode",choices=("scan","publish"),required=True)
    p.add_argument("--output",type=Path)
    p.add_argument("--report",type=Path)
    p.add_argument("--threshold-minutes",type=int,default=45)
    a=p.parse_args()
    try:
        api=API(os.environ["GITHUB_REPOSITORY"],os.environ["GH_TOKEN"])
        if a.mode=="scan":
            if a.output is None:
                raise ValueError("Missing output path")
            report=scan(api,datetime.now(timezone.utc),a.threshold_minutes)
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(json.dumps(report,sort_keys=True,indent=2))
            print(json.dumps({"status":report["status"],"tracked":len(report["records"]),
                              "stalled":sum(x["stalled"] for x in report["records"])}))
        else:
            if a.report is None:
                raise ValueError("Missing authenticated scan artifact")
            print(json.dumps(publish(api,json.loads(a.report.read_text()))))
        return 0
    except (OSError,ValueError,TypeError,KeyError,error.HTTPError) as exc:
        print("ERROR: watchdog blocked:",type(exc).__name__,file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
