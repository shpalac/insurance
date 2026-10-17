# Backend-neutral agent dispatch and queue progression

## Trust boundary

The orchestrator's public workflow remains read-only. A separate
`workflow_run` child checks out `main` with persisted credentials disabled and
accepts only successful schedule or Issue-event runs from `main`. It never
runs candidate PR code with dispatch secrets.

Dispatch is off by default. The owner must explicitly enable
`FACTORY_AGENT_DISPATCH_ENABLED`, set `orchestration.enabled: true`, add
approved agent logins and provider identifiers to `.factory/config.yaml`, and
provision a GitHub App token that can read Issues/Actions and perform the
non-forced lease-state ref CAS. The production `factory-lease-state` branch
must be provisioned separately; the controller never initializes it implicitly.

## Provider-neutral gateway contract

`agent_dispatch_contract.py` constructs an envelope bound to the issue lease,
epoch, revision, role, branch, checkpoint SHA and idempotency key. Provider
identifiers must be in the owner-configured allowlist. A gateway implementation
must durably deduplicate submissions by that key and return the same receipt
for retries.

`agent_dispatch.py` uses a generic HTTPS gateway. A role-specific token
(`FACTORY_AGENT_TOKEN_PLANNER`, `FACTORY_AGENT_TOKEN_CI_ENGINEER`, or
`FACTORY_AGENT_TOKEN_INTEGRATOR`) is sent only in the Authorization header;
it is never included in the envelope or logged. Redirects are rejected so the
credential cannot be forwarded to another host. The endpoint must return a
receipt and echo the idempotency key.

## Checkpoints and queue progression

The Git ref lease store uses immutable commit snapshots and non-forced CAS
updates. A live lease prevents a second claim; branch and commit checkpoints
survive process restarts. A closed issue's lease is retired by a CAS before the
controller selects the next eligible task. The bounded planner prioritizes
main regressions, merge blockers and failing PRs ahead of ready Issues, skips
active leases, and enforces `max_concurrent_agents`. A truncated open-Issue
listing fails closed instead of treating missing Issues as complete.

## Live activation gate

No external dispatch is sent unless a successful
`Factory live CI repair end-to-end canary` exists for the exact current
`main` SHA. The canary must independently prove a real failing job, a
lease-fenced repair, repaired-head verification and required-check rerun.
Missing secrets, an unconfigured provider, a missing lease-state branch, or
missing canary evidence leaves the system disabled; none of these conditions
is replaced with simulated live success.
