# Definition of done

A Developer is done when scoped code and tests are in a reviewable PR with required gates green. A Reviewer is done after independent recorded review. An Integrator is done only after merge to `main`, post-merge CI and full acceptance evidence, immutable audit, and idempotent Issue closure.

The factory itself is *not operational* until the happy-path and fault-injection canaries prove dispatch, lease fencing, CI repair, independent review, merge, closure, and recovery on hosted runners.
