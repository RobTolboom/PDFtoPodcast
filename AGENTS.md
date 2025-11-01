# Repository Guidelines

## Project Structure & Module Organization
- Pipeline source lives in `src/`, with orchestration under `src/pipeline/`, provider adapters in `src/llm/`, and the Streamlit interface in `src/streamlit_app/`.
- CLI entry points are `run_pipeline.py` (pipeline) and `app.py` (web UI). Prompt templates sit in `prompts/`, JSON Schemas in `schemas/`, and run artefacts in `tmp/`.
- Tests mirror production code: quick checks in `tests/unit/`, scenario validation in `tests/integration/`, and reusable fixtures in `tests/fixtures/`.

## Build, Test, and Development Commands
- `make install` / `make install-dev` — install runtime or dev dependencies (pytest, linting, tooling).
- `make format`, `make lint`, `make typecheck`, `make check` — apply Black, run Ruff, execute mypy, or perform all checks sequentially.
- `make test`, `make test-fast`, `make test-coverage` — execute the full pytest suite, the fast unit subset, or pytest with coverage plus HTML output (`htmlcov/index.html`).
- Runtime: `python run_pipeline.py data/paper.pdf` for CLI automation; `streamlit run app.py` to launch the UI.

## Coding Style & Naming Conventions
- Target Python 3.10+; auto-format with Black (line length 100) and lint with Ruff (configured in `pyproject.toml`). Stick to snake_case for functions/modules and PascalCase for classes.
- Keep comments purposeful; prefer docstrings for public APIs. Configuration belongs in `.env` or `src/config.py`, never hard-coded.

## Testing Guidelines
- Pytest is the standard. Name modules `test_*.py`; mark long-running cases with `@pytest.mark.slow` or `@pytest.mark.integration`.
- Add fixtures in `tests/fixtures/` to share expensive resources; avoid real LLM calls except in tests marked `llm`.
- Run `make test-fast` before committing; use `make test-coverage` when touching critical pipeline paths.

## Commit & Pull Request Guidelines
- Follow the conventional format `type: short description` (e.g., `feat: add validation summary`). Keep commits scoped and run `make check` plus `make test-fast` prior to committing.
- Pull requests should outline scope, testing performed, and link related issues. Include screenshots/log excerpts when altering Streamlit or pipeline output.
- Update CHANGELOG entries under “Unreleased” and refresh documentation when behaviour or APIs change.

## Agent Automation Rules (CLAUDE.md)
- Automation agents must honour the meta rules in `CLAUDE.md`: obtain y/n approval before filesystem, git, build, or CI actions; share planned commands first; never change agreed plans without user consent; and always display repository policies verbatim when required.
- Follow the documented workflows (`make format → make lint → make test-fast` after code changes, `make ci` before pushes) and ensure feature work is tracked via markdown plans in `features/`.
- Every change must also consider the mandated doc/test updates described in the `change_management` section of `CLAUDE.md`.
