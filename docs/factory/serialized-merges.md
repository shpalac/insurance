# Strict up-to-date merge coordinator

The **Factory serialized PR integrator** is a trusted-main, single-writer
Actions workflow with one global concurrency group. It may update **one**
behind-main same-repository PR branch using the non-forcing GitHub
`update-branch` endpoint, or squash-merge **one** eligible current-head
PR. The deterministic queue orders by creation timestamp, then PR number.

The coordinator re-reads both `main` and the PR before acting and sends
the exact candidate SHA to the merge endpoint. A stale response, missing
required check, draft, fork, unverified mergeability, unprotected main,
or missing current-head owner authorization blocks integration. A PR branch
update produces a new commit and **must rerun required CI**; protected
changes also require a **new owner authorization** on the updated SHA.
No check is skipped, disabled, simulated or marked successful by this workflow.

## Activation prerequisite

Set `FACTORY_INTEGRATOR_TOKEN` to a narrowly scoped GitHub App
installation token with permission to update PR branches and merge PRs,
and ensure its Actions are permitted by GitHub rules. **Never use the
ephemeral `GITHUB_TOKEN` to update branches**: events caused by it will
not trigger the required candidate PR CI. Until owner provisioning, the
workflow reports `mode: disabled` without modifying PRs. The workflow
runs after selective CI or every 15 minutes, with a single concurrency
group. This serializes **its own** integration actions; externally
initiated merges remain governed by GitHub's strict branch rules.

The coordinator's `resync_summary` contract counts distinct expected
head/main resynchronization cycles. A no-race canary records a zero rate,
while any detected retry is surfaced rather than misreported as green.
An operational end-to-end canary should be performed before enabling
unattended integration.
