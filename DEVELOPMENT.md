# Development Guide

Complete guide for local development, testing, and debugging of PDFtoPodcast.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Development Environment](#development-environment)
- [Project Structure](#project-structure)
- [Common Development Tasks](#common-development-tasks)
- [Testing Strategies](#testing-strategies)
- [Debugging](#debugging)
- [Performance Profiling](#performance-profiling)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/RobTolboom/PDFtoPodcast.git
cd PDFtoPodcast
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Configure
cp .env.example .env
# Edit .env with your API keys

# 4. Verify setup
make test

# 5. Run pipeline on sample
python run_pipeline.py samples/sample_trial.pdf --max-pages 5
```

---

## Development Environment

### Required Tools

- **Python 3.10+**: Core language
- **Git**: Version control
- **Make**: Task automation (optional but recommended)
- **VS Code / PyCharm**: Recommended IDEs

### Optional Tools

- **pre-commit**: Git hooks for code quality
- **jq**: JSON inspection (`brew install jq` or `apt install jq`)
- **httpie**: API testing (`pip install httpie`)

### IDE Setup

#### VS Code

Recommended extensions:
- Python (Microsoft)
- Pylance
- Black Formatter
- Ruff
- JSON
- YAML

`.vscode/settings.json`:
```json
{
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": ["--line-length", "100"],
  "editor.formatOnSave": true,
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests/"],
  "[python]": {
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  }
}
```

#### PyCharm

Settings:
- Enable Black as formatter
- Enable Ruff as linter
- Set pytest as test runner
- Enable type checking with mypy

---

## Project Structure

```
PDFtoPodcast/
├── run_pipeline.py              # Main entry point
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Development dependencies
├── .env.example                 # Environment template
├── .env                         # Your local config (gitignored)
│
├── src/                         # Core source code
│   ├── __init__.py
│   ├── config.py                # Configuration management
│   ├── llm.py                   # LLM provider abstraction
│   ├── prompts.py               # Prompt loading utilities
│   ├── schemas_loader.py        # Schema management
│   ├── validation.py            # Validation logic
│   └── README.md                # Module documentation
│
├── prompts/                     # Prompt templates
│   ├── Classification.txt
│   ├── Extraction-prompt-*.txt
│   ├── Extraction-validation.txt
│   ├── Extraction-correction.txt
│   └── README.md
│
├── schemas/                     # JSON schemas
│   ├── classification.schema.json
│   ├── validation.schema.json
│   ├── *_bundled.json          # Bundled schemas for LLMs
│   ├── json-bundler.py         # Schema bundling script
│   └── readme.md
│
├── tests/                       # Test suite
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   ├── fixtures/               # Test data
│   └── conftest.py            # Pytest configuration
│
├── tmp/                        # Pipeline outputs (gitignored)
│   └── *.json                 # Intermediate results
│
├── docs/                       # Additional documentation
│   ├── ARCHITECTURE.md
│   ├── CONTRIBUTING.md
│   ├── DEVELOPMENT.md (this file)
│   └── examples/
│
└── .github/                    # GitHub configuration
    ├── workflows/             # CI/CD
    └── ISSUE_TEMPLATE/       # Issue templates
```

---

## Common Development Tasks

### Running the Pipeline

```bash
# Full pipeline (all 4 steps)
python run_pipeline.py paper.pdf

# With OpenAI (default)
python run_pipeline.py paper.pdf --llm-provider openai

# With Claude
python run_pipeline.py paper.pdf --llm-provider claude

# Limit pages (save costs during development)
python run_pipeline.py paper.pdf --max-pages 5

# Keep intermediate files
python run_pipeline.py paper.pdf --keep-tmp
```

### Using Breakpoints for Step-by-Step Testing

Edit `run_pipeline.py:104`:

```python
# Stop after classification
BREAKPOINT_AFTER_STEP = "classification"

# Stop after extraction
BREAKPOINT_AFTER_STEP = "extraction"

# Stop after validation
BREAKPOINT_AFTER_STEP = "validation"

# Run full pipeline
BREAKPOINT_AFTER_STEP = None
```

**Example workflow:**

```bash
# 1. Test classification only
# Set BREAKPOINT_AFTER_STEP = "classification"
python run_pipeline.py paper.pdf
# Inspect: tmp/paper-classification.json

# 2. Test extraction
# Set BREAKPOINT_AFTER_STEP = "extraction"
python run_pipeline.py paper.pdf
# Inspect: tmp/paper-extraction.json

# 3. Full pipeline
# Set BREAKPOINT_AFTER_STEP = None
python run_pipeline.py paper.pdf
```

### Code Quality Checks

```bash
# Format code with Black
make format

# Run linter (Ruff)
make lint

# Type checking (mypy)
make typecheck

# All checks together
make check
```

### Running Tests

```bash
# All tests
make test

# With coverage report
make test-coverage

# Specific test file
pytest tests/unit/test_schemas.py -v

# Specific test function
pytest tests/unit/test_schemas.py::test_load_classification_schema -v

# Run with verbose output
pytest tests/ -v -s

# Run only fast tests (skip integration)
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v
```

### Working with Schemas

```bash
# Validate a schema file
python validate_schemas.py schemas/interventional_trial.schema.json

# Bundle schemas (inline all $ref)
cd schemas
python json-bundler.py

# Test schema with sample data
cat tmp/sample-extraction.json | jq -s '.[0]' | \
  python -c "import sys, json; from src.schemas_loader import load_schema; \
  from jsonschema import validate; \
  data = json.load(sys.stdin); \
  schema = load_schema('interventional_trial'); \
  validate(data, schema); \
  print('✓ Valid')"
```

### Inspecting Pipeline Outputs

```bash
# Pretty-print JSON
cat tmp/paper-classification.json | jq '.'

# Extract specific fields
cat tmp/paper-extraction.json | jq '.metadata'

# Check validation issues
cat tmp/paper-validation.json | jq '.issues[]'

# Count issues by severity
cat tmp/paper-validation.json | jq '[.issues[] | .severity] | group_by(.) | map({severity: .[0], count: length})'
```

---

## Testing Strategies

### Unit Testing Strategy

**Fast, isolated tests** for individual functions:

```python
# tests/unit/test_schemas.py
def test_load_schema_caches_results():
    """Test that schemas are cached after first load."""
    from src.schemas_loader import load_schema, _schema_cache

    # Clear cache
    _schema_cache.clear()

    # First load
    schema1 = load_schema("classification")
    assert "classification" in _schema_cache

    # Second load (should use cache)
    schema2 = load_schema("classification")
    assert schema1 is schema2  # Same object
```

### Integration Testing Strategy

**Test multiple components together**:

```python
# tests/integration/test_pipeline.py
def test_classification_step_end_to_end(sample_pdf):
    """Test complete classification step."""
    from src.llm import get_llm_provider
    from src.prompts import load_classification_prompt
    from src.schemas_loader import load_schema

    llm = get_llm_provider("openai")
    prompt = load_classification_prompt()
    schema = load_schema("classification")

    result = llm.generate_json_with_pdf(
        pdf_path=sample_pdf,
        schema=schema,
        system_prompt=prompt,
        max_pages=5
    )

    # Validate result structure
    assert "publication_type" in result
    assert "metadata" in result
    assert result["metadata"]["title"]
```

### Mocking LLM Calls

**Save costs during testing**:

```python
# tests/conftest.py
import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_llm_response():
    """Sample LLM response for testing."""
    return {
        "publication_type": "interventional_trial",
        "metadata": {
            "doi": "10.1234/test",
            "title": "Test Trial",
            "authors": ["Smith J", "Doe J"]
        },
        "classification_confidence": 0.95
    }

@pytest.fixture
def mock_openai_provider(mock_llm_response):
    """Mocked OpenAI provider."""
    provider = Mock()
    provider.generate_json_with_pdf.return_value = mock_llm_response
    return provider
```

### Fixture-Based Testing

**Use real sample PDFs** for integration tests:

```
tests/fixtures/
├── sample_pdfs/
│   ├── sample_trial.pdf          # Interventional trial
│   ├── sample_observational.pdf  # Cohort study
│   └── sample_review.pdf         # Meta-analysis
└── expected_outputs/
    ├── sample_trial_classification.json
    ├── sample_trial_extraction.json
    └── sample_trial_validation.json
```

---

## Debugging

### Enable Verbose Logging

```python
# In run_pipeline.py or src modules
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug(f"Schema loaded: {schema.keys()}")
logger.info(f"Processing PDF: {pdf_path}")
logger.warning(f"Schema quality below threshold: {quality_score}")
logger.error(f"LLM call failed: {error}")
```

### Debug LLM Requests

**See actual prompts and responses**:

```python
# In src/llm.py, add debugging
def generate_json_with_pdf(self, pdf_path, schema, system_prompt, ...):
    # Log the prompt
    print(f"PROMPT:\n{system_prompt}\n")

    # Make API call
    response = self.client.chat.completions.create(...)

    # Log the response
    print(f"RESPONSE:\n{response}\n")

    return parsed_json
```

### Interactive Debugging with pdb

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use built-in breakpoint() (Python 3.7+)
breakpoint()
```

**Common pdb commands:**
- `n` - Next line
- `s` - Step into function
- `c` - Continue execution
- `p variable` - Print variable
- `pp variable` - Pretty-print variable
- `l` - Show source code context
- `q` - Quit debugger

### Debugging with VS Code

Add to `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Pipeline",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/run_pipeline.py",
      "args": ["samples/sample_trial.pdf", "--max-pages", "5"],
      "console": "integratedTerminal",
      "justMyCode": true,
      "env": {
        "PYTHONPATH": "${workspaceFolder}"
      }
    },
    {
      "name": "Python: Current Test",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["${file}", "-v", "-s"],
      "console": "integratedTerminal",
      "justMyCode": false
    }
  ]
}
```

---

## Performance Profiling

### Token Usage Tracking

```python
# Track tokens per step
import tiktoken

def count_tokens(text: str, model: str = "gpt-4") -> int:
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

# Before LLM call
prompt_tokens = count_tokens(system_prompt)
schema_tokens = count_tokens(json.dumps(schema))
print(f"Prompt: {prompt_tokens}, Schema: {schema_tokens}")
```

### Timing Pipeline Steps

```python
import time
from functools import wraps

def timer(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"{func.__name__} took {elapsed:.2f}s")
        return result
    return wrapper

@timer
def run_classification(...):
    # Step implementation
    pass
```

### Memory Profiling

```bash
# Install memory profiler
pip install memory-profiler

# Add decorator
from memory_profiler import profile

@profile
def process_large_pdf(...):
    # Function implementation
    pass

# Run with profiling
python -m memory_profiler run_pipeline.py paper.pdf
```

---

## Troubleshooting

### Common Issues

#### 1. API Key Not Found

```
Error: OPENAI_API_KEY not found
```

**Solution:**
```bash
# Check .env file exists
ls -la .env

# Verify key is set
cat .env | grep OPENAI_API_KEY

# Load environment
source .env  # Bash
# or
export $(cat .env | xargs)  # Alternative
```

#### 2. Schema Validation Fails

```
jsonschema.exceptions.ValidationError: 'title' is a required property
```

**Solution:**
```python
# Debug the data structure
import json
data = json.load(open('tmp/paper-extraction.json'))
print(f"Keys: {data.keys()}")
print(f"Metadata: {data.get('metadata', {})}")

# Check what's missing
from jsonschema import validate, ValidationError
try:
    validate(data, schema)
except ValidationError as e:
    print(f"Failed at: {e.json_path}")
    print(f"Message: {e.message}")
```

#### 3. LLM Timeout

```
TimeoutError: Request timeout after 120s
```

**Solution:**
```python
# Increase timeout in .env
LLM_TIMEOUT=300  # 5 minutes

# Or reduce PDF pages
python run_pipeline.py paper.pdf --max-pages 10
```

#### 4. PDF Too Large

```
Error: PDF size 45MB exceeds limit of 32MB
```

**Solution:**
```bash
# Split PDF
pdftk input.pdf cat 1-50 output part1.pdf
pdftk input.pdf cat 51-100 output part2.pdf

# Or compress PDF
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 \
   -dPDFSETTINGS=/ebook -dNOPAUSE -dQUIET -dBATCH \
   -sOutputFile=compressed.pdf input.pdf
```

#### 5. Module Import Errors

```
ModuleNotFoundError: No module named 'src'
```

**Solution:**
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Add project to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Getting Help

1. **Check existing documentation**:
   - README.md
   - ARCHITECTURE.md
   - CONTRIBUTING.md

2. **Search issues**:
   - https://github.com/RobTolboom/PDFtoPodcast/issues

3. **Enable debug output**:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

4. **Create minimal reproduction**:
   ```bash
   python run_pipeline.py samples/minimal_test.pdf --max-pages 2
   ```

5. **Open GitHub issue** with:
   - Error message
   - Steps to reproduce
   - Environment info (Python version, OS, dependencies)
   - Relevant logs

---

## Development Best Practices

### 1. Always Use Breakpoints During Development

```python
# Don't waste money on full pipeline runs
BREAKPOINT_AFTER_STEP = "classification"  # Test one step at a time
```

### 2. Limit Pages for Testing

```bash
# Use small page counts
python run_pipeline.py paper.pdf --max-pages 5
```

### 3. Use Mocking for Unit Tests

```python
# Never call real LLM APIs in unit tests
@patch('src.llm.OpenAIProvider.generate_json_with_pdf')
def test_classification(mock_llm):
    mock_llm.return_value = {...}
    # Test logic
```

### 4. Keep tmp/ Directory Clean

```bash
# Regularly clean up old test outputs
rm tmp/*.json

# Or use --keep-tmp flag selectively
```

### 5. Version Control Hygiene

```bash
# Never commit sensitive data
git status | grep tmp/    # Should show nothing
git status | grep .env    # Should show nothing

# Use .gitignore properly
echo ".env" >> .gitignore
echo "tmp/" >> .gitignore
```

---

## Next Steps

- Read `ARCHITECTURE.md` for system design
- See `CONTRIBUTING.md` for contribution guidelines
- Check `TESTING.md` for comprehensive testing guide
- Review `API.md` for module reference

**Happy coding!**
