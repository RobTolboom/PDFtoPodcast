# Architecture Overview

PDFtoPodcast extracts structured medical research data by streaming PDF content through a five-stage pipeline with iterative validation/correction loops. This document describes the runtime architecture, major components, data flow, and extensibility points. For implementation-level detail, see `src/README.md`, `schemas/readme.md`, `VALIDATION_STRATEGY.md`, `features/appraisal.md`, and `features/report-generation.md`.

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
run_appraisal_with_correction()
    • study-type routing (RoB 2, ROBINS-I, PROBAST, AMSTAR 2, etc.)
    • appraisal execution (risk of bias + GRADE ratings)
    • appraisal validation (logical consistency, completeness, evidence support)
    • correction iterations (<= max)
    • best iteration saved (appraisal-best.json, appraisal-validation-best.json)
        |
        v
run_report_with_correction()
    • report generation (combine classification + extraction + appraisal)
    • block-based JSON structure (text, table, figure, callout blocks)
    • report validation (accuracy, completeness, consistency)
    • correction iterations (<= max)
    • best iteration saved (report-best.json, report_validation-best.json)
    • rendering: JSON → LaTeX/WeasyPrint → PDF
    • figure generation (RoB traffic light, forest plots, CONSORT/PRISMA flows)
    • outputs: report.pdf, report.tex, report.md
        |
        v
