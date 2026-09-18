# Contributing to Chaser

Thanks for taking the time to contribute.

## Reporting bugs

Open a [bug report](https://github.com/emanuelsdsj/chaser/issues/new?template=bug_report.yml). Include:

- What you expected to happen vs. what actually happened
- A minimal snippet that reproduces the issue
- Chaser version (`chaser --version` or `python -c "import chaser; print(chaser.__version__)"`), Python version, and OS

## Suggesting features

Open a [feature request](https://github.com/emanuelsdsj/chaser/issues/new?template=feature_request.yml) describing the problem you're trying to solve, not just the API you have in mind — the "why" makes it much easier to evaluate.

## Development setup

```bash
git clone https://github.com/emanuelsdsj/chaser.git
cd chaser
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Before opening a pull request

The CI pipeline runs these checks on every push; run them locally first:

```bash
ruff check chaser tests
ruff format --check chaser tests
mypy chaser
pytest
```

A few conventions worth knowing:

- Commit messages follow `type(scope): summary` (`feat`, `fix`, `docs`, `test`, `refactor`, `release`), matching the existing log — see `git log` for examples. Explain *why* in the body, not just what changed.
- Public API changes should be reflected in `chaser/__init__.py`'s `__all__` (see `docs/stability.md` for the stability policy) and noted in `CHANGELOG.md` under `[Unreleased]`.
- Keep pull requests focused — one logical change per PR is easier to review and revert if needed.

## Review process

Chaser currently has a single maintainer. Pull requests are reviewed and merged directly once CI is green and the change fits the project's scope — there's no separate approval step yet. If a PR sits without a response for a while, a friendly ping on the PR is fine.

## License

By contributing, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
