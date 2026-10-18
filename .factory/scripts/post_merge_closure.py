#!/usr/bin/env python3
"""Post-merge acceptance reconciliation. Never close an Issue on PR text alone.

Two-step protocol:
  prepare: read-only token; run allowlisted acceptance tests against current main.
  apply: issues:write token; verify immutable proof + current remote state, then audit/close.

No Issue-provided shell commands are evaluated. Absence of any proof fails closed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib import error, parse, request

from integration_policy import closure_progress
from acceptance_discovery import DiscoveryError, available_criteria
from run_acceptance_manifest import AcceptanceError, load_targets, run_criteria
from cross_os_proof import CrossOSProofError, verified_hosted_rows
from lease_canary_proof import HostedLeaseCanaryMissing, verify_live_lease_canary
from two_issue_canary import LiveTwoIssueCanaryMissing, verify_live_two_issue_canary
from validate_issue_manifest import extract_manifest, validate_body

ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REQUIRED_JOBS = ("unit-tests", "factory-bootstrap-gate", "factory-gate-preflight")
STATUS_MARKER = "<!-- FACTORY_CLOSURE_STATUS_V1 -->"
AUDIT_PREFIX = "<!-- FACTORY_CLOSURE_AUDIT_V1 "
MAX_ISSUES = 25  # bounded amount of mutation/proof per reconciliation run
MAX_ISSUES_FETCH = 10000  # explicit fail-closed discovery ceiling
MAX_PRS = 15000  # grows beyond the original 1000-PR history ceiling


class ReconcileError(RuntimeError):
    pass


class GitHub:
    def __init__(self, repo: str, token: str):
        if not REPO.fullmatch(repo) or not token:
            raise ReconcileError("Missing repository or authentication")
        self.repo = repo
        self.token = token
        self.base = "https://api.github.com/repos/" + repo

    def call(self, method: str, endpoint: str, data: dict | None = None):
        if not endpoint.startswith("/") or "://" in endpoint:
            raise ReconcileError("Invalid API endpoint")
        url = "https://api.github.com/repos/" + self.repo + endpoint
        payload = json.dumps(data).encode() if data is not None else None
        req = request.Request(url, data=payload, method=method, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if payload is not None else {}),
        })
        try:
            with request.urlopen(req, timeout=25) as response:
                raw = response.read()
        except (error.HTTPError, error.URLError) as exc:
            raise ReconcileError(f"GitHub {method} request failed ({getattr(exc, 'code', 'network')})") from exc
        return json.loads(raw) if raw else {}

    def get(self, endpoint: str):
        return self.call("GET", endpoint)

    def post(self, endpoint: str, data: dict):
        return self.call("POST", endpoint, data)

    def patch(self, endpoint: str, data: dict):
        return self.call("PATCH", endpoint, data)

    def pages(self, endpoint: str, *, limit: int = 1000):
        """Never use a truncated result set to authorize closure."""
        found = []
        for page in range(1, limit // 100 + 2):
            separator = "&" if "?" in endpoint else "?"
            batch = self.get(f"{endpoint}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise ReconcileError("Unexpected GitHub pagination payload")
            if len(found) + len(batch) > limit:
                raise ReconcileError("Pagination cap exceeded; refusing incomplete evidence")
            found.extend(batch)
            if len(batch) < 100:
                return found
        raise ReconcileError("Incomplete pagination")


def reconciliation_window(issues: list[dict], run_id: int,
                          batch_size: int = MAX_ISSUES) -> list[dict]:
    """Bound each run, rotate deterministically, never silently drop backlog."""
    if not isinstance(issues, list) or not isinstance(run_id, int) or run_id < 0:
        raise ReconcileError("Invalid issue cursor inputs")
    if batch_size < 1 or batch_size > MAX_ISSUES:
        raise ReconcileError("Invalid bounded reconciliation batch")
    ordered = sorted((x for x in issues if "pull_request" not in x),
                     key=lambda x: x.get("number", 0))
    pages = max(1, (len(ordered) + batch_size - 1) // batch_size)
    chosen = run_id % pages
    return ordered[chosen * batch_size:(chosen + 1) * batch_size]


def durable_report_fields(row: dict, root: Path = ROOT) -> dict:
    """Pin tested report bytes in a permanent audit, not only a 30-day URL."""
    path = row.get("artifact")
    if isinstance(row.get("report_sha256"), str):
        h = row["report_sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", h):
            raise ReconcileError("Malformed hosted report digest")
        report = row.get("report", path)
    else:
        if not isinstance(path, str) or not path.startswith("reports/"):
            raise ReconcileError("Missing JUnit evidence path")
        file = (root / path).resolve()
        if not file.is_relative_to(root.resolve()) or not file.is_file():
            raise ReconcileError("Missing current-run acceptance report")
        h = hashlib.sha256(file.read_bytes()).hexdigest()
        report = path
    if (not isinstance(report, str) or not report.startswith("reports/")
            or type(row.get("assertions")) is not int or row["assertions"] < 1
            or type(row.get("testcases")) is not int or row["testcases"] < 1
            or row.get("runner", "ubuntu-latest") not in
            {"ubuntu-latest", "macos-latest", "windows-latest"}):
        raise ReconcileError("Incomplete durable JUnit identity")
    return {"report": report, "report_sha256": h,
            "runner": row.get("runner", "ubuntu-latest"),
            "testcases": row["testcases"], "assertions": row["assertions"]}


def current_main(api: GitHub) -> str:
    ref = api.get("/git/ref/heads/main")
    sha = ref.get("object", {}).get("sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ReconcileError("Invalid main ref SHA")
    return sha


def require_main_checks(api: GitHub, sha: str):
    if current_main(api) != sha:
        raise ReconcileError("Head changed; retry on the new main SHA")
    result = api.get(f"/commits/{sha}/check-runs?per_page=100")
    checks = result.get("check_runs")
    if not isinstance(checks, list) or result.get("total_count", 0) > 100:
        raise ReconcileError("Missing or truncated check-run evidence")
    for name in REQUIRED_JOBS:
        valid = [check for check in checks if
                 check.get("name") == name and check.get("head_sha") == sha
                 and check.get("app", {}).get("slug") == "github-actions"
                 and check.get("status") == "completed"
                 and check.get("conclusion") == "success"]
        if not valid:
            raise ReconcileError(f"Required default-branch check not green: {name}")


def is_ancestor(api: GitHub, merge_sha: str, main_sha: str) -> bool:
    if merge_sha == main_sha:
        return True
    result = api.get(f"/compare/{merge_sha}...{main_sha}")
    return result.get("status") in ("ahead", "identical") and result.get("behind_by") == 0


def linked_merged_prs(issue: int, prs: list[dict], api: GitHub, sha: str):
    """Only completed PRs targeting main with explicit Refs #N and ancestry."""
    token = re.compile(r"(?im)^\s*Refs\s+#" + str(issue) + r"\s*$")
    found = []
    for pr in prs:
        if (not isinstance(pr, dict) or not pr.get("merged_at")
                or pr.get("base", {}).get("ref") != "main"
                or not isinstance(pr.get("body"), str)
                or not token.search(pr["body"])):
            continue
        merge_sha = pr.get("merge_commit_sha")
        if not isinstance(merge_sha, str) or not SHA.fullmatch(merge_sha):
            continue
        if is_ancestor(api, merge_sha, sha):
            found.append({"number": pr["number"], "merge_sha": merge_sha})
    return sorted(found, key=lambda item: item["number"])


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def prepare(api: GitHub, sha: str, run_id: int, *, run=run_criteria):
    require_main_checks(api, sha)
    all_issues = api.pages("/issues?state=open", limit=MAX_ISSUES_FETCH)
    issues = reconciliation_window(all_issues, run_id)
    prs = api.pages("/pulls?state=closed&base=main", limit=MAX_PRS)
    plan = {"schema_version": 1, "main_sha": sha, "run_id": run_id,
            "scanned_count": len(all_issues), "batch_size": MAX_ISSUES,
            "items": []}
    for issue in issues:
        number = issue.get("number")
        if type(number) is not int:
            continue
        refs = linked_merged_prs(number, prs, api, sha)
        if not refs:
            continue
        body = issue.get("body") or ""
        item = {
            "issue": number, "body_digest": digest(body), "prs": refs,
            "status": "blocked", "reason": "invalid_or_missing_manifest",
            "criteria": [], "evidence": [],
        }
        errors = validate_body(body, expected_issue_id=number)
        if not errors:
            manifest = extract_manifest(body)
            item["criteria"] = [ac["id"] for ac in manifest["acceptance_criteria"]]
            # Report unimplemented ACs in a durable artifact for autonomous
            # triage; no Issue-authored code or commands run during discovery.
            try:
                available = available_criteria(
                    ROOT, number, item["criteria"], load_targets(ROOT)
                )
                item["missing_criteria"] = [
                    ac for ac in item["criteria"] if ac not in available
                ]
            except (DiscoveryError, OSError, ValueError):
                item["missing_criteria"] = list(item["criteria"])
            try:
                    linux = {ac["id"] for ac in manifest["acceptance_criteria"]
                             if ac["runner_os"] == "ubuntu-latest"}
                    results = (run(body, issue_id=number, head_sha=sha,
                                   root=ROOT, criteria_subset=linux) if linux else [])
                    required_os = {}
                    for criterion in manifest["acceptance_criteria"]:
                        if criterion["runner_os"] != "ubuntu-latest":
                            required_os.setdefault(criterion["runner_os"], []).append(
                                (number, criterion["id"]))
                    if required_os:
                        hosted = verified_hosted_rows(api, sha, required_os)
                        results.extend(hosted[(number, ac)]
                                       for os_name, names in required_os.items()
                                       for _, ac in names)
                    results.sort(key=lambda row: int(row["id"].split("-")[1]))
                    if [r["id"] for r in results] != item["criteria"]:
                        raise AcceptanceError("Acceptance coverage is incomplete")
                    for row in results:
                        if (row.get("status") != "PASS"
                                or type(row.get("testcases")) is not int
                                or row["testcases"] < 1
                                or type(row.get("assertions")) is not int
                                or row["assertions"] < 1
                                or row.get("head_sha") != sha):
                            raise AcceptanceError("Incomplete acceptance proof")
                    latest = refs[-1]
                    evidence = [{
                        "id": row["id"], "verified_main_sha": sha,
                        "status": "PASS", "assertions": row["assertions"],
                        "permanent_regression": True,
                        "artifact_url": f"https://github.com/{api.repo}/actions/runs/{run_id}",
                        "merge_sha": latest["merge_sha"], "pr_number": latest["number"],
                    } for row in results]
                    for row, proof in zip(results, evidence):
                        proof.update(durable_report_fields(row))
                    if number == 44:
                        if api.get("/issues/43").get("state") != "closed":
                            raise HostedLeaseCanaryMissing("Identity dependency #43 is open")
                        item["hosted_canary"] = verify_live_lease_canary(api, sha)
                    if number == 48:
                        item["two_issue_canary"] = verify_live_two_issue_canary(api, sha)
                    audit = closure_progress(
                        criteria_ids=item["criteria"], evidence=evidence, main_sha=sha
                    )
                    if not audit["should_close"]:
                        raise AcceptanceError("Some acceptance criteria were not proven")
                    item["status"] = "ready"
                    item["reason"] = "all_acceptance_green_on_main"
                    item["evidence"] = evidence
            except LiveTwoIssueCanaryMissing:
                    item["reason"] = "acceptance_incomplete_or_untrusted_target"
                    # The named tests exist, but every criterion remains unproven
                    # until real hosted delivery and fault-injection evidence passes.
                    item["unproven_criteria"] = list(item["criteria"])
                    item["evidence_blocker"] = "live_two_issue_canary_not_verified"
                    print(f"Issue #{number}: acceptance blocked (LiveTwoIssueCanaryMissing)")
            except (AcceptanceError, CrossOSProofError, HostedLeaseCanaryMissing, OSError, ValueError) as exc:
                    item["reason"] = "acceptance_incomplete_or_untrusted_target"
                    # Do not leak stdout, stderr, or issue-supplied strings into public comments.
                    print(f"Issue #{number}: acceptance blocked ({type(exc).__name__})")
        plan["items"].append(item)
    if len(json.dumps(plan)) > 50000:
        raise ReconcileError("Proof exceeds safe output size")
    return plan


