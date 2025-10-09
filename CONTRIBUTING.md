# Contributing to PDFtoPodcast

Thank you for your interest in contributing to PDFtoPodcast! This guide will help you get started with development, testing, and submitting contributions.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Style Guide](#code-style-guide)
- [Testing Guidelines](#testing-guidelines)
- [Adding New Features](#adding-new-features)
- [Submitting Changes](#submitting-changes)
- [Documentation](#documentation)

---

## Code of Conduct

This project follows professional medical software standards:

- **Accuracy First**: Medical data extraction must be accurate and traceable
- **Respectful Communication**: Constructive feedback, professional tone
- **Evidence-Based**: Changes should be motivated by data or clear use cases
- **Documentation**: All changes must be documented
- **Testing**: All features must include tests

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- OpenAI API key and/or Anthropic API key
- Basic understanding of:
  - JSON Schema
  - LLM prompting
  - Medical research terminology (helpful but not required)

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/RobTolboom/PDFtoPodcast.git
   cd PDFtoPodcast
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # Development dependencies
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Verify setup**
   ```bash
   python -c "from src.llm import get_llm_provider; print('✓ Setup OK')"
   ```

6. **Install pre-commit hooks** (optional but recommended)
   ```bash
   pre-commit install
   ```

---

## Development Workflow

### Branch Strategy

We use **trunk-based development** with short-lived feature branches:

```
main (protected)
  ├── feature/add-multilingual-support
  ├── fix/validation-timeout-issue
  └── docs/update-api-reference
```

**Branch Naming Convention:**
- `feature/` - New functionality
- `fix/` - Bug fixes
- `docs/` - Documentation only
- `refactor/` - Code improvements without behavior change
- `test/` - Adding or improving tests

### Daily Workflow

1. **Start with latest main**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Create feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make changes iteratively**
   - Write tests first (TDD recommended)
   - Implement feature
   - Run tests locally
   - Update documentation

4. **Commit frequently**
   ```bash
   git add .
   git commit -m "feat: add initial multilingual support"
   ```

5. **Push and create PR**
   ```bash
   git push -u origin feature/your-feature-name
   # Create PR via GitHub UI
   ```

---

## Code Style Guide

### Python Style

We follow **PEP 8** with the following tools:

- **Black**: Automatic code formatting (line length: 100)
- **Ruff**: Fast linting (replaces flake8, isort, etc.)
- **mypy**: Static type checking

#### Running Code Quality Checks

```bash
# Format code
make format

# Run linters
make lint

# Type checking
make typecheck

# Run all checks
make check
```

### Code Conventions

#### 1. Naming Conventions

```python
# Classes: PascalCase
class OpenAIProvider:
    pass

# Functions/methods: snake_case
def load_schema(schema_name: str) -> Dict:
    pass

# Constants: UPPER_SNAKE_CASE
MAX_PDF_PAGES = 100

# Private methods: _leading_underscore
def _internal_helper():
    pass
```

#### 2. Type Hints

**Always use type hints** for function signatures:

```python
from typing import Dict, List, Optional, Any
from pathlib import Path

def extract_data(
    pdf_path: Path,
    schema: Dict[str, Any],
    max_pages: Optional[int] = None
) -> Dict[str, Any]:
    """
    Extract structured data from PDF.

    Args:
        pdf_path: Path to PDF file
        schema: JSON schema for validation
        max_pages: Maximum pages to process (None = all)

    Returns:
        Extracted data as dictionary

    Raises:
        LLMError: If extraction fails
        ValidationError: If schema validation fails
    """
    pass
```

#### 3. Docstrings

Use **Google-style docstrings**:

```python
def validate_extraction_quality(
    data: Dict[str, Any],
    schema: Dict[str, Any],
    strict: bool = False
) -> Dict[str, Any]:
    """Validate extraction quality using schema and completeness checks.

    Args:
        data: Extracted data to validate
        schema: JSON schema for structural validation
        strict: If True, fail on any schema violation

    Returns:
        Dictionary containing:
            - schema_compliant: bool
            - quality_score: float (0.0-1.0)
            - errors: List[str]
            - warnings: List[str]

    Raises:
        ValidationError: If schema is invalid or data is None

    Example:
        >>> result = validate_extraction_quality(data, schema)
        >>> print(f"Quality: {result['quality_score']:.1%}")
        Quality: 87.5%
    """
    pass
```

#### 4. Error Handling

**Use custom exceptions** and handle errors explicitly:

```python
# Define custom exceptions
class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass

class APIError(LLMError):
    """LLM API call failed."""
    pass

# Usage
try:
    result = llm.generate_json_with_pdf(pdf_path, schema, prompt)
except APIError as e:
    console.print(f"[red]API error: {e}[/red]")
    # Log error, retry, or fail gracefully
except TimeoutError as e:
    console.print(f"[yellow]Request timeout: {e}[/yellow]")
    # Retry with exponential backoff
```

#### 5. Logging

Use **Rich console** for user-facing output:

```python
from rich.console import Console
console = Console()

# User messages
console.print("[green]✅ Classification completed[/green]")
console.print("[yellow]⚠️  Schema quality below threshold[/yellow]")
console.print("[red]❌ Extraction failed[/red]")

# Debug output (dim for less important info)
console.print("[dim]Loading schema: interventional_trial[/dim]")
```

---

## Testing Guidelines

### Test Structure

```
tests/
├── unit/                    # Fast, isolated tests
│   ├── test_llm.py
│   ├── test_schemas.py
│   ├── test_validation.py
│   └── test_prompts.py
├── integration/             # Multi-component tests
│   ├── test_pipeline.py
│   └── test_end_to_end.py
├── fixtures/                # Test data
│   ├── sample_pdfs/
│   │   ├── sample_trial.pdf
│   │   └── sample_review.pdf
│   └── expected_outputs/
│       ├── sample_trial_extraction.json
│       └── sample_review_extraction.json
└── conftest.py             # Shared fixtures
```

### Writing Tests

#### Unit Tests

```python
import pytest
from pathlib import Path
from src.schemas_loader import load_schema, SchemaLoadError

def test_load_classification_schema():
    """Test loading classification schema."""
    schema = load_schema("classification")

    assert schema is not None
    assert "type" in schema
    assert schema["type"] == "object"
    assert "properties" in schema

def test_load_invalid_schema_raises_error():
    """Test that loading invalid schema raises SchemaLoadError."""
    with pytest.raises(SchemaLoadError):
        load_schema("nonexistent_schema")
```

#### Integration Tests

```python
def test_classification_step(sample_pdf: Path, openai_provider):
    """Test complete classification step."""
    from src.prompts import load_classification_prompt
    from src.schemas_loader import load_schema

    prompt = load_classification_prompt()
    schema = load_schema("classification")

    result = openai_provider.generate_json_with_pdf(
        pdf_path=sample_pdf,
        schema=schema,
        system_prompt=prompt,
        max_pages=5
    )

    assert "publication_type" in result
    assert result["publication_type"] in [
        "interventional_trial",
        "observational_analytic",
        "evidence_synthesis",
        "prediction_prognosis",
        "editorials_opinion",
        "overig"
    ]
```

#### Mocking LLM Calls

```python
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_openai_response():
    return {
        "publication_type": "interventional_trial",
        "metadata": {
            "doi": "10.1234/test",
            "title": "Test Paper"
        }
    }

def test_pipeline_with_mock(mock_openai_response):
    """Test pipeline with mocked LLM responses."""
    with patch("src.llm.OpenAIProvider.generate_json_with_pdf") as mock:
        mock.return_value = mock_openai_response

        # Run pipeline
        result = run_classification(pdf_path)

        assert result["publication_type"] == "interventional_trial"
```

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-coverage

# Run specific test file
pytest tests/unit/test_schemas.py -v

# Run specific test
pytest tests/unit/test_schemas.py::test_load_classification_schema -v

# Run with output
pytest tests/ -v -s
```

---

## Adding New Features

### 1. Adding a New Publication Type

**Complete checklist:**

- [ ] Create extraction prompt: `prompts/Extraction-prompt-{type}.txt`
- [ ] Create JSON schema: `schemas/{type}.schema.json`
- [ ] Bundle schema: Run `python schemas/json-bundler.py`
- [ ] Update `SCHEMA_MAPPING` in `src/schemas_loader.py`
- [ ] Update `prompt_mapping` in `src/prompts.py`
- [ ] Add to classification schema enum in `schemas/classification.schema.json`
- [ ] Write tests with sample PDF
- [ ] Update `README.md` supported types table
- [ ] Document in `CHANGELOG.md`

**Example PR:** See `docs/examples/adding-publication-type.md`

### 2. Adding a New LLM Provider

**Checklist:**

- [ ] Create provider class inheriting from `BaseLLMProvider`
- [ ] Implement `generate_json_with_pdf()` method
- [ ] Add to `get_llm_provider()` factory in `src/llm.py`
- [ ] Add environment variables to `src/config.py`
- [ ] Add to `.env.example`
- [ ] Write unit tests for provider
- [ ] Test with integration tests
- [ ] Document in `README.md` and `ARCHITECTURE.md`
- [ ] Update `CHANGELOG.md`

### 3. Adding a New Validation Check

**Checklist:**

- [ ] Add check to `validate_extraction_quality()` in `src/validation.py`
- [ ] Update quality score calculation if needed
- [ ] Add to validation schema if needed
- [ ] Write unit tests
- [ ] Document in `VALIDATION_STRATEGY.md`
- [ ] Update `CHANGELOG.md`

---

## Submitting Changes

### Commit Message Format

We use **Conventional Commits**:

```
<type>(<scope>): <short description>

<longer description if needed>

<footer with issue references>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `refactor`: Code restructuring without behavior change
- `test`: Adding or updating tests
- `chore`: Maintenance tasks (dependencies, config)

**Examples:**

```bash
# Good
git commit -m "feat(validation): add dual-tier validation strategy"
git commit -m "fix(llm): handle OpenAI timeout errors gracefully"
git commit -m "docs(architecture): add data flow diagrams"

# Bad
git commit -m "updated stuff"
git commit -m "WIP"
```

### Pull Request Process

1. **Create feature branch** from `main`

2. **Make your changes** following code style guide

3. **Write/update tests** - PRs without tests will not be merged

4. **Update documentation** - Update relevant `.md` files

5. **Run quality checks**
   ```bash
   make check    # Format, lint, typecheck
   make test     # Run tests
   ```

6. **Update CHANGELOG.md** under "Unreleased" section

7. **Push and create PR** with template filled out

8. **Address review comments** - Reviews typically within 48 hours

9. **Squash and merge** - Maintain clean commit history

### PR Review Checklist

**Before requesting review:**

- [ ] All tests pass (`make test`)
- [ ] Code is formatted (`make format`)
- [ ] Linting passes (`make lint`)
- [ ] Type checking passes (`make typecheck`)
- [ ] Documentation updated
- [ ] `CHANGELOG.md` updated
- [ ] PR template filled out
- [ ] No merge conflicts with `main`

**Reviewers will check:**

- [ ] Code quality and style
- [ ] Test coverage (aim for >80%)
- [ ] Documentation completeness
- [ ] Performance implications
- [ ] Security considerations
- [ ] Medical accuracy (for domain-specific changes)

---

## Documentation

### What to Document

**Code documentation:**
- All public functions must have docstrings
- Complex logic should have inline comments
- Type hints for all function signatures

**User documentation:**
- `README.md` - User-facing features
- `ARCHITECTURE.md` - System design decisions
- `API.md` - Module and function reference

**Process documentation:**
- `CHANGELOG.md` - All user-facing changes
- `ROADMAP.md` - Future plans (if feature is part of roadmap)

### Documentation Style

**Be concise and specific:**

```markdown
# ✅ Good
The validation step uses a two-tier approach: schema validation (fast, cheap)
followed by LLM validation (slow, expensive) only if quality ≥ 50%.

# ❌ Bad
The validation step validates things in two steps.
```

**Include examples:**

```markdown
# ✅ Good
## Usage

```bash
# Process single PDF
python run_pipeline.py paper.pdf

# Limit to first 10 pages
python run_pipeline.py paper.pdf --max-pages 10
```

# ❌ Bad
## Usage

Run the pipeline script.
```

---

## Advanced Contribution Topics

### Working with Schemas

See `SCHEMA_GUIDELINES.md` for detailed guidance on:
- Schema design principles
- Bundling process
- Compatibility testing
- Versioning strategy

### Prompt Engineering

See `PROMPT_ENGINEERING.md` for:
- Effective prompting techniques
- Testing prompts
- A/B testing approach
- Version control for prompts

### Cost Optimization

See `COST_OPTIMIZATION.md` for:
- Token usage tracking
- Provider selection
- Caching strategies
- Development best practices

---

## Getting Help

### Communication Channels

- **GitHub Issues**: Bug reports, feature requests
- **GitHub Discussions**: Questions, ideas, general discussion
- **Pull Requests**: Code review, implementation discussion

### Common Questions

**Q: How do I test changes without spending money on API calls?**

A: Use mocking in unit tests, or use the breakpoint system:
```python
BREAKPOINT_AFTER_STEP = "classification"  # Stop early
```
```bash
python run_pipeline.py paper.pdf --max-pages 5  # Limit pages
```

**Q: How do I add a custom field to an existing schema?**

A:
1. Edit `schemas/{type}.schema.json`
2. Re-bundle: `python schemas/json-bundler.py`
3. Update corresponding prompt
4. Test with sample PDF
5. Update schema version in schema file

**Q: How do I debug validation failures?**

A: Enable verbose output and check `tmp/` files:
```bash
python run_pipeline.py paper.pdf --keep-tmp
cat tmp/{filename}-validation.json | jq '.issues'
```

---

## Recognition

Contributors will be recognized in:
- `CHANGELOG.md` for each release
- GitHub releases
- Project README (for significant contributions)

---

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (Prosperity Public License 3.0.0 for non-commercial use, commercial license available).

See `LICENSE` and `COMMERCIAL_LICENSE.md` for details.

---

**Thank you for contributing to PDFtoPodcast! Your work helps advance medical research data extraction.**
