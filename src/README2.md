# Source Code Overview

Application source lives under `src/`. The modules here orchestrate PDF ingestion, interact with LLM providers, validate outputs, and power the Streamlit UI.

## Module Map
| Path | Summary |
| --- | --- |
| `config.py` | Central configuration helpers that read environment variables (API keys, model options). |
| `llm/` | Provider abstraction layer with concrete adapters and error handling. |
| `pipeline/` | Core orchestration logic, file management, validation runner, and utility helpers. |
| `prompts.py` | Loader that maps schema metadata to prompt files in `prompts/`. |
| `schemas_loader.py` | JSON Schema loading, dereferencing, and compatibility checks against pipeline inputs. |
| `streamlit_app/` | Streamlit screens, session utilities, and orchestration bindings for the UI. |
| `validation.py` | Shared validation helpers used by the pipeline and tests.

## Development Notes
- Keep public APIs documented with docstrings; CLI and UI modules import directly from these packages.
- Cross-module contracts (e.g., schema keys, prompt identifiers) should be updated atomically to avoid runtime failures.
- When adding new providers or pipeline steps, extend unit tests in `tests/unit/` and integration flows in `tests/integration/`.
- Ensure imports remain relative within the package to support both CLI and Streamlit execution contexts.