def audit_marker(issue: int, sha: str) -> str:
    return f"{AUDIT_PREFIX}issue={issue} main={sha} -->"


def existing_comments(api: GitHub, issue: int) -> list[dict]:
    return api.pages(f"/issues/{issue}/comments", limit=500)


def blocked_message(item: dict, sha: str) -> str:
    reason = item["reason"]
    if reason not in {
        "invalid_or_missing_manifest",
        "unsupported_runner_pending_hosted_verification",
        "acceptance_incomplete_or_untrusted_target",
    }:
        raise ReconcileError("Untrusted blocking reason")
    missing = item.get("missing_criteria", [])
    unproven = item.get("unproven_criteria", [])
    for values, label in (
        (missing, "missing-criteria"),
        (unproven, "unproven-criteria"),
    ):
        if (not isinstance(values, list) or len(values) > 100
                or any(not isinstance(ac, str)
                       or not re.fullmatch(r"AC-[1-9][0-9]*", ac)
                       for ac in values)
                or len(set(values)) != len(values)):
            raise ReconcileError(f"Unsafe {label} diagnostics")
    blocker = item.get("evidence_blocker")
    if blocker not in (None, "live_two_issue_canary_not_verified"):
        raise ReconcileError("Unsafe evidence blocker diagnostic")
    details = (
        "- Missing acceptance implementations: " + ", ".join(missing) + "\n"
        if missing else ""
    )
    proof_details = (
        "- Acceptance criteria without verified proof: "
        + ", ".join(unproven) + "\n"
        if unproven else ""
    )
    blocker_details = (
        "- Live-evidence blocker: `live_two_issue_canary_not_verified`\n"
        if blocker else ""
    )
    next_step = (
        "- Provide genuine hosted delivery and fault-injection evidence for the listed criteria; mocked tests alone do not satisfy the live canary.\n"
        if unproven else
        "- Implement every missing criterion in .factory/acceptance/issue_N/test_ac_K.py.\n"
    )
    return (
        f"{STATUS_MARKER}\n"
        "Post-merge completion remains **blocked**; the Issue is intentionally open.\n\n"
        f"- Verification main SHA: {sha}\n"
        f"- Reason: `{reason}`\n"
        + details + proof_details + blocker_details
        + "- The linked PR has merged, but the complete executable acceptance contract "
        "has not been verified on the current default branch.\n"
        "- CI-only review policy waives independent review, not acceptance tests.\n"
        + next_step
    )

