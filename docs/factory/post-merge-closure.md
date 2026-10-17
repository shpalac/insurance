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
