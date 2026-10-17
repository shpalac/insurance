# Failure recovery policy — target specification

Bound deterministic CI repairs by `limits.max_ci_repair_attempts`. Track normalized diff hashes; repeated hashes stop the loop. Rebase retries are bounded. Infra errors are classified separately from compile/test failures. Flakes require an issue and continued blocking until policy-authorized resolution.

After an expired lease, fence the old agent and resume from the last verified commit/checkpoint. After a `main` regression, halt merges and open a verified revert PR. Never silently make a failing test optional.
