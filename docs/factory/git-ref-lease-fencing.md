# Git-ref CAS lease isolation and stale worker fencing

The software factory's durable lock is a **Git ref compare-and-fast-forward**
state machine; the source of truth is GitHub, not process memory. One immutable
commit contains `.factory/lease-state.json`, whose `version: 1` lease map
records entity, revision, epoch, owner/role, timestamped heartbeat/expiry,
checkpoint SHA, repair attempts and diff hashes. Every mutation builds a child
commit from the read ref and writes it with `force: false`. A concurrent
candidate from the same ancestor is non-fast-forward and loses the CAS;
callers must re-read state rather than silently retrying stale work.

## Isolated hosted proof

`Factory isolated lease CAS canary` is a **trusted-main-only** Actions
workflow triggered by the first merge or manual dispatch. It creates
`factory-lease-canary-<run_id>` as a fresh orphan Git ref (no production
state, no overwrite), then two **independent GitHub-hosted Ubuntu workers**
race to acquire the same Issue number. A final read-only job confirms a
single surviving generation and exactly one worker success. Evidence is
associated with the workflow's immutable tested SHA and artifacts; a
fail-closed post-merge checker blocks Issue #44 closure without a successful
same-main-SHA hosted run containing all four jobs. The isolated test refs
are intentionally left for traceability, not silently deleted.

## Worker fencing and capacity

A trusted controller must validate a worker proof immediately before every
agent-initiated mutation: `branch_push`, `ci_repair`,
`issue_transition`, or `integrator_merge`. The proof contains Issue,
epoch, revision, authenticated owner and role, branch, and checkpoint SHA;
`assert_fence` compares it with the current durable lease, expiry and
role allowlist. Expired, transferred, blocked, non-matching or superseded
workers are denied. `acquire_bounded` evaluates active agents using an
immutable lease-map snapshot and a global ref CAS before committing a new
generation; the configured cap is 2.

A lease heartbeat extends expiry only under the same epoch; a checkpoint
records the exact branch/commit and changes to the normalized diff. Repeated
diff hashes or exhausted repair attempts lead to a durable blocked state.
Writes under the production ref `factory-lease-state` remain
**disabled by default**. An owner must provision narrowly scoped GitHub App
permissions, verify the state-ref bootstrap and isolated canary, enable a
trusted role-authenticated controller, and explicitly approve production
activation. No PR code, Issue instructions or source checkout gets a
privileged GitHub token.

## Safety caveat

The co-shipped unittest acceptance fixtures test the mathematical CAS and
fencing contracts. Those fixtures are **not** evidence of a hosted GitHub
race; the actual canary workflow must pass after merging. The post-merge
closure checks the separate trusted run before completing #44. Parent #7
remains open until its own acceptance conditions are satisfied.
