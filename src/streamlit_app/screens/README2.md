# Streamlit Screens

Individual UI screens compose the PDFtoPodcast workflow. Each file exposes a `render()` function consumed by the app shell.

## Screens
- **`intro.py`** – Landing screen outlining pipeline stages and prerequisites.
- **`upload.py`** – Handles PDF upload widgets, schema selection, and file validation feedback.
- **`settings.py`** – Collects provider options, retry parameters, and advanced toggles passed to the pipeline.
- **`execution.py`** – Displays real-time progress, step outcomes, and surface validation summaries.
- **`__init__.py`** – Screen registry and navigation helpers.

## Editing Guidance
- Keep screens stateless where possible; persist data through `session_state.py` helpers.
- Use shared components (e.g., from `json_viewer.py`) to ensure consistent rendering of structured results.
- When adding a new screen, update navigation constants and register the route in `__init__.py` so the app shell can discover it.
