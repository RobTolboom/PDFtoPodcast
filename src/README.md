# src package overview

`src/` contains the production code for the PDFtoPodcast pipeline. Modules are organised by responsibility: configuration and shared utilities at the top level, provider abstractions under `llm/`, orchestration logic in `pipeline/`, and the Streamlit client in `streamlit_app/`.

## Directory layout

```
src/
|-- config.py               # Environment-driven settings
|-- prompts.py              # Prompt loading helpers
|-- schemas_loader.py       # JSON schema registry and validation helpers
|-- validation.py           # Local validation utilities
|-- llm/                    # Large-language-model provider implementations
|   |-- base.py             # Provider interface and shared helpers
|   |-- openai_provider.py  # OpenAI Responses API client
|   `-- claude_provider.py  # Anthropic Claude client
|-- pipeline/               # CLI/Streamlit pipeline orchestration
|   |-- orchestrator.py     # Four-step pipeline and validation loop
|   |-- validation_runner.py# Dual validation coordinator
|   |-- file_manager.py     # Consistent file naming for outputs
|   `-- utils.py            # Miscellaneous helpers (breakpoints, identifiers)
`-- streamlit_app/          # Streamlit UI
    |-- screens/            # Intro, upload, settings, execution views
    |-- session_state.py    # State initialisation
    |-- file_management.py  # Upload handling and manifest storage
    `-- json_viewer.py      # JSON modal rendering
```

## Core modules

### config.py
Loads environment variables (from `.env` via `python-dotenv`) into immutable dataclasses.

```python
from src.config import llm_settings

assert llm_settings.openai_model == "gpt-5"
assert llm_settings.max_pdf_size_mb == 10  # Pipeline default (can be raised to provider limit 32)
```

### llm package
Provides a provider-agnostic interface (`BaseLLMProvider`) with concrete `OpenAIProvider` and `ClaudeProvider` implementations. Both support:

- `generate_text`
- `generate_json_with_schema`
- `generate_json_with_pdf` (base64 upload with schema enforcement)

Automatic retry, file-size checks, and unified `LLMError` exceptions are built in. Use `src.llm.get_llm_provider("openai")` to construct instances.

### prompts.py and schemas_loader.py
`prompts.py` locates prompt templates in `prompts/` and raises `PromptLoadError` when a file is missing. `schemas_loader.py` loads bundled JSON schemas, performs basic validation, and exposes `load_schema("interventional_trial")`.

### validation.py
Implements local schema validation and quality scoring. `validate_extraction_quality` returns schema compliance, completeness metrics, and detailed error lists. It is used by `pipeline.validation_runner`.

### pipeline package
- `orchestrator.py`: exposes `run_four_step_pipeline`, `run_single_step`, and `run_validation_with_correction`.
- `validation_runner.py`: coordinates schema validation and conditional LLM validation.
- `file_manager.py`: writes numbered outputs (`paper-extraction0.json`, `paper-validation0.json`, `paper-extraction-best.json`, etc.) to `tmp/`.
- `utils.py`: DOI normalisation, step ordering, breakpoint helpers.

### streamlit_app package
Contains the Streamlit client used by `app.py`. Screens orchestrate session state, allow step selection, preview JSON artefacts, and surface verbose execution logs.

## Key APIs

### run_four_step_pipeline
```python
from pathlib import Path
from src.pipeline import run_four_step_pipeline

results = run_four_step_pipeline(
    pdf_path=Path("paper.pdf"),
    max_pages=None,
    llm_provider="openai",
)
print(results["classification"]["publication_type"])
```

Returns a dictionary with completed steps (`classification`, `extraction`, optionally `validation`, `extraction_corrected`, `validation_corrected`).

### run_validation_with_correction
```python
from src.pipeline.orchestrator import run_validation_with_correction

loop_result = run_validation_with_correction(
    pdf_path=Path("paper.pdf"),
    extraction_result=extraction_json,
    classification_result=classification_json,
    llm_provider="claude",
    file_manager=file_manager,
    max_iterations=3,
)
```

Yields the best extraction, the associated validation report, iteration history, quality trajectory, and final status (`passed`, `max_iterations_reached`, etc.).

### PipelineFileManager
Ensures consistent filenames and simplifies loading previously saved outputs.

```python
from pathlib import Path
from src.pipeline import PipelineFileManager

fm = PipelineFileManager(Path("paper.pdf"))
fm.save_json(classification, "classification")
fm.save_json(extraction, "extraction", iteration_number=0)
fm.save_json(best_extraction, "extraction", status="best")
```

## Streamlit integration

`app.py` boots the Streamlit interface and imports components from `src/streamlit_app`. The UI mirrors CLI functionality (classification, extraction, validation/correction) while persisting outputs in `tmp/` and surfacing validation feedback. Verbose logging can be toggled to display token usage and metadata captured during pipeline runs.

## Tests

- Unit tests covering prompt/schema loading, validation, and helpers live under `tests/unit/`.
- Integration tests in `tests/integration/` exercise the orchestrator with mocked providers.
- Use `make test-fast` for quick feedback; `make test-coverage` generates `htmlcov/index.html`.

## Related documentation

- `../README.md` - project overview and setup.
- `../ARCHITECTURE.md` - high-level design and decision log.
- `../VALIDATION_STRATEGY.md` - dual validation and correction loop details.
- `../prompts/README.md` - prompt maintenance guide.
- `../schemas/readme.md` - schema definitions and bundling process.
