# Integration Tests

Integration tests exercise multi-module flows and schema tooling.

## Current Coverage
- **`test_schema_bundling.py`** – Verifies that `json-bundler.py` produces dereferenced schema bundles and that bundled files validate correctly.

## Adding New Tests
- Use real pipeline entry points (`src.pipeline.orchestrator.run_single_step`) where possible to capture regressions across modules.
- Mark network-dependent tests with `pytest.mark.slow` and guard them behind environment variables for CI stability.
- Share fixtures via `tests/fixtures/` to keep expected payloads consistent with unit tests.
