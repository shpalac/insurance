# Issue #48 live acceptance evidence

Issue #48 is not closable merely because its four named Python acceptance tests
pass. Those tests verify the fail-closed verifier and its contracts; the closure
gate separately requires real hosted evidence for every acceptance criterion.

## Why the original canary could not run

The canary workflow referenced
`.factory/live-evidence/issue_48.json`, but that file was not present in the
repository and there was no step that created it. This created a dead end:
every canary job failed before it could attest evidence. The workflow now
requires the operator to supply the evidence manifest as the
`workflow_dispatch` input `evidence_json`. The JSON is passed through an
environment variable, parsed as data, and never evaluated as shell or Python.

## Required evidence manifest

The input must be a JSON object with this shape. The values below are field
descriptions, **not passing evidence**; replace them only with identifiers and
digests copied from completed GitHub runs and artifacts.

```json
{
  "schema_version": 1,
  "repository": "shpalac/insurance",
  "mode": "live",
  "deliveries": [
    {
      "issue": 0,
      "pr": 0,
      "merge_sha": "<real-merge-sha>",
      "dispatch_run": 0,
      "agent_login": "<real-approved-agent-login>",
      "dispatch_digest": "sha256:<real-artifact-digest>",
      "closure_run": 0
    },
    {
      "issue": 0,
      "pr": 0,
      "merge_sha": "<real-merge-sha>",
      "dispatch_run": 0,
      "agent_login": "<real-approved-agent-login>",
      "dispatch_digest": "sha256:<real-artifact-digest>",
      "closure_run": 0
    }
  ],
  "faults": {
    "injected_ci_failure": {"run_id": 0, "digest": "sha256:<real-artifact-digest>"},
    "worker_interruption": {"run_id": 0, "digest": "sha256:<real-artifact-digest>"},
    "expired_lease": {"run_id": 0, "digest": "sha256:<real-artifact-digest>"},
    "simultaneous_claim": {"run_id": 0, "digest": "sha256:<real-artifact-digest>"},
    "merge_conflict": {"run_id": 0, "digest": "sha256:<real-artifact-digest>"},
    "missing_required_check": {"run_id": 0, "digest": "sha256:<real-artifact-digest>"},
    "unapproved_identity": {"run_id": 0, "digest": "sha256:<real-artifact-digest>"},
    "protected_path": {"run_id": 0, "digest": "sha256:<real-artifact-digest>"},
    "malicious_issue_prompt": {"run_id": 0, "digest": "sha256:<real-artifact-digest>"},
    "stale_sha": {"run_id": 0, "digest": "sha256:<real-artifact-digest>"}
  }
}
```

For each delivery, the verifier fetches the actual closed Issue, merged PR,
merge ancestry, all five required checks on the immutable PR head, a successful
`Factory agent dispatch` run by the declared approved agent, its retained
`factory-agent-dispatch-proof` artifact and digest, a successful closure run,
and exactly one audited closure record tied to the merge SHA and PR number.

For each fault case, it fetches the actual successful `Factory fault injection
canary` run, the case-specific successful job, and its retained artifact with
the matching digest. Reusing synthetic IDs, fake digests, expired artifacts,
untrusted actors, or mocked-only proof fails verification.

## Completion sequence

1. Run genuine approved-agent delivery and closure for two distinct Issues.
2. Run the hosted fault-injection workflow for all five recovery and five
   negative-admission cases; retain each real artifact and SHA-256 digest.
3. Assemble the manifest from those immutable records and dispatch
   **Factory two-issue autonomous delivery canary** on `main`.
4. On a successful canary, **Factory verified issue closure** runs immediately
   and rechecks every criterion against the exact current `main` SHA.
5. If any record is missing, the Issue remains open and the status comment lists
   every criterion whose live evidence is still unproven.

The repository does not currently contain the live delivery/fault artifacts
needed to complete this sequence. Do not populate the manifest with placeholders
or treat this PR's unit tests as a substitute.
