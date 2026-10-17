"""Validate the audited closure segment of the autonomous canary.

This proof helper is not itself a live end-to-end canary. A real canary must
also demonstrate Issue intake, lease ownership, PR/merge transitions, recovery,
and queue advancement with authoritative GitHub evidence.
"""
from __future__ import annotations
import re

SHA = re.compile(r"^[a-f0-9]{40}$")
AUDIT = re.compile(r"<!-- FACTORY_CLOSURE_AUDIT_V1 issue=(\d+) main=([a-f0-9]{40}) -->")


def prove_closure(
    *, issue: dict, comments: list[dict], current_main_sha: str,
    linked_pr: dict, required_criteria: tuple[str, ...],
    is_ancestor=lambda ancestor, descendant: ancestor == descendant,
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
    else:
        audited_sha, body = audits[0]
        if not SHA.fullmatch(audited_sha) or not is_ancestor(audited_sha, current_main_sha):
            errors.append("Audited main SHA is not an ancestor of current main")
        if not (audited_sha == merge_sha or is_ancestor(merge_sha, audited_sha)):
            errors.append("Audit does not include the linked PR merge")
        if any(f'"id": "{ac}"' not in body for ac in required_criteria):
            errors.append("Audit lacks at least one accepted criterion")
        if '"should_close": true' not in body:
            errors.append("Audit did not verify closure eligibility")
    return errors
