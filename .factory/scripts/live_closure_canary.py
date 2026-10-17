"""Authenticate the live post-merge closure section of an autonomous canary.

This is intentionally narrower than proving autonomous lease/dispatch/repair;
it cannot substitute for those still-missing transitions.
"""
from __future__ import annotations
import re

SHA = re.compile(r"^[a-f0-9]{40}$")
AUDIT = re.compile(
    r"<!-- FACTORY_CLOSURE_AUDIT_V1 issue=(\d+) main=([a-f0-9]{40}) -->"
)


def prove_closure(
    *, issue: dict, comments: list[dict], current_main_sha: str,
    linked_pr: dict, required_criteria: tuple[str, ...],
) -> list[str]:
    errors = []
    number = issue.get("number")
    if type(number) is not int or issue.get("state") != "closed":
        errors.append("Canary Issue is not actually closed")
    if not isinstance(current_main_sha, str) or not SHA.fullmatch(current_main_sha):
        errors.append("Current default-branch SHA missing")
    merge_sha = linked_pr.get("merge_commit_sha")
    if (not linked_pr.get("merged_at")
            or not isinstance(merge_sha, str) or not SHA.fullmatch(merge_sha)):
        errors.append("No immutable merged PR record")
    if number and not re.search(
        r"(?m)^Refs #" + str(number) + r"\s*$",
        linked_pr.get("body") or ""
    ):
        errors.append("PR lacks explicit Issue association")
    audits = []
    for comment in comments:
        if (comment.get("user", {}).get("type") != "Bot"
                or not isinstance(comment.get("body"), str)):
            continue
        match = AUDIT.search(comment["body"])
        if match and int(match.group(1)) == number:
            audits.append((match.group(2), comment["body"]))
    if len(audits) != 1:
        errors.append("Expected exactly one bot-authored closure audit")
    elif not (audits[0][0] == merge_sha or audits[0][0] == current_main_sha):
        # The trusted audit is pinned to a committed main SHA, but the current
        # main may have advanced. A real git ancestry check is still required.
        errors.append("Audited main SHA does not match supplied commit")
    else:
        text = audits[0][1]
        if any(f'"id": "{ac}"' not in text for ac in required_criteria):
            errors.append("Audit lacks at least one accepted criterion")
        if '"should_close": true' not in text:
            errors.append("Audit did not verify closure eligibility")
    return errors
