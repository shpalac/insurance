# Role-scoped work contracts

Orchestrator prioritizes regressions, failed PRs, ready Issues, then triage; claims only through fenced durable lease state and must not modify application code. Planner creates atomic dependency-ordered Issues but not code. Issue Validator ensures every AC maps to an automated hosted-runner test and may promote an Issue to ready when identity policy allows.

Developer writes red-to-green tests, scoped implementations, and linked PRs; cannot weaken tests or bypass required gates. Reviewer is an optional advisory role, not a prerequisite to merge. CI Engineer tunes dependency graphs, caches, and flake diagnosis without bypassing required checks.

Integrator admits CI-green, authorized PRs without independent approval, verifies `main` and complete acceptance, writes a closure audit and idempotently closes the Issue. Maintainer controls protected policy/workflow authorization; a second-person review is not mandatory.

**These are contracts, not yet activated permission enforcement.** Roles require distinct authenticated identities. See [agent assignment](agent-assignment.md).
