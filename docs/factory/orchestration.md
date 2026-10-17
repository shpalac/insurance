# Orchestration queue — target behavior

Priority: failing `main` regressions; merge blockers; open failing PRs; dependency-ready Issues; triage. Dispatch to isolated workers only after authorization and lease acquisition. Concurrency is bounded by configuration and overlapping write scopes must be serialized.

A webhook may trigger fast dispatch; scheduled reconciliation repairs missed events. Dispatch, CI repair, merging, and closure are intentionally disabled in the current bootstrap.
