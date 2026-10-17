# Integrator policy and audited closure

The `integration_policy.py` module is a **pure decision engine**, deliberately incapable of GitHub writes. It must consume independently verified GitHub state snapshots, never assertions made by a PR author.

Under `repository.review_policy: ci_only`, no reviewer approval or review-thread resolution is required. GitHub's current SHA, mandatory CI, acceptance and any owner/policy authorization still govern merge admission.

Before a merge, the exact PR head SHA must match both required `factory-gate` and `acceptance-gate` successes and impact integrity; the PR must be conflict-free, non-draft, on `main`, unblocked, within its executable Issue scope, and explicitly authorized for protected paths.

After merge, the Integrator must verify each Issue criterion in the *current* `main` tree using permanent registered regression tests. The closure planner requires passing evidence, nonzero assertions, artifact URLs, merge SHAs, a verified `main` SHA, and a criterion count of N/N. A partial multi-PR implementation remains open. Repeating an audit for an already closed Issue is a no-op.

**Post-merge reconciliation:** `.github/workflows/factory-verified-closure.yml` runs default-branch verification and uses a separate privileged job for audited Issue closure. See [runtime and limitations](post-merge-closure.md). **Still not deployed:** automatic merge queue admission, verified GitHub branch protection configuration, cross-OS acceptance tests, or full multi-agent orchestration. Do not treat the pure policy tests as proof that a live GitHub integration is safe to enable.
