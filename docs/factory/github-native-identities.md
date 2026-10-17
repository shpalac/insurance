# GitHub-native factory identity contract

The controller remains disabled by default (`orchestration.enabled: false` and an empty `approved_agent_logins` list). No PR or Issue content grants permissions.

## Roles and minimum permissions
- Validator: `issues:read`, `contents:read`. A trusted GitHub Actions workflow may use its job-scoped `GITHUB_TOKEN` for read-only validation.
- Developer: `contents:read/write`, `pull_requests:write` on isolated implementation branches only. Never authorize protected paths.
- Integrator: `contents:read`, `pull_requests:write`, `checks:read`. Trusted-main control plane only, with exact-head admission and effective ruleset verification; no bypass.

## Identity binding
`github-actions[bot]` is usable only when the workflow identity is bound to a trusted workflow and explicitly allowlisted. A dedicated GitHub App bot must be allowlisted by its authenticated login and given the minimum role-specific installation permissions. Do not treat a login, a PR author, an Issue role string, or a candidate workflow as proof of the credential's effective scopes.

For a dedicated GitHub App installation, store `FACTORY_APP_ID` as a repository Actions variable and `FACTORY_APP_PRIVATE_KEY` as a repository Actions secret. Limit the installation to `shpalac/insurance`, with Contents: read/write, Pull requests: read/write, Issues: read/write only for the designated transition job, Checks: read/write only for the trusted admission job, and Metadata: read. Use separate job-scoped tokens with only the permissions required by each role. Never grant Actions secrets to fork PR jobs.

Activation requires independently tested live credential identity, scoped token generation, and audit-backed readiness. Keep orchestration disabled until those proofs succeed.
