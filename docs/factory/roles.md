# Role-scoped work contracts

Orchestrator prioritizes regressions, failed PRs, ready Issues, then triage; claims only through fenced durable lease state and must not modify application code. Planner creates atomic dependency-ordered Issues but not code. Issue Validator ensures every AC maps to an automated hosted-runner test and may promote an Issue to ready when identity policy allows.

Developer writes red-to-green tests, scoped implementations, and linked PRs; cannot weaken tests or self-review/merge. Reviewer independently evaluates design, edge cases, security, tests, scope, and manifest fidelity; never pushes on Developer's branch. CI Engineer tunes dependency graphs, caches, and flake diagnosis without bypassing required checks.

Integrator admits approved green PRs to configured merger, verifies `main` and complete acceptance, writes a closure audit and idempotently closes the Issue. Maintainer handles protected policy/workflow changes and security reviews.

**These are contracts, not yet activated permission enforcement.** Roles require distinct authenticated identities. See [agent assignment](agent-assignment.md).
