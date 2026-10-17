# Issue-specific acceptance execution

The static manifest validator (Issue #2) treats the Issue body as untrusted metadata. This stage adds a **trusted registry** at `.factory/acceptance-targets.json`; only a maintainer-reviewed registry edit can activate test targets. Arbitrary shell commands found in an Issue manifest are NEVER passed to a shell.

The unprivileged reusable workflow accepts a GitHub Issue ID and immutable head SHA, downloads its body for static validation, selects every required criterion or an explicitly declared subset, then resolves each criterion against its trusted registry entry. The registry requires `python3 -m unittest` argv, the expected hosted runner, and a report emitted under `reports/`.

A valid JUnit report must contain non-skipped, nonfailed tests with at least one explicitly reported assertion. Generic JUnit XML does not consistently record assertion counts; registered targets must add this instrumentation. A passing exit code alone is insufficient. Report outputs include criterion, head SHA, runner and evidence path.

**Still gated:** no trusted targets are registered by default; issue #2–#8 are not retroactively accepted or closed. Automatic PR-body linking, multi-PR accumulated evidence on `main`, cross-OS dispatcher, and a separate trusted status-comment publisher must be completed before authorizing automatic merges. This workflow cannot write Issues, PRs, or repository contents.
