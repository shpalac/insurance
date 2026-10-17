# Executable acceptance contract — target specification

Phase 2 will implement `.factory/schemas/acceptance.schema.json` and an issue-body validator for `yaml factory-acceptance-manifest` blocks. Each `AC-N` must specify a deterministic hosted runner target, concrete assertion, report artifact, timeout, and scope.

**Untrusted Issue text must never become shell commands.** The eventual acceptance worker will execute a trusted registry of test targets on an unprivileged runner, verify actual test cases in JUnit/JSON evidence, and publish traceability. Manual or physical-only requirements must be converted to deterministic mocks/harnesses or rejected.
