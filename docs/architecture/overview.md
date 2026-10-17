# Architecture

The repository currently contains only factory bootstrap policy, configuration, and validation tests. No insurance product architecture exists yet. Product implementation must receive separately scoped, executable Issues.

Target flow: Issue → validated acceptance → fenced lease → role-assigned worker → PR + tests → selective CI → independent review → merge → `main` verification → audited Issue closure.

`AGENTS.md` is the agent entry point. `.factory/config.yaml` is the repository adapter. GitHub owns source, backlog, workflow evidence, and immutable merge/closure audit references.
