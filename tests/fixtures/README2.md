# Test Fixtures

Reusable payloads and helper artefacts shared across the test suite.

## Contents
- **`schemas/`** – Bundled schema snapshots used by schema validation tests.
- Additional fixture factories live in `tests/conftest.py` and may write temporary files into pytest-provided directories.

## Maintenance Tips
- Regenerate schema snapshots when canonical schemas change to prevent mismatches.
- Store only synthetic or anonymised data; never commit real patient information.
- Document fixture shape changes in affected test modules to help reviewers understand new expectations.
