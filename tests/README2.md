# Test Suite Overview

Tests ensure the pipeline, schema tooling, and UI integrations stay reliable.

## Layout
| Path | Description |
| --- | --- |
| `unit/` | Fine-grained tests for pipeline utilities, LLM providers, schema loaders, and validation helpers. |
| `integration/` | Multi-step pipeline scenarios verifying orchestration, schema compliance, and prompt interactions. |
| `fixtures/` | Shared payloads, schema samples, and helper factories. |
| `validate_schemas.py` | Standalone schema validation script used by CI. |
| `conftest.py` | Pytest fixtures configuring temporary directories and provider stubs. |

## Running Tests
```bash
pytest tests/unit -v
pytest tests/integration -v
pytest tests --cov=src --cov-report=term-missing
python tests/validate_schemas.py
```

## Contribution Checklist
- Update or add fixtures when schemas, prompts, or pipeline outputs change.
- Use `pytest.mark.slow` or environment guards for tests that hit real LLM endpoints.
- Keep assertions focused on schema keys and validation scores to detect regressions clearly.
