# Streamlit Application Package

Implements the clinician-facing UI that orchestrates uploads, pipeline execution, and review within Streamlit.

## Modules
- **`file_management.py`** – Handles upload persistence, DOI folder naming, and cleanup to mirror `PipelineFileManager`.
- **`json_viewer.py`** – Renders schema-compliant JSON with formatting and download options.
- **`result_checker.py`** – Provides helpers to assess validation outcomes and surface human review queues.
- **`session_state.py`** – Centralises Streamlit session state keys for navigation and data sharing between screens.
- **`screens/`** – Individual screen components (upload, pipeline progress, validation review, summary) that compose the UI flow.
- **`__init__.py`** – Binds screens together and exposes high-level rendering hooks for `app.py`.

## Implementation Tips
- Maintain parity with CLI behaviour by routing execution through `src.pipeline.orchestrator.run_single_step`.
- Keep network/API calls asynchronous-friendly or clearly note blocking operations to avoid UI freezes.
- When introducing new screens, register them in `screens/__init__.py` and add navigation state transitions in `session_state.py`.
- Use fixtures in `tests/integration/` to simulate UI-driven pipeline runs where possible.