def apply(api: GitHub, sha: str, plan: dict):
    if plan.get("schema_version") != 1 or plan.get("main_sha") != sha:
        raise ReconcileError("Proof is not bound to current SHA")
    require_main_checks(api, sha)
    items = plan.get("items")
    if not isinstance(items, list) or len(items) > MAX_ISSUES:
        raise ReconcileError("Invalid issue proof set")
    if len({item.get("issue") for item in items if isinstance(item, dict)}) != len(items):
        raise ReconcileError("Duplicate issue records")
    closed = []
    blocked = []
    for item in items:
        number = item.get("issue")
        if type(number) is not int or number < 1:
            raise ReconcileError("Malformed Issue number")
        issue = api.get(f"/issues/{number}")
        if issue.get("state") != "open" or "pull_request" in issue:
            continue
        body = issue.get("body") or ""
        if digest(body) != item.get("body_digest"):
            blocked.append({"issue": number, "reason": "issue_spec_changed"})
            continue
        refs = item.get("prs", [])
        if not refs:
            raise ReconcileError("Missing linked merged PR")
        for entry in refs:
            pr = api.get(f"/pulls/{entry['number']}")
            if (not pr.get("merged_at") or pr.get("merge_commit_sha") != entry["merge_sha"]
                    or pr.get("base", {}).get("ref") != "main"
                    or not re.search(r"(?<![A-Za-z0-9_])Refs?\s+#" + str(number) + r"\b",
                                     pr.get("body") or "", re.I)
                    or not is_ancestor(api, entry["merge_sha"], sha)):
                raise ReconcileError("Linked PR no longer verifies")
        comments = existing_comments(api, number)
        if item.get("status") != "ready":
            message = blocked_message(item, sha)
            old = next((c for c in comments if STATUS_MARKER in c.get("body", "")), None)
            if old and old.get("body") != message:
                api.patch(f"/issues/comments/{old['id']}", {"body": message})
            elif not old:
                api.post(f"/issues/{number}/comments", {"body": message})
            blocked.append({"issue": number, "reason": item["reason"]})
            continue
        errors = validate_body(body, expected_issue_id=number)
        if errors:
            blocked.append({"issue": number, "reason": "manifest_changed_or_invalid"})
            continue
        criteria = [ac["id"] for ac in extract_manifest(body)["acceptance_criteria"]]
        if criteria != item.get("criteria"):
            raise ReconcileError("Proof criterion mismatch")
        evidence = item.get("evidence", [])
        if (len(evidence) != len(criteria) or
                any(e.get("pr_number") not in [p["number"] for p in refs]
                    or e.get("merge_sha") not in [p["merge_sha"] for p in refs]
                    or e.get("artifact_url") !=
                    f"https://github.com/{api.repo}/actions/runs/{plan['run_id']}"
                    for e in evidence)):
            raise ReconcileError("Invalid linked acceptance evidence")
        for proof in evidence:
            if (not re.fullmatch(r"[a-f0-9]{64}", proof.get("report_sha256") or "")
                    or not isinstance(proof.get("report"), str)
                    or not proof["report"].startswith("reports/")
                    or proof.get("runner") not in
                    {"ubuntu-latest", "macos-latest", "windows-latest"}
                    or type(proof.get("testcases")) is not int
                    or proof["testcases"] < 1):
                raise ReconcileError("Durable acceptance proof is incomplete")
        if number == 44:
            if api.get("/issues/43").get("state") != "closed":
                blocked.append({"issue": number, "reason": "identity_dependency_pending"})
                continue
            if item.get("hosted_canary") != verify_live_lease_canary(api, sha):
                raise ReconcileError("Hosted canary proof differs from immutable main")
        if number == 48:
            if item.get("two_issue_canary") != verify_live_two_issue_canary(api, sha):
                raise ReconcileError("Live two-issue proof differs from immutable main")
        decision = closure_progress(criteria_ids=criteria, evidence=evidence, main_sha=sha)
        if not decision["should_close"]:
            blocked.append({"issue": number, "reason": "incomplete_criteria"})
            continue
        if current_main(api) != sha:
            raise ReconcileError("Default branch changed during reconciliation")
        marker = audit_marker(number, sha)
        comment = next((c for c in comments if marker in c.get("body", "")), None)
        if not comment:
            decision["durable_reports"] = [{
                "criterion": proof["id"], "runner": proof["runner"],
                "testcases": proof["testcases"],
                "assertions": proof["assertions"],
                "report_path": proof["report"],
                "sha256": proof["report_sha256"],
            } for proof in evidence]
            decision["report_retention"] = {
                "hosted_artifacts_days": 30,
                "permanent_reference": sha,
                "explanation": "Hosted downloads expire; this audit retains the tested SHA and report digests.",
            }
            audit = json.dumps(decision, sort_keys=True, indent=2)
            api.post(f"/issues/{number}/comments", {
                "body": marker + "\nVerified automatic closure audit:\n\n"
                        + "~~~json\n" + audit + "\n~~~\n"
                        + "\nIndependent review is optional; acceptance and CI were required."
            })
        api.patch(f"/issues/{number}", {"state": "closed", "state_reason": "completed"})
        closed.append(number)
    return {"closed": closed, "blocked": blocked, "main_sha": sha}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("prepare", "apply"))
    p.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", ""))
    p.add_argument("--sha", required=True)
    p.add_argument("--run-id", type=int, default=int(os.getenv("GITHUB_RUN_ID", "0")))
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    if not SHA.fullmatch(args.sha):
        p.error("expected an exact 40-character main commit SHA")
    try:
        api = GitHub(args.repo, os.getenv("GH_TOKEN", ""))
        if args.mode == "prepare":
            if not args.output:
                raise ReconcileError("Prepare requires --output")
            plan = prepare(api, args.sha, args.run_id)
            args.output.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
            output = os.getenv("GITHUB_OUTPUT")
            if output:
                encoded = base64.b64encode(json.dumps(plan, sort_keys=True).encode()).decode()
                with open(output, "a", encoding="utf-8") as fp:
                    fp.write("proof=" + encoded + "\n")
            print(json.dumps({"status": "prepared", "items": len(plan["items"])}))
        else:
            encoded = os.getenv("CLOSURE_PROOF", "")
            if not encoded or len(encoded) > 80000:
                raise ReconcileError("Missing or oversized prior read-only proof")
            plan = json.loads(base64.b64decode(encoded, validate=True))
            print(json.dumps(apply(api, args.sha, plan), sort_keys=True))
    except (ReconcileError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: reconciliation failed closed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
