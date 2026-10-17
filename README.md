# Insurance — Public Autonomous Software Factory

This is a **public**, provider-agnostic software-factory repository intended for independently assigned LLM agents.

**Current state: bootstrap only.** Role contracts, schemas, policy validation, and a read-only CI gate are being introduced. The repository does **not** yet automatically dispatch workers, run issue acceptance, review, merge, or close issues.

## Agent entry point

Read [AGENTS.md](AGENTS.md), [.factory/config.yaml](.factory/config.yaml), and [agent assignment](docs/factory/agent-assignment.md) before proposing a change. No chat memory is required.

## Local verification

```sh
python3 -m pip install -r .factory/requirements-dev.txt
python3 .factory/scripts/validate_config.py
python3 -m unittest discover -s .factory/tests -v
```

## Roadmap

1. **Foundation (this PR):** configuration, policies, documentation, bootstrap tests.
2. Executable issue manifests and static issue validation.
3. Dependency-aware selective CI and required factory gate.
4. Isolated issue acceptance execution and traceability.
5. Audited PR integration and verified issue closure.
6. External agent dispatcher, fenced leases, bounded autonomous repair.
7. Live canary and fault injection before autonomous merge activation.

See [rollout](docs/factory/rollout.md) and [security policy](SECURITY.md).
