# Unit Tests

Focused tests for individual modules live here. They cover orchestration helpers, schema tooling, prompt loading, UI components, and validation logic.

## Representative Files
- **`test_orchestrator.py`** – Exercises step transitions, callback behaviour, and error handling in `src.pipeline.orchestrator`.
- **`test_file_manager.py` / `test_file_management_iterations.py`** – Validate DOI folder management and iteration bookkeeping.
- **`test_llm_base.py`** – Ensures provider abstractions raise consistent errors and honour configuration defaults.
- **`test_prompts.py`** – Confirms prompt selection matches schema identifiers.
- **`test_schemas_loader.py`** – Checks schema loading, bundling, and compatibility validation.
- **`test_json_bundler.py`** – Covers `json-bundler.py` edge cases.
- **`test_validation.py` & `test_iterative_validation_correction.py`** – Verify semantic+schema validation loops.
- **`test_execution_screen.py`** – Validates Streamlit progress rendering and data binding.

## Best Practices
- Mock external services (LLM APIs, filesystem) to keep tests deterministic.
- Use fixtures from `tests/fixtures/` and `conftest.py` to avoid duplication.
- Prefer explicit assertions about schema keys, statuses, and exceptions to document expected behaviour.
