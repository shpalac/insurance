# Worker idle watchdog

A scheduled (15-minute cadence) read-only job reads the versioned
`factory-lease-state` Git ref and reports claimed or repairing Issue
leases that have seen no heartbeat, branch commit or linked PR update within
`FACTORY_STALL_THRESHOLD_MINUTES` (default 45, valid 15–1440).
Dates are timezone-aware and the observation records exact last-activity and
sample times, idle duration in seconds, lease epoch and owner. If the
lease-state ref has not been provisioned, the artifact explicitly says
`lease_state_unavailable`; it does not claim the factory is idle.

A separate token-scoped publisher may create or update one bot-owned
`FACTORY_STALL_WATCH_V1` status comment per stalled Issue. It never
mutates a lease, dispatches workers, merges PRs, touches issue status or
changes code. The scan job has only read permissions; all output is
machine-readable in a 90-day GitHub Actions artifact
`factory-worker-idle-v1`, intended as source evidence for efficiency
metrics #71. No secrets or freeform Issue bodies enter public reports.

Comments are observational, not proof of a broken agent. A worker that
does not publish GitHub activity may be reported as stalled even while
doing useful offline work. Audit using worker checkpoints before reassigning.
