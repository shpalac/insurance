# Orchestration and agent dispatch (Phase 6 foundation)

Orchestration is deliberately **read-only** until external LLM runtimes, authenticated GitHub App identities, branch rules, and full live canary evidence are configured. The scheduled workflow enumerates the backlog but cannot open PRs, push code, repair CI, or merge. Github scheduled workflow execution can be delayed and is not a guarantee of exact 5-minute intervals.

## Lease CAS contract

Use a dedicated GitHub state ref and a single serialized dispatcher. Each lease transition must be represented by a new immutable Git commit with the old state ref as its sole parent; the writer pushes only with `force=false`. Two simultaneous writers that read the same revision cannot both fast-forward a single ref. Increment a monotonic `lease_epoch` and require every worker mutation to check the current epoch and identity immediately before action. Expired agents are fenced from writing, even after their context is resumed elsewhere.

`.factory/scripts/lease_state.py` models claiming, heartbeat, checkpoint recovery, bounded repair and identical-diff oscillation detection with a CAS interface. Its in-memory store is **only a test adapter**, not a safe production lease backend. A Git-ref CAS implementation with real concurrent external runners is mandatory before activation.

## External agent integration

Agents receive work envelopes through an externally provisioned, least-privilege service; no model API credentials belong in this public repository. Envelopes contain role, Issue/PR, lease epoch, branch SHA, and checkpoint reference. Do not infer privileges from GitHub comments or Issue text. The runtime must supply a real GitHub App with scoped permissions and separate reviewer/integrator identities.

Keep `orchestration.enabled: false` until the state-ref integration, roles, CI/merge gates and canary all prove safe.
