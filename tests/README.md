# Test Suite

> **📖 For complete testing guidelines and contribution process, see [CONTRIBUTING.md](../CONTRIBUTING.md)**
> This document provides quick reference for running and writing tests.

Comprehensive test suite for PDFtoPodcast.

## Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_schemas.py      # Schema loading and validation
│   ├── test_prompts.py      # Prompt loading
│   ├── test_validation.py   # Validation logic
│   └── test_llm.py          # LLM provider interface
├── integration/             # Integration tests (slower, end-to-end)
│   ├── test_pipeline.py     # Full pipeline tests
│   └── test_providers.py    # Provider integration tests
└── fixtures/                # Test data
    ├── sample_pdfs/         # Sample PDFs for testing
    └── expected_outputs/    # Expected extraction results
```

## Running Tests

```bash
# All tests
make test

# Unit tests only (fast)
make test-unit

# Integration tests only
make test-integration

# With coverage
make test-coverage

# Specific test file
pytest tests/unit/test_schemas.py -v

# Specific test
pytest tests/unit/test_schemas.py::test_load_classification_schema -v
```

## Writing Tests

### Unit Tests

Fast, isolated tests for individual functions:

```python
def test_load_schema():
    """Test schema loading."""
    from src.schemas_loader import load_schema

    schema = load_schema("classification")
    assert schema is not None
    assert "properties" in schema
```

### Integration Tests

Test multiple components working together:

```python
def test_classification_pipeline(sample_pdf, mock_openai_provider):
    """Test classification with mocked LLM."""
    from src.prompts import load_classification_prompt
    from src.schemas_loader import load_schema

    prompt = load_classification_prompt()
    schema = load_schema("classification")

    result = mock_openai_provider.generate_json_with_pdf(
        pdf_path=sample_pdf,
        schema=schema,
        system_prompt=prompt
    )

    assert result["publication_type"] in ["interventional_trial", ...]
```

## Test Markers

Use markers to categorize tests:

```python
@pytest.mark.slow
def test_full_pipeline():
    """This test is slow."""
    pass

@pytest.mark.integration
def test_llm_integration():
    """Integration test."""
    pass
```

Run specific markers:
```bash
# Skip slow tests
pytest -m "not slow"

# Only integration tests
pytest -m integration
```

## Mocking

Mock LLM calls to avoid API costs:

```python
from unittest.mock import Mock, patch

@patch('src.llm.OpenAIProvider.generate_json_with_pdf')
def test_with_mock(mock_generate):
    mock_generate.return_value = {"publication_type": "interventional_trial"}
    # Test logic
```

## Fixtures

Shared test data in `conftest.py`:

```python
@pytest.fixture
def sample_pdf():
    return Path("tests/fixtures/sample_pdfs/sample_trial.pdf")
```

Use in tests:

```python
def test_something(sample_pdf):
    # sample_pdf fixture automatically provided
    assert sample_pdf.exists()
```

## Coverage

Aim for >80% coverage:

```bash
make test-coverage
# Opens htmlcov/index.html
```

## Best Practices

1. **Fast unit tests**: Mock external dependencies
2. **Meaningful names**: `test_load_schema_raises_error_for_invalid_name`
3. **One assertion focus**: Test one thing per test function
4. **Use fixtures**: Share common test data
5. **Mark slow tests**: Use `@pytest.mark.slow`
6. **Test edge cases**: Empty inputs, malformed data, etc.

## TODO

- [ ] Add unit tests for all src/ modules
- [ ] Add integration tests for full pipeline
- [ ] Add sample PDFs to fixtures
- [ ] Add expected outputs for validation
- [ ] Achieve >80% code coverage

---

## Related Documentation

- **[CONTRIBUTING.md](../CONTRIBUTING.md)** - Complete testing guidelines and contribution process
- **[DEVELOPMENT.md](../DEVELOPMENT.md)** - Development workflow and debugging strategies
- **[ARCHITECTURE.md](../ARCHITECTURE.md)** - System architecture and component design
- **[src/README.md](../src/README.md)** - Core module API documentation