Outputs persisted to tmp/ and returned to caller
```

## Component architecture

### Orchestrator (`src/pipeline/orchestrator.py`)
- Public APIs: `run_four_step_pipeline`, `run_single_step`, `run_validation_with_correction`, `run_appraisal_with_correction`.
- Extraction iterative loop tracks quality metrics (completeness, accuracy, schema compliance) and selects the highest-scoring iteration.
- Appraisal iterative loop tracks appraisal-specific metrics (logical consistency, completeness, evidence support, schema compliance) and selects the highest-scoring iteration.
- Uses `PipelineFileManager` to write iteration files (`extraction{N}.json`, `appraisal{N}.json`) and best-result artefacts (`extraction-best.json`, `appraisal-best.json`, metadata files).
- Breakpoints and progress callbacks support both CLI batching and Streamlit step-by-step execution.

### Validation runner (`src/pipeline/validation_runner.py`)
- Runs schema validation via `validation.validate_extraction_quality`.
- Invokes LLM validation when the schema quality score meets `SCHEMA_QUALITY_THRESHOLD` (default 0.5).
- Merges schema results and LLM feedback into a single report (`validation_bundled.json` schema).
- See `VALIDATION_STRATEGY.md` for quality metrics, thresholds, and exit codes.

### Critical Appraisal (`src/pipeline/orchestrator.py` - appraisal functions)
- **Study-type routing**: Maps publication types to appropriate appraisal tools via `_get_appraisal_prompt_name()`:
  - `interventional_trial` → RoB 2 (Cochrane Risk of Bias tool for randomized trials)
  - `observational_analytic` → ROBINS-I (Risk Of Bias In Non-randomized Studies)
  - `evidence_synthesis` → AMSTAR 2 + ROBIS (systematic review/meta-analysis quality)
  - `prediction_prognosis` → PROBAST (Prediction model Risk Of Bias ASsessment Tool)
  - `diagnostic` → PROBAST (shared prompt with prediction_prognosis)
  - `editorials_opinion` → Argument quality assessment
- **Iterative correction**: `run_appraisal_with_correction()` executes appraisal → validation → correction loop until quality thresholds met or max iterations reached.
- **Quality metrics**: Appraisal validation checks logical consistency (35%), completeness (25%), evidence support (25%), and schema compliance (15%).
- **GRADE integration**: Per-outcome certainty ratings (High/Moderate/Low/Very Low) with downgrading factors (risk of bias, inconsistency, imprecision, indirectness, publication bias).
- **Best selection**: `_select_best_appraisal_iteration()` ranks iterations by weighted quality score, filtering out critical issues.
- **File outputs**: Saves `{id}-appraisal{N}.json`, `{id}-appraisal-validation{N}.json`, and best files (`{id}-appraisal-best.json`).
- See `features/appraisal.md` for complete specification, tool descriptions, and acceptance criteria.

### Report Generation (`src/pipeline/orchestrator.py` - report functions, `src/rendering/`)
- **Report orchestration**: `run_report_with_correction()` executes report generation → validation → correction loop until quality thresholds met or max iterations reached.
- **Block-based architecture**: Reports use typed blocks (`text`, `table`, `figure`, `callout`) for flexible rendering.
- **Publication-type sections**: Type-specific sections added based on publication type (CONSORT for RCTs, PRISMA for systematic reviews, PROBAST for prediction models).
- **Quality metrics**: Report validation checks accuracy (35%), completeness (30%), cross-reference consistency (10%), data consistency (10%), and schema compliance (15%).
- **Rendering pipeline**: `src/rendering/latex_renderer.py` converts report JSON → LaTeX → PDF (or WeasyPrint HTML → PDF).
- **Figure generation**: `src/rendering/figure_generator.py` creates RoB traffic lights, forest plots, CONSORT/PRISMA flow diagrams using matplotlib.
- **LaTeX templates**: `templates/latex/vetrix/` contains professional LaTeX templates with booktabs tables, tcolorbox callouts, and siunitx number formatting.
- **Fallback outputs**: Markdown always generated regardless of PDF compilation success.
- **File outputs**: Saves `{id}-report{N}.json`, `{id}-report_validation{N}.json`, best files, and rendered outputs (`render/report.pdf`, `render/report.tex`, `render/report.md`).
- See `features/report-generation.md` for complete specification and `docs/report.md` for usage guide.

### LLM providers (`src/llm/`)
- `BaseLLMProvider` defines `generate_json_with_pdf`, `generate_json_with_schema`, and `generate_text`.
- `OpenAIProvider` and `ClaudeProvider` implement the interface with provider-specific retries, PDF upload limits, and error handling.
- Configuration (API keys, model names, timeouts, 10 MB default upload cap) is drawn from `src/config.py` (`llm_settings`).

### Prompts (`prompts/`)
- Classification, type-specific extraction prompts, validation, correction, and appraisal prompts are stored as plain text.
- **Extraction**: `Classification.txt`, `Extraction-prompt-*.txt`, `Extraction-validation.txt`, `Extraction-correction.txt`
- **Appraisal**: `Appraisal-interventional.txt`, `Appraisal-observational.txt`, `Appraisal-evidence-synthesis.txt`, `Appraisal-prediction.txt`, `Appraisal-editorials.txt`, `Appraisal-validation.txt`, `Appraisal-correction.txt`
- **Report**: `Report-generation.txt`, `Report-validation.txt`, `Report-correction.txt`
- `src/prompts.py` loads the appropriate prompt and raises `PromptLoadError` when a file is missing.
- Prompt revisions must stay in sync with schemas; see `prompts/README.md` for maintenance guidance.

### Schemas (`schemas/`)
- Modular sources (`*.schema.json`) share components via `common.schema.json`.
- **Extraction schemas**: Type-specific extraction schemas for interventional, observational, evidence synthesis, etc.
- **Appraisal schemas**: `appraisal.schema.json` (risk of bias + GRADE structure), `appraisal_validation.schema.json` (validation result structure)
- **Report schemas**: `report.schema.json` (block-based report structure), `report_validation.schema.json` (report validation metrics)
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
  - `paper-extraction0.json`, `paper-validation0.json` (initial extraction)
  - `paper-extraction1.json`, `paper-validation1.json` (correction iterations)
  - `paper-extraction-best.json`, `paper-validation-best.json`, `paper-extraction-best-metadata.json` (best extraction)
  - `paper-appraisal0.json`, `paper-appraisal-validation0.json` (initial appraisal)
  - `paper-appraisal1.json`, `paper-appraisal-validation1.json` (appraisal correction iterations)
  - `paper-appraisal-best.json`, `paper-appraisal-validation-best.json` (best appraisal)
  - `paper-report0.json`, `paper-report_validation0.json` (initial report)
  - `paper-report1.json`, `paper-report_validation1.json` (report correction iterations)
  - `paper-report-best.json`, `paper-report_validation-best.json` (best report)
  - `render/report.pdf`, `render/report.tex`, `render/report.md` (rendered outputs)
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
- `docs/appraisal.md` – appraisal usage guide.
- `docs/report.md` – report generation usage guide.
- `features/appraisal.md` – appraisal feature specification.
- `features/report-generation.md` – report generation feature specification.
