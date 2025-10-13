# Test Suite

> **📖 For complete testing guidelines, see [CONTRIBUTING.md](../CONTRIBUTING.md)**
> This document provides quick reference for running and writing tests.

Comprehensive test suite for PDFtoPodcast medical literature extraction pipeline.

---

## Quick Start

```bash
# Run all tests
make test

# Fast unit tests only
make test-unit

# Integration tests
make test-integration

# With coverage report
make test-coverage
```

---

## Test Structure

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

---

## Running Tests

### Using Make Commands

```bash
# All tests
make test

# Unit tests only (fast)
make test-unit

# Integration tests only
make test-integration

# With coverage
make test-coverage
```

### Using Pytest Directly

```bash
# All tests with verbose output
pytest tests/ -v

# Specific test file
pytest tests/unit/test_schemas.py -v

# Specific test function
pytest tests/unit/test_schemas.py::test_load_classification_schema -v

# With output capture disabled
pytest tests/ -v -s
```

### Test Markers

```bash
# Skip slow tests
pytest -m "not slow"

# Only integration tests
pytest -m integration

# Only unit tests
pytest -m unit
```

---

## Writing Tests

### Unit Tests

Fast, isolated tests for individual functions:

```python
import pytest
from src.schemas_loader import load_schema, SchemaLoadError

def test_load_classification_schema():
    """Test loading classification schema."""
    schema = load_schema("classification")

    assert schema is not None
    assert "properties" in schema
    assert schema["type"] == "object"

def test_load_invalid_schema_raises_error():
    """Test that loading invalid schema raises SchemaLoadError."""
    with pytest.raises(SchemaLoadError):
        load_schema("nonexistent_schema")
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

    assert result["publication_type"] in [
        "interventional_trial",
        "observational_analytic",
        "evidence_synthesis",
        "prediction_prognosis",
        "editorials_opinion",
        "overig"
    ]
```

---

## Test Markers

Use markers to categorize tests:

```python
@pytest.mark.slow
def test_full_pipeline():
    """This test is slow - only run when needed."""
    pass

@pytest.mark.integration
def test_llm_integration():
    """Integration test requiring LLM."""
    pass

@pytest.mark.unit
def test_schema_loading():
    """Fast unit test."""
    pass
```

---

## Mocking LLM Calls

Mock LLM calls to avoid API costs during testing:

```python
from unittest.mock import Mock, patch

@patch('src.llm.OpenAIProvider.generate_json_with_pdf')
def test_with_mock(mock_generate):
    """Test with mocked LLM response."""
    mock_generate.return_value = {
        "publication_type": "interventional_trial",
        "metadata": {"doi": "10.1234/test"}
    }

    # Test logic here
    result = run_classification(pdf_path)
    assert result["publication_type"] == "interventional_trial"
```

---

## Fixtures

Shared test data in `conftest.py`:

```python
@pytest.fixture
def sample_pdf():
    """Provide path to sample PDF."""
    return Path("tests/fixtures/sample_pdfs/sample_trial.pdf")

@pytest.fixture
def mock_openai_provider():
    """Provide mocked OpenAI provider."""
    return Mock(spec=OpenAIProvider)
```

Use fixtures in tests:

```python
def test_something(sample_pdf, mock_openai_provider):
    """Test using fixtures."""
    # Fixtures automatically provided by pytest
    assert sample_pdf.exists()
    assert mock_openai_provider is not None
```

---

## Coverage

Aim for >80% code coverage:

```bash
# Run tests with coverage
make test-coverage

# Opens htmlcov/index.html in browser
```

Coverage reports show:
- Which lines are tested
- Which branches are covered
- Overall coverage percentage

---

## Best Practices

1. **Fast unit tests** - Mock external dependencies (API calls, file I/O)
2. **Meaningful names** - Use descriptive test names: `test_load_schema_raises_error_for_invalid_name`
3. **One focus per test** - Each test should verify one specific behavior
4. **Use fixtures** - Share common test data and setup
5. **Mark slow tests** - Use `@pytest.mark.slow` for tests that take >1 second
6. **Test edge cases** - Empty inputs, malformed data, boundary conditions

---

## Development Workflow

```bash
# Before committing
make test-unit          # Quick feedback
make format             # Format code
make lint               # Check code quality
make test               # Run all tests
make commit             # Prepare for commit
```

**For complete testing guidelines and contribution process, see [CONTRIBUTING.md](../CONTRIBUTING.md)**

---

## Related Documentation

- **[CONTRIBUTING.md](../CONTRIBUTING.md)** - Complete testing guidelines
- **[DEVELOPMENT.md](../DEVELOPMENT.md)** - Development workflow
- **[src/README.md](../src/README.md)** - Module API documentation
- **[README.md](../README.md)** - Project overview
