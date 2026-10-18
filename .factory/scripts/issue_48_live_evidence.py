#!/usr/bin/env python3
"""Read-only online verifier of actual two-Issue factory deliveries and faults.

The evidence file is an index of GitHub identifiers, never authority by
itself. Every Issue, PR, Actions run, audit comment and digest is independently
fetched using the workflow's read-only GitHub token. No synthetic input is
accepted as a successful live operation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from urllib import request

ROOT=Path(__file__).resolve().parents[2]
REPO=re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
SHA=re.compile(r"^[a-f0-9]{40}$")
DIGEST=re.compile(r"^sha256:[a-f0-9]{64}$")
AUDIT=re.compile(r"<!-- FACTORY_CLOSURE_AUDIT_V1 issue=(\d+) main=([a-f0-9]{40}) -->")
REQUIRED=("unit-tests","factory-gate-preflight","factory-bootstrap-gate",
          "issue-completion","factory-trusted-admission")
RECOVERY=("injected_ci_failure","worker_interruption","expired_lease",
          "simultaneous_claim","merge_conflict")
NEGATIVE=("missing_required_check","unapproved_identity","protected_path",
          "malicious_issue_prompt","stale_sha")


class UnverifiedLiveDelivery(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise UnverifiedLiveDelivery(reason)


def _integer(n):
    return type(n) is int and n > 0


def _artifact(api, run_id: int, name: str, digest: str) -> None:
    _require(isinstance(digest,str) and DIGEST.fullmatch(digest),
             "Missing genuine artifact digest")
    page=api.get(f"/actions/runs/{run_id}/artifacts?per_page=100")
    items=page.get("artifacts")
    _require(type(page.get("total_count")) is int
             and page["total_count"]<=100 and isinstance(items,list),
             "Truncated artifact listing")
    _require(sum(1 for item in items if
                 item.get("name")==name and item.get("digest")==digest
                 and item.get("expired") is False)==1,
             "Verified immutable artifact missing or expired")


def _successful_run(api, number, name, *, require_actor=True):
    _require(_integer(number),"Missing real hosted run ID")
    run=api.get(f"/actions/runs/{number}")
    _require(run.get("name")==name and run.get("id")==number
             and run.get("status")=="completed"
             and run.get("conclusion")=="success",
             "Actions run did not complete the expected verification")
    if require_actor:
        actor=(run.get("actor") or {}).get("login")
        _require(isinstance(actor,str) and actor
                 and actor!="github-actions[bot]",
                 "No independently identified actor")
    return run


def _is_ancestor(api, ancestor, main):
    if not isinstance(ancestor,str) or not SHA.fullmatch(ancestor):
        return False
    if ancestor==main: return True
    comparison=api.get(f"/compare/{ancestor}...{main}")
    return comparison.get("status")=="ahead" and comparison.get("behind_by")==0


def verify_delivery(api, row, main_sha, *, repository):
    issue_number=row.get("issue")
    pr_number=row.get("pr")
    _require(_integer(issue_number) and _integer(pr_number),
             "Missing distinct Issue and PR identifiers")
    issue=api.get(f"/issues/{issue_number}")
    pr=api.get(f"/pulls/{pr_number}")
    merge=pr.get("merge_commit_sha")
    _require(issue.get("state")=="closed"
             and pr.get("merged_at") and pr.get("base",{}).get("ref")=="main"
             and merge==row.get("merge_sha") and _is_ancestor(api,merge,main_sha),
             "Real guarded merge and completed Issue not verified")
    _require(re.search(r"(?m)^Refs #"+str(issue_number)+r"\s*$",pr.get("body") or ""),
             "PR lacks Refs-only Issue scope")
    _require("Closes #" not in (pr.get("body") or "")
             and "Fixes #" not in (pr.get("body") or ""),
             "Native Issue-close keywords not permitted")
    head=(pr.get("head") or {}).get("sha")
    _require(isinstance(head,str) and SHA.fullmatch(head),
             "Merged PR lacks immutable candidate head")
    checks=api.get(f"/commits/{head}/check-runs?per_page=100")
    rows=checks.get("check_runs")
    _require(type(checks.get("total_count")) is int
             and checks["total_count"]<=100 and isinstance(rows,list),
             "Required PR checks incomplete")
    for name in REQUIRED:
        _require(any(c.get("name")==name and c.get("head_sha")==head
                     and c.get("status")=="completed"
                     and c.get("conclusion")=="success" for c in rows),
                 "Missing required PR proof: "+name)
    dispatch=_successful_run(api,row.get("dispatch_run"),"Factory agent dispatch")
    _require((dispatch.get("actor") or {}).get("login")==row.get("agent_login"),
             "Authenticated worker identity differs from declared actor")
    _artifact(api,dispatch["id"],"factory-agent-dispatch-proof",
              row.get("dispatch_digest"))
    _successful_run(api,row.get("closure_run"),"Factory verified issue closure",
                    require_actor=False)
    comments=api.get(f"/issues/{issue_number}/comments?per_page=100")
    _require(isinstance(comments,list) and len(comments)<100,
             "Issue audit comments could be truncated")
    audited=[c for c in comments
             if c.get("user",{}).get("type")=="Bot"
             and isinstance(c.get("body"),str)
             and (match:=AUDIT.search(c["body"]))
             and int(match.group(1))==issue_number]
    _require(len(audited)==1,"Expected exactly one trusted closure audit")
    body=audited[0]["body"]
    _require('"should_close": true' in body and
             '"merge_sha": "'+merge+'"' in body and
             '"pr_number": '+str(pr_number) in body,
             "Closure audit lacks accepted merge and PR evidence")
    return {"issue":issue_number,"pr":pr_number,"merge_sha":merge,
            "closed_at":issue.get("closed_at"),"head_sha":head}


def verify_fault(api,row,name):
    _require(isinstance(row,dict),"Missing fault injection record")
    run=_successful_run(api,row.get("run_id"),"Factory fault injection canary")
    _artifact(api,run["id"],"factory-fault-"+name+"-proof",row.get("digest"))
    jobs=api.get(f"/actions/runs/{run['id']}/jobs?per_page=100")
    records=jobs.get("jobs")
    _require(type(jobs.get("total_count")) is int
             and jobs["total_count"]<=100 and isinstance(records,list),
             "Fault injection job evidence truncated")
    _require(any(j.get("name")==name and j.get("status")=="completed"
                 and j.get("conclusion")=="success" for j in records),
             "Actual hosted fault assertion was not exercised")


def verify_phase(api,evidence,*,repo,phase):
    _require(evidence.get("schema_version")==1
             and evidence.get("repository")==repo
             and evidence.get("mode")=="live",
             "Evidence is not from this live repository")
    main=api.get("/git/ref/heads/main").get("object",{}).get("sha")
    _require(isinstance(main,str) and SHA.fullmatch(main),
             "Trusted main ref unavailable")
    deliveries=evidence.get("deliveries")
    _require(isinstance(deliveries,list) and len(deliveries)==2
             and all(isinstance(r,dict) for r in deliveries),
             "Exactly two distinct real Issue deliveries required")
    first,second=deliveries
    _require(first.get("issue")!=second.get("issue")
             and first.get("pr")!=second.get("pr"),
             "Live deliveries must be distinct")
    if phase in {"first","all"}:
        verify_delivery(api,first,main,repository=repo)
    if phase in {"second","all"}:
        result_first=verify_delivery(api,first,main,repository=repo)
        result_second=verify_delivery(api,second,main,repository=repo)
        _require(result_first["closed_at"] and result_second["closed_at"]
                 and result_first["closed_at"] < result_second["closed_at"],
                 "Second task was not completed after first Issue closure")
    faults=evidence.get("faults")
    if phase in {"recovery","negative","all"}:
        _require(isinstance(faults,dict),"Missing fault-injection evidence")
        kinds=RECOVERY if phase=="recovery" else NEGATIVE if phase=="negative" else RECOVERY+NEGATIVE
        for kind in kinds:
            verify_fault(api,faults.get(kind),kind)
    return {"phase":phase,"verified_main_sha":main,"deliveries":2,
            "recovery_cases":len(RECOVERY),"negative_cases":len(NEGATIVE)}


def load_evidence(path: Path | None, raw_json: str | None) -> dict:
    """Load an operator-supplied evidence manifest without inventing proof."""
    if path is not None:
        raw = path.read_text(encoding="utf-8")
    elif isinstance(raw_json, str) and raw_json.strip():
        raw = raw_json
    else:
        raise UnverifiedLiveDelivery("Live evidence JSON input is required")
    try:
        evidence = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise UnverifiedLiveDelivery("Live evidence JSON is malformed") from exc
    if not isinstance(evidence, dict):
        raise UnverifiedLiveDelivery("Live evidence must be a JSON object")
    return evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("first","recovery","negative","second","all"),
                        required=True)
    parser.add_argument("--evidence",type=Path)
    args=parser.parse_args()
    repo=os.environ.get("GITHUB_REPOSITORY","")
    token=os.environ.get("GH_TOKEN","")
    if not REPO.fullmatch(repo) or not token:
        raise SystemExit("BLOCKED: authenticated read-only GitHub context missing")
    try:
        proof=load_evidence(args.evidence,os.environ.get("FACTORY_LIVE_EVIDENCE_JSON",""))
        class ReadAPI:
            def get(self,path):
                if not path.startswith("/") or "://" in path:
                    raise UnverifiedLiveDelivery("Unsafe GitHub request")
                req=request.Request(
                    "https://api.github.com/repos/"+repo+path,
                    headers={"Authorization":"Bearer "+token,
                             "Accept":"application/vnd.github+json"})
                with request.urlopen(req,timeout=20) as res:
                    return json.load(res)
        result=verify_phase(ReadAPI(),proof,repo=repo,phase=args.phase)
    except (OSError,ValueError,KeyError,TypeError):
        raise SystemExit("BLOCKED: real, independently verified factory evidence unavailable")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
