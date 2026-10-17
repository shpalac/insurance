# Verified post-merge Issue closure

Automatic closure is **enabled only when the post-merge verifier proves every AC** on the exact current `main` SHA. Merging a `Refs #N` PR does **not** by itself close an Issue.

## Runtime

`.github/workflows/factory-verified-closure.yml` runs when a successful push-to-main **Factory selective CI** workflow completes, hourly as a missed-event reconciler, or manually via `workflow_dispatch`. An Issue edit performed by the repository owner also requests prompt reconciliation; edits by other actors remain covered by the hourly fallback. Jobs are serialized.

1. **verify:** read-only GitHub token, checks that `main` has successful `unit-tests`, `factory-bootstrap-gate`, and `factory-gate-preflight` check runs at the exact head SHA. Enumerates merged PRs explicitly containing `Refs #N`; their merge commits must be ancestors of `main`.
2. Reads each linked open Issue's one valid `yaml factory-acceptance-manifest` block, then runs **all** registered acceptance targets from `.factory/acceptance-targets.json` in an unprivileged GitHub-hosted runner. Commands in Issue text are never executed.
3. Each target must produce a successful nonempty JUnit report with positive assertion count. The verification step uploads the resulting reports and passes an SHA-bound proof to the separate write step.
4. **close:** has `issues:write` but **never executes acceptance tests**. Revalidates current main SHA, required CI checks, Issue body digest, merged PR ancestry, criterion mapping and complete evidence; writes an idempotent audit comment, then closes the completed Issue.
5. Missing/invalid manifests, unsupported runners, unknown targets, missing tests, stale CI, failing tests and partial multi-PR acceptance leave Issues open. A single sticky status comment records the current blocking reason for already merged linked Issues.

## Proof and limitations

Review approval is **not required**. A passing current-head CI gate and complete acceptance proof are required. The proof is linked to the GitHub Actions run with uploaded JUnit artifacts (30-day retention); the closure audit comment records the main SHA, merged PR numbers/SHAs and criterion results indefinitely.

**Initial implementation supports `ubuntu-latest` acceptance only.** macOS and Windows acceptance are never misrepresented as verified on Linux; they remain open until separate trusted hosted-runner evidence exists.

Current older factory Issues #2–#8 were authored before executable acceptance manifests and do not automatically qualify for closure even when their initial scaffolding PRs merge. They must be migrated to valid manifests with registered targets and validated on `main`, or remain open.

The workflow does **not** run a persistent LLM daemon, create tests automatically, grant missing GitHub permissions, or authorize live trading. In a public repository, never put secrets, accounts, PII, or broker data into Issue bodies or logs.

## Required GitHub settings

Enable Actions' repository token permission to write Issues for this workflow as permitted by repository/org policy. Keep `main` protected by required check names. GitHub Actions scheduled runs are best-effort; the workflow provides an hourly reconciliation fallback and manual dispatch. Automation fails closed if GitHub APIs are unavailable or the required CI evidence is incomplete.

## Local tests

```bash
python3 -m pip install -r .factory/requirements-dev.txt
python3 -m unittest discover -s .factory/tests -v
```

## Required PR-time completion gate

Every `pull_request` runs a dedicated `issue-completion` CI job as a mandatory upstream dependency of `factory-gate-preflight`.

- Use `Refs #N` for a partial delivery; no closure is promised and regular CI gates still apply.
- Add a standalone `Completes #N` alongside `Refs #N` only when every Issue acceptance criterion has a trusted registered test target, all those tests are runnable on GitHub-hosted Ubuntu, and their JUnit evidence passes on that exact PR head SHA.
- `Completes` without `Refs`, missing/invalid Issue manifests, unknown tests, missing assertions and native `Closes/Fixes/Resolves` keywords fail CI. Issue author-supplied commands are not executed.
- On merge, GitHub does **not** interpret `Completes` as native auto-close. The existing post-main validator reruns the tests on `main` and closes the Issue with an audit. A failed post-main run leaves it open.

**Repository branch protection matters:** configure a ruleset requiring `factory-gate-preflight`, `factory-bootstrap-gate` and `unit-tests` before allowing merges. Without a required-check ruleset, GitHub can permit an owner to merge a failing PR; the completion system will still refuse to close it, but cannot prevent an unsafe merge. CI-only review policy does not disable these checks.

Older Issues #2–#8 are **migration work**, not automatic green results. Each must receive a structured manifest, verified trusted test targets, and remaining missing features before close. Do not change the meaning of existing ACs just to turn their Issues green.

## PR acceptance traceability

The trusted `Factory PR acceptance traceability` workflow reacts only to successful pull-request `Factory selective CI` runs. It fetches the associated check-run jobs, verifies the PR's current head SHA, and posts/updates a single bot-owned acceptance comment listing each criterion, trusted target identity, requested runner, PR-gate result and immutable CI run URL. A partial PR is marked PARTIAL, never PASS. The privileged publisher checks out `main` only, cannot execute fork/PR code, and is not an alternative source of closure authority; `post_merge_closure.py` independently reruns all targets on `main`.

PR-body edits trigger CI again so a stale green check cannot be reused to add or remove a completion claim.

## Independent GitHub branch-rule enforcement audit

The read-only `Factory branch protection audit` workflow checks GitHub's **effective** main rulesets or classic branch protection for the three required contexts: `unit-tests`, `factory-bootstrap-gate`, and `factory-gate-preflight`. The audit fails if GitHub does not expose complete enforced rules; it never attempts to change repository settings or relax a gate. Run it manually from Actions or inspect its daily schedule. Without a green branch-enforcement audit, do not assert that an owner cannot bypass required CI. Reviewer approval is not required by the CI-only policy.
