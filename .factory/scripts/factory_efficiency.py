#!/usr/bin/env python3
"""GitHub-only factory efficiency report, bounded and auditable.

Collect runs with read-only API credentials; a separate minimal writer
maintains exactly one bot-authored tracking comment on Issue #71.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import statistics
import sys
from urllib import request

TRACKING_ISSUE = 71
MARKER = "<!-- FACTORY_EFFICIENCY_METRICS_V1 -->"
WATCHDOG = "<!-- FACTORY_STALL_WATCH_V1 -->"
REFS = re.compile(r"(?im)^\s*Refs\s+#([1-9][0-9]*)\s*$")
AUTH = re.compile(r"^FACTORY-OWNER-AUTH sha=[a-f0-9]{40} reason=.{12,300}$")


def dt(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Missing timezone in GitHub timestamp")
    return value.astimezone(timezone.utc)


def mean_or_none(numbers):
    return round(statistics.mean(numbers), 3) if numbers else None


def median_or_none(numbers):
    return round(statistics.median(numbers), 3) if numbers else None


def aggregate(issues: list[dict], prs: list[dict], runs: list[dict],
              comments: dict[int, list[dict]],
              watchdog: dict[int, list[dict]], owner: str,
              now: datetime) -> dict:
    """Fixed definitions; never count unsampled GitHub state as complete."""
    if now.tzinfo is None:
        raise ValueError("Naive measurement time")
    window = now.astimezone(timezone.utc) - timedelta(hours=24)
    closed = [x for x in issues if x.get("closed_at") and x.get("created_at")]
    lead = []
    for issue in closed:
        hours = (dt(issue["closed_at"]) - dt(issue["created_at"])).total_seconds()/3600
        if hours < 0:
            raise ValueError("Negative Issue lead time")
        lead.append(hours)
    merged = [p for p in prs if p.get("merged_at")]
    refs = {}
    for pr in merged:
        for raw in REFS.findall(pr.get("body") or ""):
            n = int(raw)
            refs.setdefault(n,set()).add(pr["number"])
    count_by_issue = {str(n):len(ids) for n,ids in sorted(refs.items())}
    ci = [r for r in runs if r.get("status")=="completed"
          and r.get("conclusion") in ("success","failure")]
    failures = sum(x.get("conclusion") == "failure" for x in ci)
    hour_merges = sum(dt(p["merged_at"]) >= window for p in merged)
    idle_samples = []
    for issue_id,entries in watchdog.items():
        matching=[c for c in entries if WATCHDOG in (c.get("body") or "")
                  and (c.get("user") or {}).get("type")=="Bot"]
        for c in matching[-1:]:
            body = c.get("body") or ""
            if "STALLED" not in body:
                continue
            match=re.search(r"(?m)^Idle seconds:\s*(\d+)\s*$",body)
            if match:
                idle_samples.append(int(match.group(1)))
    auth_count=0
    for pr in merged:
        for comment in comments.get(pr["number"],[]):
            if ((comment.get("user") or {}).get("login") or "").lower() == owner.lower():
                if AUTH.fullmatch((comment.get("body") or "").strip()):
                    auth_count+=1
    return {
        "schema_version": 1, "source":"github-rest", "as_of":now.isoformat(),
        "sample": {"issues":len(issues),"merged_prs":len(merged),
                   "completed_ci":len(ci),"window_hours":24,
                   "commented_merged_prs":len(comments)},
        "issue_lead_time_hours": {"count":len(lead),
                                  "median":median_or_none(lead),
                                  "mean":mean_or_none(lead)},
        "ci_failure_rate": {"failures":failures,"completed":len(ci),
            "ratio":round(failures/len(ci),5) if ci else None},
        "prs_per_issue": {"issue_count":len(refs),"counts":count_by_issue,
                           "mean":mean_or_none(list(count_by_issue.values()))},
        "merges_per_hour": round(hour_merges/24,5),
        "worker_idle_time_seconds": {
            "stalled_workers_sampled":len(idle_samples),
            "total_sampled_seconds":sum(idle_samples),
            "mean_sampled_seconds":mean_or_none(idle_samples)},
        "human_interventions": {"owner_authorization_comments":auth_count,
            "unobserved_actions":"Ruleset edits and external interactions are not counted"},
        "coverage_limits": {
            "scope":"Up to 500 Issues, 500 closed PRs, 100 workflow runs",
            "older_history":"Not represented beyond API sampling bounds"},
    }


def render(d: dict) -> str:
    if d.get("schema_version") != 1:
        raise ValueError("Unsupported factory efficiency report")
    lead=d["issue_lead_time_hours"]
    rate=d["ci_failure_rate"]
    return (f"{MARKER}\n### Factory efficiency (GitHub-measured)\n"
            f"Measured at {d['as_of']}\n"
            f"Median Issue lead: {lead['median']} hours ({lead['count']} closed Issues sampled)\n"
            f"CI failure rate: {rate['ratio']} ({rate['failures']}/{rate['completed']} finished success/failure runs)\n"
            f"Mean merged PRs per referenced Issue: {d['prs_per_issue']['mean']}\n"
            f"Merges/hour over 24h: {d['merges_per_hour']}\n"
            f"Sampled idle seconds: {d['worker_idle_time_seconds']['total_sampled_seconds']}\n"
            f"Observed owner auth comments: {d['human_interventions']['owner_authorization_comments']}\n"
            "Other manual interventions are not observable from this sample. "
            "This is not a security or merge admission check.")

class API:
    def __init__(self,repo:str,token:str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",repo) or not token:
            raise ValueError("Missing GitHub repository")
        self.root="https://api.github.com/repos/"+repo
        self.token=token
    def call(self,method,path,payload=None):
        if not path.startswith("/") or "://" in path:
            raise ValueError("Unsafe REST path")
        raw=json.dumps(payload).encode() if payload is not None else None
        headers={"Authorization":"Bearer "+self.token,
                 "Accept":"application/vnd.github+json"}
        if raw is not None:
            headers["Content-Type"]="application/json"
        with request.urlopen(request.Request(self.root+path,method=method,
                              data=raw,headers=headers),timeout=25) as response:
            body=response.read()
            return json.loads(body) if body else {}
    def get(self,path): return self.call("GET",path)

def pages(api: API, path:str, max_pages:int) -> list[dict]:
    values=[]
    for page in range(1,max_pages+1):
        tail=("&" if "?" in path else "?")+f"per_page=100&page={page}"
        chunk=api.get(path+tail)
        if not isinstance(chunk,list):
            raise ValueError("Invalid GitHub collection")
        values.extend(chunk)
        if len(chunk)<100:
            return values
    raise ValueError("Metrics collection exceeds bounded window")

def collect(api: API,owner:str,now:datetime) -> dict:
    issues=[x for x in pages(api,"/issues?state=all",5) if "pull_request" not in x]
    prs=pages(api,"/pulls?state=closed",5)
    runs=api.get("/actions/runs?per_page=100")
    if runs.get("total_count",101)>100:
        # This is explicitly a recent-run sample, never full-history proof.
        pass
    history=runs.get("workflow_runs")
    if not isinstance(history,list):
        raise ValueError("Missing workflow histories")
    merged=[p for p in prs if p.get("merged_at")]
    comments={}
    for pr in merged:
        n=pr["number"]
        c=api.get(f"/issues/{n}/comments?per_page=100")
        if not isinstance(c,list) or len(c)>=100:
            raise ValueError("Truncated PR authorization comments")
        comments[n]=c
    idle={}
    # Watchdog writes sticky bot comments only on claimed stalled Issues.
    for issue in issues:
        if not any((x.get("name") or "").startswith(("status:","preflight:"))
                   for x in issue.get("labels",[])):
            continue
        n=issue["number"]
        c=api.get(f"/issues/{n}/comments?per_page=100")
        if isinstance(c,list) and len(c)<100:
            idle[n]=c
    return aggregate(issues,prs,history,comments,idle,owner,now)

def publish(api:API,report:dict):
    issue=TRACKING_ISSUE
    current=api.get(f"/issues/{issue}/comments?per_page=100")
    if not isinstance(current,list) or len(current)>=100:
        raise ValueError("Tracking comment page is incomplete")
    body=render(report)
    bot=next((x for x in current if MARKER in (x.get("body") or "")
              and (x.get("user") or {}).get("type")=="Bot"),None)
    if bot is None:
        api.call("POST",f"/issues/{issue}/comments",{"body":body})
        return "created"
    if bot.get("body")!=body:
        api.call("PATCH",f"/issues/comments/{bot['id']}",{"body":body})
        return "updated"
    return "unchanged"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("collect","publish"),required=True)
    p.add_argument("--output",type=Path)
    p.add_argument("--input",type=Path)
    a=p.parse_args()
    try:
        api=API(os.environ["GITHUB_REPOSITORY"],os.environ["GH_TOKEN"])
        if a.mode=="collect":
            if a.output is None:raise ValueError("Missing output")
            d=collect(api,os.environ["GITHUB_REPOSITORY_OWNER"],datetime.now(timezone.utc))
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(json.dumps(d,indent=2,sort_keys=True))
            print(json.dumps({"tracked_issue_count":d["sample"]["issues"],
                              "merged_prs_sampled":d["sample"]["merged_prs"]}))
        else:
            if a.input is None:raise ValueError("Missing report input")
            print(publish(api,json.loads(a.input.read_text())))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print("ERROR: efficiency metrics blocked:",type(exc).__name__,file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
