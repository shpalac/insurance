Refs #N

## Completion intent
For a PR that **fully finishes** all acceptance criteria of its linked Issue, add a standalone `Completes #N` line. This triggers the mandatory CI completion test and an audited post-merge closure. Omit `Completes` on partial PRs.

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
