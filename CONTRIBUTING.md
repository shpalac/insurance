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
