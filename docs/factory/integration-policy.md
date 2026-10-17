# Integrator policy and audited closure

The `integration_policy.py` module is a **pure decision engine**, deliberately incapable of GitHub writes. It must consume independently verified GitHub state snapshots, never assertions made by a PR author.

Before a merge, the exact PR head SHA must match both required `factory-gate` and `acceptance-gate` successes and impact integrity; the PR must be conflict-free, non-draft, on `main`, unblocked, approved by a distinct trusted reviewer on the current SHA, free of unresolved threads, within its executable Issue scope, and explicitly authorized for protected paths.

After merge, the Integrator must verify each Issue criterion in the *current* `main` tree using permanent registered regression tests. The closure planner requires passing evidence, nonzero assertions, artifact URLs, merge SHAs, a verified `main` SHA, and a criterion count of N/N. A partial multi-PR implementation remains open. Repeating an audit for an already closed Issue is a no-op.

**Not deployed:** automatic queue admission, GitHub branch protection configuration, independent reviewer credentials, mutable closure workflow, and default-branch post-merge evidence collection. Do not treat the pure policy tests as proof that a live GitHub integration is safe to enable.
