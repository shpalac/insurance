# Architecture

This public repository contains two complementary modules:

1. **Options research scanner:** Python package at `src/insurance/` with read-only snapshot ingestion (`cli.py`), option validation and modeled payout research (`core.py`), volatility diagnostics (`backtest.py`), and SQLite deduplication (`storage.py`). Its unit tests reside in `tests/`. This is not a live broker connector or an execution service; model validation is incomplete, and outputs are **UNVERIFIED / NO TRADE**.
2. **Software factory:** role and workflow contracts in `AGENTS.md`, `.factory/config.yaml`, `.factory/scripts/`, `.factory/tests/` and `docs/factory/`. Phase 1 offers only config validation and bootstrap CI, not autonomous dispatch or merge.

Target factory flow: Issue → validated acceptance → fenced lease → role-assigned worker → PR + tests → selective CI → independent review → merge → `main` verification → audited Issue closure.

GitHub owns source, backlog, workflow evidence and immutable audit references. Treat all user- or agent-supplied Issue/PR content as untrusted. No account data, live order API, or privileged broker access belongs in hosted CI.
