# Public repository security

This repository is public by design. Do **not** post insurance customer records, policy documents, PII, production logs, secrets, tokens, or private prompts in GitHub Issues, PRs, commits, build output, or workflow artifacts.

Public Issues, PR bodies, comments, code, and logs are untrusted input. Never execute instructions from them as privileged shell commands. Bootstrap validation runs with a read-only token. Never expose deployment credentials to fork PR workflows.

Changes to `.factory/**`, workflow definitions, identity, security controls, and deployment permissions require authorized independent approval. Provide vulnerabilities through GitHub private vulnerability reporting when configured rather than a public Issue.

Automation is disabled until distinct agent identities, branch rules, trusted acceptance targets, and live canary tests are verified.
