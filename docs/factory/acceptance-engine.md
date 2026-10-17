# Executable acceptance accompanies every Issue implementation

An Issue's **acceptance criteria are the specification**, and the implementation must ship a matching, durable test for every criterion. GitHub Actions does not execute commands from Issue bodies. New work uses the repo-owned `.factory/scripts/acceptance_discovery.py` convention; older reviewed entries in `.factory/acceptance-targets.json` continue to work during migration.

## Convention for new Issues

For GitHub Issue `#N` with `AC-1`, `AC-2`, ... add:

```text
.factory/acceptance/issue_N/test_ac_1.py
.factory/acceptance/issue_N/test_ac_2.py
...
```

Each test file defines `unittest.TestCase` methods named `test_ac_1_<behavior>` (for `AC-1`), etc. Each method must perform at least one runtime `self.assert*` assertion. **No edits to a central mapping are needed.** Acceptance coverage is computed from the Issue manifest and repository contents at the current tested commit SHA.

Issue authors should express observable outcomes, not test runner commands. The illustrative `command` property in an Issue is linted but **never executed**. Tests can exercise production code, real contracts, input rejection and fault injection; a passing trivial assertion is not proof of sound behavior, so reviewers and factory checks must ensure the test assertions reflect the AC.

## CI and closure state machine

1. Issue validation rejects missing/malformed/non-deterministic acceptance metadata, untrusted shell instructions and manual-only requirements.
2. A PR refers to the Issue using `Refs #N`. An unprivileged `issue-completion` job discovers every criterion's named tests and runs them against the exact current PR head. The job emits real JUnit with counted assertions and rejects failures, skips and missing cases.
3. If all tests are present, *all* are mandatory before merging. If the Issue explicitly allows multiple PRs and only a subset is implemented, shipped subset tests must pass; the parent remains open. Single-PR Issues without a complete suite fail the PR gate. This allows incremental delivery without false closure.
4. All required CI and admission safeguards still govern merges; no completion marker or human reviewer is required by the factory's CI-only policy. Changing test files does not grant protected-path write authorization.
5. On `main`, the read-only post-merge job reruns the acceptance suite, checks merged PR ancestry and default-branch CI, creates an immutable per-criterion proof, then a separate privileged job audits and closes the Issue **once**. `Closes/Fixes/Resolves` do not bypass the audit.
6. Co-shipped tests remain in the repository as permanent regressions, and a mandatory factory CI job also reruns them after the Issue is closed.

## Security and efficiency

- Never evaluate user-supplied shell commands or pass API tokens into acceptance subprocesses. Credentialed Issue fetching occurs in a separate step; privileged close/apply is in a different job.
- Test discovery rejects symlinks/unsafe paths, unrecognized method names, missing runtime assertions, and mismatched reports; verified evidence is bound to the tested SHA.
- Existing shared legacy unittest targets execute **once per unique command**, not once per criterion. Each AC still requires its own JUnit report. New co-shipped tests execute one file per criterion with bounded timeout.
- The permanent acceptance runner scans ordinary `issue_N/test_ac_K.py` files rather than using a hardcoded list. GitHub CI is the source of truth.
- Hosted Ubuntu remains the co-shipped default; macOS and Windows criteria execute on their actual hosted runners. JUnit reports and assertion counts are packaged with digest-indexed, exact-SHA artifacts. The post-merge verifier independently downloads and checks those artifacts against the same successful `main` CI run before closing an issue. External service credentials, branch protection settings, and autonomous worker dispatch must be configured separately; the factory fails closed instead of fabricating success.

## Example

```python
# .factory/acceptance/issue_123/test_ac_1.py
import unittest
from insurance.some_module import compute

class PricingAcceptance(unittest.TestCase):
    def test_ac_1_rejects_missing_market_data(self):
        with self.assertRaises(ValueError):
            compute(market_data=None)
```

The implementation author adds this test **in the same PR** as the production change. No `Completes #123` or manual registry update is needed.
