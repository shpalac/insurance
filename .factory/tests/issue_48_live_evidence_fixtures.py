"""Deterministic fixture for testing the live-evidence verifier's contract.

Fixtures exercise the verifier only. They are deliberately never accepted as
the real hosted canary by post_merge_closure.verify_live_two_issue_canary.
"""
from __future__ import annotations

MAIN_SHA = "a" * 40
REPO = "shpalac/insurance"
REQUIRED_CHECKS = (
    "unit-tests", "factory-gate-preflight", "factory-bootstrap-gate",
    "issue-completion", "factory-trusted-admission",
)
RECOVERY = (
    "injected_ci_failure", "worker_interruption", "expired_lease",
    "simultaneous_claim", "merge_conflict",
)
NEGATIVE = (
    "missing_required_check", "unapproved_identity", "protected_path",
    "malicious_issue_prompt", "stale_sha",
)
ALL_FAULTS = RECOVERY + NEGATIVE


def make_evidence():
    deliveries = []
    for index, (issue, pr, merge, head, dispatch, closure, closed_at) in enumerate((
        (900, 910, "b" * 40, "c" * 40, 501, 502, "2026-10-17T12:00:00Z"),
        (901, 911, "d" * 40, "e" * 40, 503, 504, "2026-10-17T12:10:00Z"),
    )):
        deliveries.append({
            "issue": issue, "pr": pr, "merge_sha": merge, "head_sha": head,
            "dispatch_run": dispatch, "dispatch_digest": "sha256:" + str(index + 1) * 64,
            "agent_login": "factory-worker", "closure_run": closure,
            "closed_at": closed_at,
        })
    faults = {
        name: {"run_id": 600 + index, "digest": "sha256:" + format(index + 1, "064x")}
        for index, name in enumerate(ALL_FAULTS)
    }
    return {
        "schema_version": 1, "repository": REPO, "mode": "live",
        "deliveries": deliveries, "faults": faults,
    }


class EvidenceAPI:
    """Small explicit GitHub API model with per-route overrides for negative tests."""

    def __init__(self, evidence=None, overrides=None):
        self.evidence = evidence or make_evidence()
        self.overrides = overrides or {}
        self.deliveries = {row["issue"]: row for row in self.evidence["deliveries"]}
        self.by_pr = {row["pr"]: row for row in self.evidence["deliveries"]}
        self.runs = {}
        for row in self.evidence["deliveries"]:
            self.runs[row["dispatch_run"]] = {
                "id": row["dispatch_run"], "name": "Factory agent dispatch",
                "status": "completed", "conclusion": "success",
                "actor": {"login": row["agent_login"]},
            }
            self.runs[row["closure_run"]] = {
                "id": row["closure_run"], "name": "Factory verified issue closure",
                "status": "completed", "conclusion": "success",
                "actor": {"login": "github-actions[bot]"},
            }
        self.faults_by_run = {
            row["run_id"]: (name, row)
            for name, row in self.evidence.get("faults", {}).items()
        }
        for run_id in self.faults_by_run:
            self.runs[run_id] = {
                "id": run_id, "name": "Factory fault injection canary",
                "status": "completed", "conclusion": "success",
                "actor": {"login": "factory-worker"},
            }

    def get(self, path):
        if path in self.overrides:
            return self.overrides[path]
        if path == "/git/ref/heads/main":
            return {"object": {"sha": MAIN_SHA}}
        if path.startswith("/issues/") and path.endswith("/comments?per_page=100"):
            issue = int(path.split("/")[2])
            row = self.deliveries[issue]
            body = (
                f"<!-- FACTORY_CLOSURE_AUDIT_V1 issue={issue} main={MAIN_SHA} -->\n"
                '{ "should_close": true, "merge_sha": "'
                + row["merge_sha"] + '", "pr_number": ' + str(row["pr"]) + " }"
            )
            return [{"user": {"type": "Bot"}, "body": body}]
        if path.startswith("/issues/") and "?" not in path:
            issue = int(path.rsplit("/", 1)[1])
            row = self.deliveries[issue]
            return {"number": issue, "state": "closed", "closed_at": row["closed_at"]}
        if path.startswith("/pulls/") and "?" not in path:
            pr = int(path.rsplit("/", 1)[1])
            row = self.by_pr[pr]
            return {
                "number": pr, "state": "closed", "merged_at": row["closed_at"],
                "merge_commit_sha": row["merge_sha"], "base": {"ref": "main"},
                "body": f"Refs #{row['issue']}\n\nAcceptance tests included.",
                "head": {"sha": row["head_sha"]},
            }
        if path.startswith("/compare/"):
            return {"status": "ahead", "behind_by": 0}
        if path.startswith("/commits/") and path.endswith("/check-runs?per_page=100"):
            head = path.split("/")[2]
            return {"total_count": len(REQUIRED_CHECKS), "check_runs": [
                {"name": name, "head_sha": head, "status": "completed",
                 "conclusion": "success"} for name in REQUIRED_CHECKS
            ]}
        if path.startswith("/actions/runs/") and path.endswith("/artifacts?per_page=100"):
            run_id = int(path.split("/")[3])
            if run_id in self.faults_by_run:
                name, row = self.faults_by_run[run_id]
                artifact_name, digest = f"factory-fault-{name}-proof", row["digest"]
            else:
                delivery = next(
                    row for row in self.evidence["deliveries"]
                    if run_id in (row["dispatch_run"], row["closure_run"])
                )
                artifact_name, digest = "factory-agent-dispatch-proof", delivery["dispatch_digest"]
            return {"total_count": 1, "artifacts": [
                {"id": run_id + 1000, "name": artifact_name,
                 "expired": False, "digest": digest}
            ]}
        if path.startswith("/actions/runs/") and path.endswith("/jobs?per_page=100"):
            run_id = int(path.split("/")[3])
            name, _ = self.faults_by_run[run_id]
            return {"total_count": 1, "jobs": [
                {"name": name, "status": "completed", "conclusion": "success"}
            ]}
        if path.startswith("/actions/runs/") and "?" not in path:
            return self.runs[int(path.rsplit("/", 1)[1])]
        raise AssertionError("Unexpected GitHub API path: " + path)
