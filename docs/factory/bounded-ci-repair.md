# Bounded CI repair and conflict recovery

The factory repairs **specific, verified CI regressions** rather than
looping blindly. The trusted-main `Factory bounded CI repair dispatch`
workflow runs when `Factory selective CI` finishes unsuccessfully,
but is **disabled by default**. It needs an owner-approved
`FACTORY_REPAIR_ENABLED=true`, the GitHub App installation secret
`FACTORY_REPAIR_APP_TOKEN`, an active role allowlist, enabled factory
orchestration, and successfully completed dependencies #43, #44 and #45.
No production repairs, branch pushes or merges occur without these settings.

## Deterministic dispatch and idempotency

A trusted scheduler independently verifies the GitHub run ID, event,
immutable failing PR head SHA, single linked Issue, same-repository
source, all job results, the current lease owner and CI engineer role.
Only test and lint failures are eligible: policy/security, issue
completion, unknown failures and hidden diagnostics **never** grant
repair capability. The scheduler constructs a bounded SHA-derived
idempotency key and reserves it in the durable Git-ref CAS lease map,
requiring an active role, epoch, revision, owner, allowed branch and
exact checkpoint SHA. Parallel/duplicate events lose CAS or are already
reserved. It emits at most one provider-neutral `factory-ci-repair`
`repository_dispatch` envelope per run/head. It does **not** execute
Issue shell commands or PR files under privileged credentials.

The external agent must verify its lease again immediately before every
commit. No workflow grants `GITHUB_TOKEN` to unchecked candidate
code. A changed commit gets a **new SHA** and must run the complete
branch-required GitHub CI. A failed dispatch following a committed
reservation is not retried blindly; it requires trusted reconciliation.

## Recovery budgets and merge safety

The bounded policy is **maximum three unsuccessful repairs**, **maximum
two conflict-rebase recovery attempts**, and immediate block on
repeated normalized diff hashes. Exhaustion produces a stable
`three_unsuccessful_repairs`, `repeated_normalized_diff` or
`conflict_rebase_budget_exhausted` reason, rather than unbounded
retries. Authorized recovery may only create non-forced branch updates;
it may never delete tests, ignore failures, force-push over a different
worker, suppress security checks, or modify protected code without
fresh exact-head owner approval.

`approve_candidate` requires a current integrator lease and revision,
matching branch/commit identity, a conflict-free GitHub PR, exact main
SHA, **all five passing required checks**, and current-head
`FACTORY-OWNER-AUTH` when protected files changed. CI failures remain
a hard security boundary, not a suggestion.

## Readiness and live verification

The co-shipped acceptance tests exercise run/head-specific dispatch
selection, duplicate CAS rejection, the three/two retry budgets, and
negative merge/security/lease cases. They **do not establish that an
external agent actually repaired a real CI failure**. Do not enable
unattended repair or auto-close #46 until a privileged owner-run canary
with a real failing test, one agent repair, current-head CI rerun and
GitHub audit has succeeded. Main issue #7 retains its own contract.
