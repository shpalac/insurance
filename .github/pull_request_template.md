Refs #N
Completes #N

## Completion intent
**Default: one Issue = one finishing PR.** Replace both `#N` placeholders with the actual Issue number. Every acceptance criterion must have a real, registered CI test before merge. The mandatory completion gate rejects missing, skipped or failed AC tests; verified post-merge CI writes the closure audit and automatically closes the Issue.

For a legitimately partial PR, remove the `Completes #N` line and retain only `Refs #N`. Use a child Issue for further work or an Issue whose manifest explicitly declares `multi_pr_allowed: true`. A partial PR must never promise completion.

Do **not** use GitHub native `Closes/Fixes/Resolves #N`: those bypass the factory's post-merge acceptance audit.

## Change scope
What changed and why?

## Acceptance traceability
List AC-N identifiers, implementing files, and hosted-runner tests. Each `Completes #N` requires a full executable manifest in the Issue and registered trusted tests for **every** AC.

## Evidence
Paste relevant CI run links; never paste credentials, private data, or unredacted logs.

## Merge policy (CI-only)
Independent review is not required. Merge only when `factory-gate-preflight`, `issue-completion`, scanner and policy tests pass on the **current** head and the PR is conflict-free.

## Protected-path authorization
Changes to workflows, permissions, security or protected paths still need owner/policy authorization; a green test does not grant authorization.
