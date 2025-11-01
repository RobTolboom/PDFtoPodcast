# Architecture Overview

PDFtoPodcast extracts structured medical research data by streaming PDF content through a three-stage pipeline with an iterative validation/correction loop. This document describes the runtime architecture, major components, data flow, and extensibility points. For implementation-level detail, see `src/README.md`, `schemas/readme.md`, and `VALIDATION_STRATEGY.md`.

## System summary

- **Vision-first extraction**: PDFs are sent directly to LLM vision endpoints so tables, figures, and layout cues remain intact.
- **Schema-driven outputs**: Each extraction prompt maps to a JSON Schema file; every response must validate locally before being accepted.
- **Dual validation**: Schema checks run locally, while semantic validation is delegated to an LLM when structural quality is sufficient.
- **Iterative correction**: Validation feedback can trigger a bounded correction loop until quality thresholds are met or early-stop conditions fire.
- **Provider abstraction**: OpenAI and Anthropic clients implement a shared interface so new providers can be added without touching the pipeline logic.

## High-level flow

```
PDF input (<=100 pages, <= provider limit)
        |
        v
Classification prompt -> metadata + publication_type
        |
        v
Select extraction prompt + schema
        |
        v
Extraction prompt -> extraction0.json
        |
        v
run_validation_with_correction()
    • schema validation (always)
    • LLM validation (quality >= 0.5)
    • correction iterations (<= max)
    • best iteration saved (extraction-best.json, validation-best.json)
        |
        v
Outputs persisted to tmp/ and returned to caller
```

## Component architecture

### Orchestrator (`src/pipeline/orchestrator.py`)
- Public APIs: `run_four_step_pipeline`, `run_single_step`, `run_validation_with_correction`.
- Iterative loop tracks quality metrics (completeness, accuracy, schema compliance) and selects the highest-scoring iteration.
- Uses `PipelineFileManager` to write `extraction0.json`, `validation0.json`, iteration files (`extraction1.json`, …) and best-result artefacts (`extraction-best.json`, `extraction-best-metadata.json`).
- Breakpoints and progress callbacks support both CLI batching and Streamlit step-by-step execution.

### Validation runner (`src/pipeline/validation_runner.py`)
- Runs schema validation via `validation.validate_extraction_quality`.
- Invokes LLM validation when the schema quality score meets `SCHEMA_QUALITY_THRESHOLD` (default 0.5).
- Merges schema results and LLM feedback into a single report (`validation_bundled.json` schema).
- See `VALIDATION_STRATEGY.md` for quality metrics, thresholds, and exit codes.

### LLM providers (`src/llm/`)
- `BaseLLMProvider` defines `generate_json_with_pdf`, `generate_json_with_schema`, and `generate_text`.
- `OpenAIProvider` and `ClaudeProvider` implement the interface with provider-specific retries, PDF upload limits, and error handling.
- Configuration (API keys, model names, timeouts, 10 MB default upload cap) is drawn from `src/config.py` (`llm_settings`).

### Prompts (`prompts/`)
- Classification, type-specific extraction prompts, validation, and correction prompts are stored as plain text (
  `Classification.txt`, `Extraction-prompt-*.txt`, `Extraction-validation.txt`, `Extraction-correction.txt`).
- `src/prompts.py` loads the appropriate prompt and raises `PromptLoadError` when a file is missing.
- Prompt revisions must stay in sync with schemas; see `prompts/README.md` for maintenance guidance.

### Schemas (`schemas/`)
- Modular sources (`*.schema.json`) share components via `common.schema.json`.
- Bundled files (`*_bundled.json`) inline references for LLM compatibility and runtime validation.
- `src/schemas_loader.py` caches schemas and validates compatibility.
- `json-bundler.py` regenerates bundled files after edits; run schema unit tests afterwards.

### Validation utilities (`src/validation.py`)
- Provides local quality scoring and completeness metrics.
- Outputs a dictionary with schema compliance, completeness, field coverage, and error details consumed by the validation runner.

### File management (`src/pipeline/file_manager.py`)
- Derives an identifier from the PDF filename and generates output paths within `tmp/`.
- Naming patterns:
  - `paper-classification.json`
  - `paper-extraction0.json`, `paper-validation0.json`
  - `paper-extraction1.json`, `paper-validation1.json` (iterations)
  - `paper-extraction-best.json`, `paper-validation-best.json`, `paper-extraction-best-metadata.json`
  - `paper-extraction-failed.json` (error diagnostics)

### Streamlit app (`src/streamlit_app/`)
- Mirrors CLI functionality with interactive upload, step selection, execution progress, and JSON previews.
- Uses session state to track configured steps, per-step status, and iteration history returned by the orchestrator.

## Execution modes

| Mode      | Entry point            | Behaviour                                                    |
|-----------|------------------------|--------------------------------------------------------------|
| CLI       | `python run_pipeline.py paper.pdf` | Runs all configured steps sequentially, writing outputs to `tmp/`. |
| Streamlit | `streamlit run app.py`             | Executes one step per rerun, updating session state between steps. |

Both modes call `run_single_step` internally, ensuring consistent behaviour and simplifying testing.

## Configuration

- Defaults come from `src/config.py` (`llm_settings` dataclass).
- `.env` supplies API keys, model names, upload size overrides, and timeout settings.
- Raising `MAX_PDF_SIZE_MB` above 10 requires that the chosen provider account permits larger uploads (hard limit 32 MB).

## Error handling and resilience

- Unified `LLMError` hierarchy encapsulates provider-specific failures.
- Tenacity-backed retries with exponential backoff (1s, 2s, 4s) handle transient network issues.
- Validation loop early-stops when quality degrades across iterations, schema quality drops below 0.5, or repeated LLM errors occur.
- Best available iteration is always returned, even on failure paths, to keep downstream consumers from receiving empty results.

## Extensibility

- **New provider**: implement `BaseLLMProvider`, register in `src/llm/__init__.py`, update configuration docs.
- **New publication type**: create prompt + schema pair, wire type mapping in `src/prompts.py` and `src/schemas_loader.py`, add tests/fixtures.
- **Custom validation**: extend `validation.py` scoring or adjust thresholds in `run_validation_with_correction`.
- **Alternative UI/API**: reuse `run_single_step` for other front ends (REST services, background workers).

## Security and data handling

- PDFs remain on disk (`tmp/`) and are uploaded only to configured LLM endpoints.
- Users should remove or redact sensitive patient information before processing.
- `.env` should never be committed; see `SECURITY.md` for credential handling guidance.

## Testing strategy

- Unit tests validate prompt loading, schema integrity, validation scoring, and pipeline utilities.
- Integration tests exercise `run_four_step_pipeline` with mocked providers.
- Use `make test-fast` for quick feedback and `make test-coverage` to generate HTML coverage reports.

## Related documentation

- `README.md` – getting started, prerequisites, usage.
- `VALIDATION_STRATEGY.md` – dual validation and correction loop details.
- `prompts/README.md` – prompt maintenance.
- `schemas/readme.md` – schema maintenance and bundling.
- `SECURITY.md` – security posture and PDF handling guidance.
