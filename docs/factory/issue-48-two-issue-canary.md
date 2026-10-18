# Issue #48 — genuine two-Issue autonomous factory canary

The implementation PR provides the verifier and permanent regression tests, but **an
ordinary green CI run is not evidence of actual autonomous agent delivery**.

## Live run prerequisites

- Issues #35, #36, #37, #38, #39, #41, #43, #44, #45, #46 and #47 must be
  complete, and branch protection and trusted owner authorization must remain
  effective.
- Two distinct sandbox Issues must be executed by an approved external agent.
  Record each actual Issue ID, PR ID, merge SHA, approved GitHub identity,
  agent-dispatch workflow run and digest of its durable dispatch artifact,
  plus the verified-closure workflow run. Both Issues must be closed by a
  single bot-authored acceptance audit (one audit per Issue), not by closing
  keywords or manual closure.
- Capture hosted fault-injection cases: failing CI recovered within budget,
  interrupted worker resumed without duplicate PR, expired lease fenced,
  competing claims with exactly one winner, and bounded merge-conflict
  recovery. Also capture independent *negative* evidence for missing check,
  unapproved identity, protected path violation, malicious Issue content and
  stale SHA. Every case needs a successful GitHub-hosted verification job and
  immutable nonexpired artifact digest.

## External evidence index

The owner-controlled worker creates `.factory/live-evidence/issue_48.json`
through an authorized PR; this file is intentionally **not** generated from
mocked tests or placeholder run IDs. Its format:

```json
{
  "schema_version": 1,
  "mode": "live",
  "repository": "shpalac/insurance",
  "deliveries": [
    {
      "issue": 0,
      "pr": 0,
      "merge_sha": "<real 40-character SHA>",
      "agent_login": "<approved GitHub identity>",
      "dispatch_run": 0,
      "dispatch_digest": "sha256:<real digest>",
      "closure_run": 0
    }
  ],
  "faults": {
    "injected_ci_failure": {
      "run_id": 0,
      "digest": "sha256:<real digest>"
    }
  }
}
```

The example is **not valid evidence**: two distinct genuine deliveries and all
ten named fault cases are mandatory. The live verifier fetches every Issue, PR,
check-run, audit comment, Actions run and artifact directly from GitHub. The
external worker must publish `factory-agent-dispatch-proof` artifacts with
durable idempotency and lease evidence, and the fault-injection runner must
publish `factory-fault-<case>-proof` artifacts. A disabled dispatcher, skipped
job, synthetic success file or merely green contract unit tests are rejected.

After the authorized evidence PR merges, trigger **Factory two-issue autonomous
delivery canary** manually against `main`. Its independent first-Issue,
fault-recovery, negative-admission, second-Issue and final attestation stages
must all pass. The final job uploads a digest-bearing
`factory-two-issue-live-evidence` artifact. The post-merge closure audit then
rechecks this exact-main run and the artifact and may close #48. Its proof is
bound to the same SHA in both prepare and privileged apply.

Until real worker authentication, gateway credentials, live fault-injection
runtime and signed-off GitHub run evidence exist, #48 must remain open. Never
disable a required gate or invent an artifact to obtain closure.
