# Factory efficiency metrics

The versioned, scheduled **Factory efficiency dashboard** reads GitHub Issues,
merged PRs, Actions run conclusions, owner-authored PR comments and the sticky
worker idle watch reports. It archives `factory-efficiency-v1.json` (90-day
artifact retention), then a separate minimal writer updates one bot-owned
`FACTORY_EFFICIENCY_METRICS_V1` comment on tracking Issue #71. The tracking
comment remains useful after #71 is closed. Nothing here is a merge or
acceptance gate; the collector runs with read-only permissions on trusted
`main`, never with broker credentials or untrusted code.

## Definitions

- **Lead time:** Closed Issue `closed_at - created_at`, in hours, across the
  bounded sample of closed Issues. Report median, mean and sample count.
- **CI failure rate:** `failure / (success + failure)` among completed
  sampled Actions workflow runs. Skipped, queued, canceled and timed-out runs
  are not success or failure observations under this narrow definition.
- **PRs per Issue:** Number of unique merged PRs with standalone `Refs #N`
  lines for each Issue. Mean across Issues with at least one linked merged
  PR; additional merged PRs expose implementation fragmentation/rework.
- **Merges per hour:** Number of sampled PRs merged within the trailing
  24 hours divided by 24. This is a throughput rate, not a latency measure.
- **Worker idle time:** Sum and mean of the *latest observed stalled idle
  seconds* from the #73 watchdog's bot-owned status comments. This is a
  sampled snapshot, not a cumulative wall-clock idle duration; unavailable
  lease state produces no measurements, not a fabricated zero.
- **Human interventions:** Count of authenticated repository-owner
  `FACTORY-OWNER-AUTH` PR comments in the sampled merged PRs. Other
  interventions (e.g. GitHub ruleset changes, private account settings,
  out-of-band repairs) are **not observed** by the available GitHub endpoints
  and are therefore explicitly outside this count.

## Sampling and integrity

The collector limits discovery to five GitHub Issues pages, five closed PR
pages and 100 latest Actions workflow runs, failing closed on incomplete
Issue/PR pagination rather than claiming full historical coverage. Counts
include `sample` and `coverage_limits` metadata; no data beyond this
window is inferred. Every API request is authenticated, but untrusted Issue
or PR prose is processed only to extract standalone `Refs` identifiers and
known bot-owned labels. No developer shell command is sourced from Issue
text. Publication updates only one marker-tagged bot comment, never Issue
state, code, leases or review gates.

The workflow runs every six hours and can be dispatched manually.
Comparisons should use the same metric version and account for data
sampling bounds, CI concurrency and watchdog coverage before inferring a
performance change.
