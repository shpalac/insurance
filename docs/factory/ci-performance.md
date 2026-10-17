# Factory CI performance and lane ownership

## Source of truth and safety

The protected branch-required contexts remain unchanged: `unit-tests`,
`factory-bootstrap-gate`, `factory-gate-preflight`, `issue-completion`
and `factory-trusted-admission`. The read-only
`Factory CI performance metrics` workflow is **not a merge gate** and
cannot substitute for any of them. It receives a completed selective CI
workflow_run, checks out only trusted `main`, and reads GitHub Actions API
metadata; no candidate PR source is executed with credentials.

The versioned `factory-ci-performance-v1` artifact records the workflow
run ID, immutable head SHA, event, queue delay, total elapsed runtime,
current job statuses and durations, required status check conclusions,
changed file paths with API provenance, and lane-by-lane **p50/p95**
durations across up to 15 recent completed runs. The JSON explicitly marks
a missing/truncated changed-file listing as `paths_complete=false` and
`path_evidence=unavailable`. Missing required checks are `pending`,
never invented green results.

Metrics are observational and sampled; they are not a guarantee of runner
latency, continuous execution or total cost. The source timestamps are
supplied by GitHub Actions and duration percentiles use linear interpolation.

## Distinct CI responsibilities

- `Research scanner CI / unit-tests`: the stable branch-required Python
  test suite and README/CLI contracts.
- `Factory bootstrap / static-policy`: the single Ubuntu owner of the
  `.factory/tests` regression group, backed by the required
  `factory-bootstrap-gate`.
- `Factory selective CI / policy`: mandatory security scan, config
  validation and all permanent issue acceptance tests.
- `Factory selective CI / scanner`: selected changed-line **coverage
  measurement and ≥90% gate**, and explicit NO TRADE market data assertions;
  rerunning application tests here is required to collect coverage and is
  therefore a distinct measurement from `unit-tests`.
- `Factory selective CI / factory`: Python syntax for factory scripts
  and shipped acceptance test modules. It does not repeat the bootstrap suite.
- `macos` and `windows`: independent platform runs, intentionally distinct
  from Ubuntu. `acceptance-macos` and `acceptance-windows` remain mandatory
  for runner-specific acceptance proofs.
- `factory-gate-preflight`: immutable selective-coverage aggregate,
  rejects missing/failed/skipped mandatory jobs.

Docs-only impact plans skip scanner and native application builds, while
policy, secret scanning, permanent acceptance, issue completion, both hosted
acceptance runner checks and the aggregate gate remain mandatory. Unknown
or unavailable impacts trigger the full selective matrix. Pull request
concurrency cancels superseded builds, but never reuses their acceptance
or merge evidence for a different head SHA.

## Investigating an incident

Inspect the CI run's `factory-gate-preflight`, `issue-completion`, and
`factory-trusted-admission` check contexts before considering a merge.
Open the matching performance artifact to compare lane-level elapsed times;
source metadata may be delayed or incomplete, and cannot override required
GitHub branch protection.
