# Definition of done

A Developer is done when scoped code and tests are in a PR with required CI and acceptance gates green. Review is optional for every Issue, including protected-path changes (which still require policy/owner authorization). An Integrator is done only after merging the exact tested head to `main`, post-merge CI and full acceptance evidence, immutable audit, and idempotent Issue closure.

The factory itself is *not operational* until the happy-path and fault-injection canaries prove dispatch, lease fencing, CI repair, CI-only merge admission, closure, and recovery on hosted runners.

Automated completion is implemented by [the post-merge closure workflow](post-merge-closure.md): verified current-main checks, full trusted target acceptance, merged PR ancestry, immutable audit, and idempotent closure. A green PR alone does not close the Issue. Non-Linux criteria remain blocked until their runner evidence is implemented.
