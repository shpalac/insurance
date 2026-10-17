# Definition of done

A Developer is done when scoped code and tests are in a PR with required CI and acceptance gates green. Review is optional for every Issue, including protected-path changes (which still require policy/owner authorization). An Integrator is done only after merging the exact tested head to `main`, post-merge CI and full acceptance evidence, immutable audit, and idempotent Issue closure.

The factory itself is *not operational* until the happy-path and fault-injection canaries prove dispatch, lease fencing, CI repair, CI-only merge admission, closure, and recovery on hosted runners.

Automated completion is implemented by [the post-merge closure workflow](post-merge-closure.md): verified current-main checks, full trusted target acceptance, merged PR ancestry, immutable audit, and idempotent closure. A green PR alone does not close the Issue. Non-Linux criteria remain blocked until their runner evidence is implemented.

## Automatic completion, no finishing PR required

Link every implementation PR with a standalone `Refs #N` line. The `issue-completion` CI job reads the trusted acceptance-target registry and automatically runs **all** criteria on the candidate head as soon as the Issue's test targets are fully registered; failures block the PR. A multi-PR Issue with targets not yet fully registered may merge a partial slice, but must stay open. Single-PR Issues must have full tests before merging.

After each successful `main` CI run, `factory-verified-closure.yml` independently gathers *all* merged `Refs #N` PRs, verifies current-main mandatory checks and full named test evidence, then writes one audit and closes the Issue. It does not require `Completes #N` or native GitHub closing keywords. It will not close an Issue whose acceptance tests or external prerequisites remain unverified. Live CI enforcement and autonomous merge admission require separately configured GitHub branch protections.
