# Contributing to Helix-Adapter

First off — thank you. This project exists because people who care about structural AI governance found each other.

## Scope

We welcome contributions that improve the adapter's ability to enforce epistemic discipline, measure drift, and produce tamper-evident receipts. This includes:

- **Bug reports** — especially boundary conditions in marker extraction, drift calculation, or receipt generation
- **Red-team findings** — if you find a way to bypass constitutional invariants, we want to know
- **Documentation** — clarity, correctness, examples
- **Tests** — regression tests for edge cases discovered in the wild
- **Tooling** — linting, CI, build improvements

## What We Don't Merge

- Changes that weaken constitutional invariants
- Features that depend on model self-reporting (the model is never trusted to self-report compliance or drift)
- Anything that removes or relaxes the out-of-band enforcement layer

## How to Contribute

1. Fork the repo
2. Create a branch (`git checkout -b fix/something`)
3. Make your changes
4. Run the tests: `pytest tests/`
5. Run the linter: `ruff check src/ tests/ widget/`
6. Open a PR against `main`

Keep PRs focused. One fix, one feature, one improvement per PR.

## Code Style

- Line length: 100 characters
- Formatter: Black (configured in `pyproject.toml`)
- Linter: Ruff (E, F, I, W rules)
- Docstrings: Not required, but explain why if the code isn't obvious

## Reporting Security Issues

See [SECURITY.md](SECURITY.md). Do not open a public issue for security vulnerabilities.

## Community

- **Live Demo:** [helixaiinnovations.ca/chat/](https://helixaiinnovations.ca/chat/) — DM for access
- **Author:** Stephen Hope on [LinkedIn](https://www.linkedin.com/in/stephen-hope-75497937a)
- **Discussions:** Use GitHub Issues for technical discussion. For broader architectural conversation, reach out directly.

## License

Apache 2.0. By contributing, you agree that your contributions will be licensed under the same terms.
