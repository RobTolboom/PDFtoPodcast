# Contributing Guide

Welcome—this document outlines how to set up a development environment, follow the project workflow, and contribute code, documentation, or tests to PDFtoPodcast.

## Table of contents
- [Code of conduct](#code-of-conduct)
- [Environment setup](#environment-setup)
- [Workflow overview](#workflow-overview)
- [Coding standards](#coding-standards)
- [Testing](#testing)
- [Feature and provider checklists](#feature-and-provider-checklists)
- [Submitting changes](#submitting-changes)
- [Documentation expectations](#documentation-expectations)
- [FAQ](#faq)
- [Licensing](#licensing)

## Code of conduct
- Prioritise accuracy and traceability of medical data.
- Communicate respectfully; critiques should stay constructive and specific.
- Back changes with data, tests, or clear user requirements.
- Document behaviour changes and keep tests up to date.
- Treat API keys and patient data responsibly (see `SECURITY.md`).

## Environment setup
1. **Clone the repository**
   ```bash
   git clone https://github.com/RobTolboom/PDFtoPodcast.git
   cd PDFtoPodcast
   ```
2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
3. **Install dependencies**
   ```bash
   make install          # production deps
   make install-dev      # adds dev tooling (pytest, black, ruff, mypy)
   ```
   *(If make is unavailable, fall back to `pip install -r requirements.txt` and `pip install -r requirements-dev.txt`.)*
4. **Configure environment variables**
   - Create `.env` manually (see `README.md` for the full list). At minimum set `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`.
   - Optional overrides: `MAX_PDF_SIZE_MB` (default 10), `LLM_TIMEOUT`, provider model names.
5. **Sanity check**
   ```bash
   python -c "from src.llm import get_llm_provider; print(get_llm_provider('openai'))"
   ```
6. **Install pre-commit hooks (optional but recommended)**
   ```bash
   pre-commit install
   ```

## Workflow overview
- Default branch is `main` (protected). Create short-lived topic branches: `feature/...`, `fix/...`, `docs/...`, `refactor/...`, `test/...`.
- For substantial work, add a planning note under `docs/plans/` describing scope, tasks, and risks (see `docs/plans/README.md`).
- Sync often: `git checkout main && git pull origin main` before branching or rebasing.
- Commit early and often using Conventional Commit messages (`feat: ...`, `fix: ...`, etc.).
- Run tests and quality checks locally before pushing (`make check`, `make test`).

## Coding standards
- Python 3.10+, formatted with **Black** (line length 100) and linted with **Ruff**.
- Type hints required for all function signatures; mypy is configured in `pyproject.toml`.
- Use Google-style docstrings for public APIs.
- Custom exceptions live in `src/llm` and `src/pipeline`—prefer raising domain-specific errors (`LLMError`, `PromptLoadError`, etc.) over generic ones.
- Rich console output should remain user-friendly; dim verbose logs where possible.

Common quality commands:
```bash
make format      # black
make lint        # ruff
make typecheck   # mypy
make check       # format + lint + typecheck
```

## Testing
### Layout
```
tests/
|-- unit/                          # 36 unit test files
|   |-- test_appraisal_*.py        # appraisal functions, quality
|   |-- test_backward_compatibility.py
|   |-- test_execution_*.py        # artifacts, results, screen
|   |-- test_figure_generator.py
|   |-- test_file_manage*.py       # file_manager, file_management_iterations
|   |-- test_iteration_tracker.py
|   |-- test_iterative_validation_correction.py
|   |-- test_json_bundler.py
|   |-- test_latex_renderer.py
|   |-- test_llm_base.py
|   |-- test_loop_runner.py
|   |-- test_markdown_renderer.py
|   |-- test_null_value_removal.py
|   |-- test_openai_provider_parsing.py
|   |-- test_orchestrator.py
|   |-- test_pipeline_*.py         # cli_flags, utils
|   |-- test_podcast_*.py          # generation, renderer
|   |-- test_prompt_template_validation.py
|   |-- test_prompts.py
|   |-- test_quality_module.py
|   |-- test_rendering_fixes.py
|   |-- test_report_*.py           # generation, prompts, quality, schema
|   |-- test_schema_*.py           # openai_compatibility, repair
|   |-- test_schemas_loader.py
|   |-- test_validation.py
|   `-- test_weasy_renderer.py
|-- integration/                   # 5 integration test files
|   |-- test_appraisal_full_loop.py
|   |-- test_report_full_loop.py
|   |-- test_report_render_tex.py
|   |-- test_schema_bundling.py
|   `-- test_validation_correction_metadata_stripping.py
|-- fixtures/
|   |-- sample_pdfs/
|   `-- expected_outputs/
`-- conftest.py
```

### Markers and commands
- Mark tests with `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`, `@pytest.mark.llm` as appropriate.
- Useful commands:
  ```bash
  make test          # full suite
  make test-fast     # unit + quick checks (excludes slow/integration)
  make test-coverage # pytest with coverage + HTML report
  pytest tests -k "validation and not slow"
  ```
- Mock LLM calls in unit tests (`unittest.mock.patch` or fixtures in `tests/conftest.py`) to avoid API spend.

## Feature and provider checklists
### Adding a publication type
- [ ] Prompt: add `prompts/Extraction-prompt-{type}.txt`.
- [ ] Schema: add `schemas/{type}.schema.json`, update bundled output via `python schemas/json-bundler.py`.
- [ ] Wire type mapping in `src/prompts.py` and `src/schemas_loader.py`.
- [ ] Extend `schemas/classification.schema.json` enum for the new publication type.
- [ ] Provide fixtures and tests (`tests/fixtures`, `tests/unit/test_prompts.py`, `tests/unit/test_schemas_loader.py`).
- [ ] Update docs: `README.md` supported types, `prompts/README.md`, `schemas/readme.md`, `CHANGELOG.md`.

### Adding an LLM provider
- [ ] Implement class inheriting from `BaseLLMProvider` with `generate_json_with_pdf` and related helpers.
- [ ] Register factory entry in `src/llm/__init__.py`.
- [ ] Extend `src/config.py` to read new environment variables.
- [ ] Document `.env` additions and defaults (`README.md`, `SECURITY.md` if relevant).
- [ ] Add unit tests (e.g., `tests/unit/test_llm_base.py`) and mocked integration coverage.
- [ ] Update `ARCHITECTURE.md`, `CHANGELOG.md`.

### Extending validation
- [ ] Modify `validate_extraction_quality` or the validation runner.
- [ ] Adjust `validation_bundled.json` if the output contract changes.
- [ ] Add or update tests (`tests/unit/test_validation.py`, `tests/unit/test_iterative_validation_correction.py`).
- [ ] Document the change in `VALIDATION_STRATEGY.md` and `CHANGELOG.md`.

## Submitting changes
1. Ensure local quality checks pass (`make check`, `make test` or `make test-fast`).
2. Update documentation as needed (`README.md`, `prompts/README.md`, `schemas/readme.md`, `ARCHITECTURE.md`, etc.).
3. Log user-visible changes under the “Unreleased” section of `CHANGELOG.md`.
4. Push your branch and open a pull request. Fill in the PR template, link issues, and summarise testing performed.
5. Address review feedback promptly. Reviewers expect tests, docs, and CHANGELOG entries before approving.
6. Squash or rebase to keep history clean when merging.

Commit message guidelines use Conventional Commits:
```
feat(pipeline): add progress callbacks
fix(llm): handle JSON parsing errors
docs(prompts): update validation prompt guidance
```

## Documentation expectations
- **Code**: public functions require docstrings and type hints; complex flows warrant inline comments.
- **User-facing**: keep `README.md`, `prompts/README.md`, `schemas/readme.md`, `ARCHITECTURE.md`, and `VALIDATION_STRATEGY.md` in sync with behaviour.
- **Process**: log notable changes in `CHANGELOG.md`, update `ROADMAP.md` if roadmap items shift, and maintain feature plans in `docs/plans/`.

## FAQ
**How do I test without incurring API cost?**
- Use unit tests with mocks, break the pipeline after early steps (`run_pipeline.py paper.pdf --step classification`), or limit pages (`--max-pages 5`).

**Where do outputs go?**
- All artefacts are written to `tmp/` (see `PipelineFileManager`). Use `--keep-tmp` to retain intermediate files when debugging.

**How do I add a field to an existing schema?**
- Update the modular schema, run `python schemas/json-bundler.py`, adjust prompts/tests, bump schema metadata, and document the change.

**How do I investigate validation failures?**
- Inspect `tmp/paper-validation*.json`, review the `issues` array, and compare against the PDF source. Enabling verbose logging in Streamlit can surface token usage and raw responses.

## Licensing
Contributions are accepted under the Prosperity Public License 3.0.0 for non-commercial use; commercial licensing terms remain unchanged. By submitting a pull request you confirm you have the right to license your work under these terms.
