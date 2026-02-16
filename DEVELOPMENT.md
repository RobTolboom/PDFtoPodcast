# Development Guide

This guide covers environment setup, common workflows, testing, and debugging tips for the PDFtoPodcast codebase. Refer to `src/README.md`, `prompts/README.md`, `schemas/readme.md`, and `VALIDATION_STRATEGY.md` for module-level detail.

## Contents
- [Quick start](#quick-start)
- [Environment & tools](#environment--tools)
- [Project layout](#project-layout)
- [Everyday tasks](#everyday-tasks)
- [Testing](#testing)
- [Debugging & profiling](#debugging--profiling)
- [Troubleshooting](#troubleshooting)
- [Further reading](#further-reading)

## Quick start
```bash
# clone and enter repo
git clone https://github.com/RobTolboom/PDFtoPodcast.git
cd PDFtoPodcast

# create virtualenv
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# install dependencies (make preferred)
make install
make install-dev
# fallback: pip install -r requirements.txt && pip install -r requirements-dev.txt

# create .env manually (see README.md) and add API keys

# verify setup
python -c "from src.llm import get_llm_provider; print(get_llm_provider('openai'))"

# run a short pipeline test
python run_pipeline.py paper.pdf --max-pages 5 --keep-tmp
```

## Environment & tools
**Required:**
- Python 3.10+
- Git
- Make (optional but recommended for convenience)

**Optional:**
- pre-commit hooks (`pre-commit install`)
- `jq` for inspecting JSON (`brew install jq` / `apt install jq`)
- IDE integrations (VS Code, PyCharm) configured for Black + Ruff + pytest + mypy

## Project layout (summary)
```
src/                    core modules (see src/README.md)
prompts/                prompt templates + prompts/README.md
schemas/                JSON schemas + schemas/readme.md + bundler
tests/                  unit & integration tests + tests/README.md
docs/plans/             feature and implementation planning notes
run_pipeline.py         CLI entry point
app.py                  Streamlit entry point
Makefile                common tasks
.tmp/                   pipeline outputs (gitignored)
```
Other documentation lives at the repo root (README, ARCHITECTURE, CONTRIBUTING, DEVELOPMENT, SECURITY, etc.).

## Everyday tasks
### Running the pipeline
```bash
python run_pipeline.py paper.pdf                    # default provider (OpenAI)
python run_pipeline.py paper.pdf --llm-provider claude
python run_pipeline.py paper.pdf --max-pages 5       # limit pages to save tokens
python run_pipeline.py paper.pdf --keep-tmp          # keep outputs in tmp/
```
Use `--step classification` / `--step extraction` to run individual phases when debugging.

### Breakpoints (development mode)
Inside `run_pipeline.py` you can set `BREAKPOINT_AFTER_STEP` to `"classification"`, `"extraction"`, or `"validation"` to stop early and inspect intermediate files in `tmp/` before continuing.

### Quality and linting
```bash
make format      # black
make lint        # ruff
make typecheck   # mypy
make check       # format + lint + typecheck
```

### Inspecting outputs
```bash
ls tmp/
cat tmp/paper-classification.json | jq '.'
cat tmp/paper-extraction0.json | jq '.metadata'
cat tmp/paper-validation-best.json | jq '.issues'
```
File naming follows the `PipelineFileManager` scheme: `extraction0.json`, `validation0.json`, iteration files (`extraction1.json`), and best artefacts (`extraction-best.json`, `extraction-best-metadata.json`).

## Testing
See `tests/README.md` for the full breakdown. Common commands:
```bash
make test          # full suite
make test-fast     # fast unit tests (excludes slow/integration)
make test-coverage # coverage + htmlcov/
pytest tests -k "validation and not slow"
```
Markers: `unit`, `integration`, `slow`, `llm`. Mock LLM calls with `unittest.mock.patch` or fixtures in `tests/conftest.py` to avoid API spend.

Test fixtures live under `tests/fixtures/` (sample PDFs and expected outputs). Update them when prompts or schemas change.

## Debugging & profiling
- Use `--keep-tmp` to preserve intermediate JSON for inspection.
- Enable verbose logging in Streamlit under Settings, or add temporary `logging` statements in Python modules.
- For CLI, set `BREAKPOINT_AFTER_STEP` or drop `breakpoint()` in the code to invoke pdb.
- Token counting or timing utilities can be copied from the snippets in README/ARCHITECTURE when needed; remember to remove instrumentation before committing.

## Troubleshooting
| Issue | Actions |
|-------|---------|
| Missing API key | Ensure `.env` defines `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`; reactivate shell or export variables. |
| PDF exceeds size limit | Default upload cap is 10 MB (configurable via `MAX_PDF_SIZE_MB`, provider hard limit 32 MB). Split or compress the PDF if needed. |
| Schema validation errors | Inspect `tmp/*-validation*.json`, run `python schemas/json-bundler.py` to ensure bundled schemas are current, check schema-prompts alignment. |
| LLM timeouts | Increase `LLM_TIMEOUT` in `.env`, reduce `--max-pages`, or rerun later. |
| Module import errors | Confirm virtualenv activation (`source .venv/bin/activate`) and ensure `PYTHONPATH` includes the repo root if running ad-hoc scripts. |

## Further reading
- `README.md` - quick start, configuration, usage.
- `CONTRIBUTING.md` - contribution workflow and coding standards.
- `ARCHITECTURE.md` - system design and component relationships.
- `VALIDATION_STRATEGY.md` - validation loop and quality thresholds.
- `prompts/README.md` & `schemas/readme.md` - prompt/schema maintenance.
