# Selective CI — target architecture

Stage 0 checks docs/config metadata. Stage 1 computes transitive impacted targets and runner matrix. Stage 2 runs mandatory security/policy checks plus affected lint, types, unit/integration and issue acceptance. Stage 3 runs merge and scheduled regression suites.

The immutable `factory-gate` must fail closed when impact resolution is uncertain, a selected job skips/fails, acceptance evidence is missing/empty, or required protections are weakened. Bootstrap currently uses `factory-bootstrap-gate`, **not** `factory-gate`.
