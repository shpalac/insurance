#!/usr/bin/env python3
"""Single-writer, fail-closed GitHub PR integration coordinator.

Only a trusted default-branch workflow executes this file. A GitHub App token
is required: GITHUB_TOKEN-induced branch updates do not trigger normal PR CI.
One invocation performs at most one branch update OR one guarded merge.
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib import request, error

import yaml
from github_ref_leases import GitHubRefLeaseStore
from lease_fencing import WorkerProof, assert_fence
from lease_state import StaleLease

REQUIRED = ("unit-tests", "factory-gate-preflight", "factory-bootstrap-gate",
            "issue-completion", "factory-trusted-admission")
SHA = re.compile(r"^[a-f0-9]{40}$")
AUTH = re.compile(r"^FACTORY-OWNER-AUTH sha=([a-f0-9]{40}) reason=.{12,300}$")
MARKER = "<!-- FACTORY_PR_RESYNC_V1 -->"


def ordered(prs: list[dict]) -> list[dict]:
    """Deterministic FIFO; drafts and other-repository PRs never enter queue."""
    return sorted((p for p in prs if p.get("state") == "open" and
                   not p.get("draft") and p.get("base", {}).get("ref") == "main"),
                  key=lambda p: (p.get("created_at") or "", p.get("number", 0)))


def check_gate(checks: list[dict], sha: str) -> bool:
    """No failed, missing or stale required context can be merged."""
    if not SHA.fullmatch(sha):
        return False
    for name in REQUIRED:
        matching = [c for c in checks if c.get("name") == name
                    and c.get("head_sha") == sha
                    and c.get("status") == "completed"]
        if not matching or any(c.get("conclusion") != "success" for c in matching):
            return False
    return True


def approved(comments: list[dict], owner: str, sha: str) -> bool:
    return any(c.get("user", {}).get("login", "").lower() == owner.lower()
               and (m := AUTH.fullmatch((c.get("body") or "").strip()))
               and m.group(1) == sha for c in comments)


def select(prs: list[dict], main_sha: str, repo: str,
           files_by_pr: dict[int, list[str]], comments_by_pr: dict[int, list[dict]],
           checks_by_pr: dict[int, list[dict]], owner: str) -> dict:
    """Exactly one non-forced action; protects authorization and main SHA."""
    if not SHA.fullmatch(main_sha):
        return {"action": "blocked", "reason": "invalid_main_sha"}
    for pr in ordered(prs):
        n = pr["number"]
        head = pr.get("head") or {}
        sha = head.get("sha", "")
        if (not SHA.fullmatch(sha) or
                ((head.get("repo") or {}).get("full_name") or "").lower() != repo.lower()):
            continue
        if pr.get("mergeable") is not True or pr.get("mergeable_state") in ("dirty", "unknown"):
            continue
        paths = files_by_pr.get(n)
        if not isinstance(paths, list) or not paths or len(paths) >= 100:
            continue
        protected = any(p.startswith((".factory/", ".github/workflows/"))
                        or p in ("AGENTS.md", "SECURITY.md") for p in paths)
        authorized = not protected or approved(comments_by_pr.get(n, []), owner, sha)
        # A behind PR is updated first, without force. New HEAD requires
        # a new owner authorization and new exact-commit required checks.
        behind = pr.get("mergeable_state") == "behind" or pr.get("behind_main") is True
        if behind:
            return {"action": "update", "number": n, "head_sha": sha,
                    "main_sha": main_sha, "owner_reapproval": protected}
        if not authorized:
            continue
        if pr.get("mergeable_state") not in ("clean", "has_hooks"):
            continue
        if check_gate(checks_by_pr.get(n, []), sha):
            return {"action": "merge", "number": n, "head_sha": sha,
                    "main_sha": main_sha}
    return {"action": "idle", "main_sha": main_sha}


def resync_summary(previous_count: int, update_events: list[tuple[str, str]]) -> dict:
    """Count update attempts and resulting stable cycles, never invent latency."""
    if previous_count < 0:
        raise ValueError("Negative re-sync attempts")
    unique = {(head, base) for head, base in update_events}
    return {"resync_count": previous_count + len(unique),
            "resync_per_pr": previous_count + len(unique),
            "under_one": previous_count + len(unique) < 1}


class API:
    def __init__(self, repo: str, token: str):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not token:
            raise ValueError("Repo and distinct app token are required")
        self.root = "https://api.github.com/repos/" + repo
        self.token = token

    def call(self, method: str, path: str, data=None):
        if not path.startswith("/") or "://" in path:
            raise ValueError("Invalid GitHub API path")
        headers = {"Authorization": "Bearer " + self.token,
                   "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        encoded = json.dumps(data).encode() if data is not None else None
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        with request.urlopen(request.Request(self.root + path, method=method,
               headers=headers, data=encoded), timeout=25) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}

    def get(self, path: str):
        return self.call("GET", path)


def live_integrator_fence(api: API, pr: dict, repo: str) -> bool:
    """Agent-driven branch updates and merges require an active lease.

    The check is performed against the remote immutable lease state before
    every privileged GitHub action. Native owner-driven PR merges remain
    governed by the separately enforced GitHub branch rules.
    """
    from pathlib import Path
    config = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "config.yaml").read_text()
    )
    if config["orchestration"]["enabled"] is not True:
        return False
    allowed = set(config["orchestration"].get("approved_agent_logins", []))
    identity = os.environ.get("FACTORY_INTEGRATOR_LOGIN", "")
    matches = re.findall(r"(?m)^Refs #([1-9][0-9]*)\\s*$",
                         pr.get("body") or "")
    if not identity or identity not in allowed or len(matches) != 1:
        return False
    store = GitHubRefLeaseStore(repo, api.token, write_enabled=False)
    lease = store.read(int(matches[0]))
    if lease is None:
        return False
    proof = WorkerProof(
        lease.entity, lease.epoch, lease.revision, lease.owner,
        lease.role, lease.branch, lease.commit_sha,
    )
    try:
        assert_fence(
            store, proof=proof, operation="integrator_merge",
            authenticated_login=identity, approved_logins=allowed,
            now=datetime.now(timezone.utc),
            actual_branch=(pr.get("head") or {}).get("ref", ""),
            actual_sha=(pr.get("head") or {}).get("sha", ""),
        )
    except StaleLease:
        return False
    return True


def tick(api: API, repo: str, owner: str) -> dict:
    main = api.get("/branches/main")
    if main.get("protected") is not True:
        raise ValueError("main branch rules are not enforced")
    sha = main["commit"]["sha"]
    prs = api.get("/pulls?state=open&base=main&per_page=100")
    if not isinstance(prs, list) or len(prs) >= 100:
        raise ValueError("Truncated PR queue")
    files, comments, checks = {}, {}, {}
    for pr in ordered(prs):
        n = pr["number"]
        paths = api.get(f"/pulls/{n}/files?per_page=100")
        if not isinstance(paths, list) or len(paths) >= 100:
            continue
        files[n] = [x["filename"] for x in paths]
        c = api.get(f"/issues/{n}/comments?per_page=100")
        if len(c) >= 100:
            continue
        comments[n] = c
        checked = api.get(f"/commits/{pr['head']['sha']}/check-runs?per_page=100")
        if checked.get("total_count", 101) > 100:
            continue
        checks[n] = checked.get("check_runs", [])
    action = select(prs, sha, repo, files, comments, checks, owner)
    if action["action"] not in {"update", "merge"}:
        return action
    # Race fencing: every action re-reads head/base immediately beforehand.
    if api.get("/branches/main")["commit"]["sha"] != sha:
        return {"action": "stale", "reason": "main moved"}
    n = action["number"]
    latest = api.get(f"/pulls/{n}")
    if (latest["head"]["sha"] != action["head_sha"]
            or latest["base"]["sha"] != sha
            or latest.get("state") != "open"):
        return {"action": "stale", "reason": "PR head/base moved"}
    if not live_integrator_fence(api, latest, repo):
        return {"action": "blocked", "reason": "active_integrator_lease_required"}
    if action["action"] == "update":
        # GitHub API compares expected_head_sha and creates a normal merge
        # commit on the contributor branch. Never force-push.
        api.call("PUT", f"/pulls/{n}/update-branch",
                 {"expected_head_sha": action["head_sha"]})
    else:
        if latest.get("mergeable_state") != "clean":
            return {"action": "stale", "reason": "Mergeability changed"}
        api.call("PUT", f"/pulls/{n}/merge",
                 {"sha": action["head_sha"], "merge_method": "squash"})
    return action


def main() -> int:
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token = os.getenv("FACTORY_INTEGRATOR_TOKEN", "")
    if not token:
        print(json.dumps({"mode": "disabled", "reason":
              "Owner must provision a narrowly scoped GitHub App token; "
              "GITHUB_TOKEN does not trigger candidate branch CI"}))
        return 0
    try:
        print(json.dumps(tick(API(repo, token), repo, os.getenv(
            "GITHUB_REPOSITORY_OWNER", "")), sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, error.HTTPError, OSError) as exc:
        print("ERROR: guarded merge coordinator blocked:", type(exc).__name__,
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
