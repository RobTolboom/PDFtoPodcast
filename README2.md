# PDFtoPodcast Repository Guide

PDFtoPodcast ingests clinical research PDFs and turns them into validated, schema-compliant JSON packages that can be consumed by downstream analytics and text-to-speech tooling. The repo pairs an automated four-step extraction pipeline with a Streamlit facilitator UI, prompt packs, schema catalogues, and a comprehensive validation strategy.

## Architecture Overview
| Layer | Location | Responsibility |
| --- | --- | --- |
| Orchestration | `src/pipeline/` | Manages the staged pipeline (classification → extraction → validation/correction), file lifecycle, and callback notifications. |
| LLM Providers | `src/llm/` | Provider-agnostic interface with adapters for OpenAI and Anthropic/Claude, retry policies, and PDF upload helpers. |
| Prompt Library | `prompts/`, `src/prompts.py` | Loads YAML prompt templates keyed by study type; surfaces helpers consumed by the pipeline orchestrator. |
| Schema Toolkit | `schemas/`, `src/schemas_loader.py`, `json-bundler.py` | Houses canonical JSON Schema definitions, bundle artefacts, and loader utilities used at runtime and in CI. |
| Validation | `src/validation.py`, `tests/` | Implements semantic + schema validation, fixtures, and regression tests that guard the data contract. |
| Streamlit UI | `app.py`, `src/streamlit_app/` | Provides the multi-screen clinician workflow, session state, and visual progress tracking. |
| Operations | `.github/`, `Makefile`, `features/` | Automations, contributor workflows, and roadmap briefs that guide ongoing development. |

## How the Pipeline Runs
1. **Classification** – `src/pipeline/orchestrator.py` calls `load_classification_prompt()` and dispatches the PDF to the chosen LLM provider.
2. **Extraction** – Raw results are normalised via `src/pipeline/utils.py` helpers before writing to `PipelineFileManager` staging.
3. **Validation + Correction** – `run_dual_validation()` from `src/pipeline/validation_runner.py` combines JSON Schema checks with semantic review prompts. Failures trigger iterative correction until thresholds in `DEFAULT_QUALITY_THRESHOLDS` are satisfied.
4. **Hand-off** – Final payloads and execution metadata are stored under `tmp/<doi>/` for human inspection and downstream systems.

## Local Development
1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # linters, pytest, type checkers
   ```
2. **Configure secrets** – Populate `.env` (or environment variables) for each LLM provider referenced in `src/config.py` (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
3. **Choose a workflow**
   - **Run the Streamlit UI**
     ```bash
     streamlit run app.py
     ```
   - **Execute the CLI pipeline**
     ```bash
     python run_pipeline.py path/to/paper.pdf --llm-provider anthropic
     python run_pipeline.py path/to/paper.pdf --step validation_correction --max-iterations 2
     ```
   - **Schema maintenance**
     ```bash
     make bundle-schemas
     make validate-schemas
     ```

## Contribution Checklist
- Format, lint, and type-check with `make format lint typecheck` before pushing.
- Run targeted `pytest` commands (unit, integration, or schema bundles) from the `tests/` directory to cover affected modules.
- Document behaviour changes in `CHANGELOG.md` and update prompts/schemas together to avoid drift.
- Keep secrets out of commits; sensitive configuration belongs in environment variables or secure storage.

## Useful References
- **Product context:** `ROADMAP.md`, `DEVELOPMENT.md`, `VALIDATION_STRATEGY.md`
- **Security & licensing:** `SECURITY.md`, `LICENSE`, `COMMERCIAL_LICENSE.md`
- **Support artefacts:** `features/` (feature briefs), `.github/workflows/` (CI definitions), `tests/fixtures/` (sample payloads)
