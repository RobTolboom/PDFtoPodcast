# Schema Fixtures

Bundled JSON Schema fixtures used by tests that validate loader behaviour and backwards compatibility.

## Files
- **`test_common.schema.json`** – Minimal shared definitions for regression tests.
- **`test_study.schema.json`** – Representative study schema used by validation and bundler tests.

## Maintenance
- Update fixtures whenever canonical schema structures change so loader tests remain meaningful.
- Keep fixtures intentionally small to speed up bundler/validation checks while covering critical references.
