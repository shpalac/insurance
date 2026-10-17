# Phase 7 end-to-end autonomous canary

**This repository is not operational as an autonomous factory until a live canary and fault-injection recovery prove every expected transition.** Static tests, local simulations, and synthetic JSON evidence are not proof of live operation.

The canary must exercise real GitHub hosted runners, independent authorized reviewer and integrator identities, a dedicated harmless executable issue and branch, target-specific acceptance tests, required factory gates, a squash merge, post-merge `main` verification, an immutable closure audit, and advancement to a second independent task.

Faults must include manual-only acceptance rejection, a deterministic failing test repaired within retry budget, expiry and takeover of a live lease, stale-agent fencing, failed required gate rejection, and rejection of unauthorized merge attempts.

`.factory/scripts/verify_canary_evidence.py` supplies only **structural** evidence preflight and fails closed on missing steps, wrong repositories, empty commit SHAs or missing artifact digests. An independent verifier must additionally fetch workflow runs, commit ancestry, approval identities, artifact bytes and closure state directly through GitHub APIs. Do not enable `orchestration.enabled` or live trading as a result of a synthetic preflight.

**Blockers:** Issues #2–#7 require merges and audited verification. Active GitHub App identities, external LLM workers, CAS reference store, branch protection, and a secure acceptance bridge must be provisioned and tested before running the live canary.
