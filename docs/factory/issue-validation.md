# Issue validation and readiness

`issue-validation.yml` is activated only when this PR is merged to the default branch. GitHub Issue webhooks are untrusted. Validator code executes from the trusted default branch. It never executes commands from Issue bodies.

Only a sender username listed in `orchestration.approved_agent_logins` may successfully validate a well-formed executable manifest. With the initial empty list, every Issue remains in `status:triage`. Before activating, authorized maintainers must provision those identities and `status:triage` / `status:ready` labels and independently review changes to the validation workflow.

On each event, the workflow evaluates manifest schema, runner constraints, scope paths, command syntax, and matching Issue identity. It makes an idempotent ready/triage label transition; invalid, incomplete, or unauthorized Issues never enter the implementation queue. It does not confer role tokens or execute issue-supplied code.

Issue label removal/update requires `issues:write` in this trusted workflow only. It never checks out a PR head or a contributor-supplied branch.
