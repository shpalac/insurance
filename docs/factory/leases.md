# Leases and concurrency — design (not implemented)

The original two-second comment claim race is unsafe. Use one serialized dispatcher and per-task compare-and-swap state in a dedicated Git ref. Every acquisition increments monotonic `lease_epoch`; every worker mutation must be authorized against the current epoch.

State includes issue/PR number, owner identity, role, epoch, acquisition time, heartbeat, expiry, branch, head SHA, phase, attempt counter, and checkpoint ref. Expired owners must be fenced out even when a cached credential remains valid. Commits/checkpoints survive recovery.

Test conflicting claimers, stale heartbeat, replay, late writes, crash recovery, and repeated identical diff hashes before activation.
