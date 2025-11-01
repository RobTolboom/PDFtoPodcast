# Pipeline Package

Coordinates PDF ingestion, staged execution, and validation for the four-step pipeline (classification → extraction → validation/correction).

## Modules
- **`orchestrator.py`** – Entry points `run_single_step` and `run_four_step_pipeline`, progress callbacks, and iterative correction thresholds (`DEFAULT_QUALITY_THRESHOLDS`).
- **`file_manager.py`** – Manages DOI-based working directories, persisted intermediates, and cleanup helpers.
- **`validation_runner.py`** – Wraps schema validation plus semantic review prompts via `run_dual_validation`.
- **`utils.py`** – Shared utilities (e.g., `check_breakpoint`, metadata stripping) used during staged execution.
- **`__init__.py`** – Exposes public APIs for CLI/UI consumers.

## Extension Guidelines
- Add new steps by updating `ALL_PIPELINE_STEPS`, providing orchestration logic, and wiring prompts/schemas.
- Maintain backward compatibility with the CLI by supporting both `validation` and `correction` steps when extending combined flows.
- Keep file writes confined to `PipelineFileManager` to ensure the Streamlit UI and CLI share a consistent storage layout.
- Cover new behaviour with integration tests in `tests/integration/` to verify multi-step execution and schema outputs.
