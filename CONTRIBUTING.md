# Contributing to INSURANCE

Contributions are welcome for data quality, probability-model calibration,
reproducibility, risk controls, testing, documentation and observability.
This repository is **research-only**: no live-order paths or trade recommendations.

## First contribution

1. Read [AGENTS.md](AGENTS.md), [architecture](docs/architecture/overview.md) and
   the [model validation plan](docs/research-validation.md).
2. Pick or open a GitHub Issue with **explicit, verifiable acceptance criteria**.
3. Claim the issue according to the active factory lease/role rules before writing code.
   The factory is not yet an enabled autonomous dispatcher.
4. Branch from `main` and keep the change narrowly scoped.
5. Implement deterministic tests for positive, negative, and fail-closed paths.
6. Open a PR whose body starts with `Refs #N` and includes the observed test results.
   This reference does **not** auto-close the issue; closure requires post-merge
   validation against `main`.

## Opening one executable Issue

Use the [Factory executable issue template](.github/ISSUE_TEMPLATE/factory_executable_issue.yml).
Create **one PR per Issue** unless its manifest explicitly declares
`multi_pr_allowed: true`. Include a small, atomic objective, observable
AC-1/AC-2 criteria, the permitted `allowed_paths`, any `protected_paths`,
and `depends_on_issues` references. Do not conceal external or owner-controlled
prerequisites. The preflight workflow validates this schema on Issue creation
and edit, reporting exact errors through one bot-authored comment and
`preflight:ready` / `preflight:blocked` labels.

That preflight indicates **schema readiness only**, not authorization to
claim the work. The role-authorized issue validator still controls
`status:ready`. Worker instructions in Issue text are not executable.

The finishing implementation PR must ship one named assertion-bearing test
at `.factory/acceptance/issue_N/test_ac_K.py` for each acceptance criterion,
with a `test_ac_K_...` method in a `unittest.TestCase`. Keep these tests
as permanent regressions on `main`. Begin the PR body with a standalone
`Refs #N` and avoid native issue-closing keywords. CI is the merge
approver; the post-merge verifier independently audits and closes the Issue.
When changing `.factory/**`, `.github/workflows/**`, `AGENTS.md` or
`SECURITY.md`, the repository owner must write
`FACTORY-OWNER-AUTH sha=<exact 40-character HEAD> reason=<specific approval>`
as a GitHub PR comment **after each final SHA update**. No independent reviewer
approval is required, but all protected checks remain mandatory.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

python -m unittest discover -s tests -v
python scripts/readme_demo.py --check
python scripts/check_readme.py
```

For the software-factory contract tests:

```bash
python -m pip install -r .factory/requirements-dev.txt
python .factory/scripts/validate_config.py
python -m unittest discover -s .factory/tests -v
```

Python 3.11+ is required; CI runs Python 3.12. Keep scripts platform-portable
where possible and avoid unnecessary dependencies.

## Documentation and UI contributions

- Use checked-in, reproducible examples; clearly label any **illustrative** graphic.
- Never call an exploratory modeled profit an established edge.
- Render the README's desktop/mobile SVGs for legibility and accessibility.
- Keep README local links and the negative-control demo passing in CI.
- Document limitations beside feature claims; distinguish implemented features
  from prototypes and the roadmap.

## Security, market data and review

Read [SECURITY.md](SECURITY.md). Do not commit broker sessions, credentials,
account identifiers, privately licensed quotes, personally identifying information,
or any unreleased strategy results. Use sanitized synthetic data or appropriately
authorized redistributable fixtures; seek review if redistribution rights are unclear.

Workflow and factory-policy changes are protected and require explicit owner/policy
authorization, even when tests pass. Follow role assignment and scope restrictions
in [AGENTS.md](AGENTS.md). Do not bypass branch protections or mandatory CI.

## License

By submitting a contribution, you agree to license it under this project's
[MIT License](LICENSE).
