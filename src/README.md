# 📁 src/ — Core Module Documentation

This directory contains the core modules for the **PDFtoPodcast** medical literature extraction pipeline.

> **📖 For system architecture and design decisions, see [ARCHITECTURE.md](../ARCHITECTURE.md)**

---

## 📦 Module Overview

### Package Structure

```
src/
├── config.py                # Configuration management
├── prompts.py              # Prompt template loading
├── schemas_loader.py       # JSON schema management
├── validation.py           # Validation utilities
├── llm/                    # LLM provider package
│   ├── __init__.py        # Provider factory and exports
│   ├── base.py            # Base provider interface
│   ├── openai_provider.py # OpenAI GPT implementation
│   └── claude_provider.py # Anthropic Claude implementation
├── pipeline/              # Pipeline orchestration package
│   ├── __init__.py       # Pipeline exports
│   ├── orchestrator.py   # Main pipeline logic
│   ├── validation_runner.py # Validation execution
│   ├── file_manager.py   # File I/O management
│   └── utils.py          # Pipeline utilities
└── streamlit_app/        # Web UI package
    ├── __init__.py
    ├── screens/          # UI screens
    ├── session_state.py  # State management
    ├── file_management.py
    ├── json_viewer.py
    └── result_checker.py
```

---

## Core Modules

### ⚙️ `config.py`
**Configuration management for LLM providers and pipeline settings**

```python
from src.config import llm_settings

print(llm_settings.openai_model)     # 'gpt-5'
print(llm_settings.max_pdf_pages)    # 100
print(llm_settings.max_pdf_size_mb)  # 32
```

**Key Features:**
- Multi-provider support (OpenAI & Claude)
- Environment variable configuration via `.env`
- PDF processing limits validation
- Timeout and token limit settings

---

### 🤖 `llm/` Package
**Multi-provider LLM abstraction with PDF upload support**

```python
from src.llm import get_llm_provider, LLMError
from src.schemas_loader import load_schema

# Get provider instance
llm = get_llm_provider("openai")  # or "claude"

# Load schema
schema = load_schema("interventional_trial")

# Extract from PDF with structured output
data = llm.generate_json_with_pdf(
    pdf_path="paper.pdf",
    schema=schema,
    system_prompt="Extract clinical trial data",
    max_pages=20
)
```

**Providers:**
- `OpenAIProvider` - GPT-5 with Responses API
- `ClaudeProvider` - Claude 3.5 Sonnet with Messages API

**API Methods:**
- `generate_text()` - Free-form text generation
- `generate_json_with_schema()` - Schema-enforced JSON with prompt
- `generate_json_with_pdf()` - PDF upload with structured output

**Features:**
- Automatic retry with exponential backoff
- Base64 PDF encoding and validation
- 32 MB file size checking
- Unified error handling via `LLMError`

---

### 📄 `prompts.py`
**Prompt template loading from `prompts/` directory**

```python
from src.prompts import (
    load_classification_prompt,
    load_extraction_prompt,
    load_validation_prompt,
    load_correction_prompt
)

# Load prompts by type
classification_prompt = load_classification_prompt()
extraction_prompt = load_extraction_prompt("interventional_trial")
validation_prompt = load_validation_prompt()
correction_prompt = load_correction_prompt()
```

**Supported Publication Types:**
- `interventional_trial` - RCTs, clinical trials
- `observational_analytic` - Cohort, case-control studies
- `evidence_synthesis` - Meta-analyses, systematic reviews
- `prediction_prognosis` - Prediction models, prognostic studies
- `editorials_opinion` - Editorials, commentaries

**Error Handling:**
- Raises `PromptLoadError` if prompt file not found

---

### 🗂️ `schemas_loader.py`
**JSON Schema loading and validation**

```python
from src.schemas_loader import (
    load_schema,
    validate_schema_compatibility,
    get_supported_publication_types
)

# Load bundled schema
schema = load_schema("interventional_trial")

# Check OpenAI compatibility
compatibility = validate_schema_compatibility(schema)
print(f"Tokens: {compatibility['estimated_tokens']}")
print(f"Compatible: {compatibility['compatible']}")

# List available types
types = get_supported_publication_types()
```

**Schema Types:**
- 5 extraction schemas (publication-type specific)
- 1 classification schema (metadata & type)
- 1 validation schema (quality report)

**Features:**
- Schema caching for performance
- Bundled schemas (all $refs resolved)
- OpenAI/Claude compatibility validation
- Error handling via `SchemaLoadError`

---

### ✅ `validation.py`
**Schema-based validation and quality scoring**

```python
from src.validation import validate_extraction_quality
from src.schemas_loader import load_schema

schema = load_schema("interventional_trial")
results = validate_extraction_quality(data, schema)

print(f"Quality: {results['quality_score']:.1%}")
print(f"Compliant: {results['schema_compliant']}")
print(f"Completeness: {results['completeness_score']:.1%}")
```

**Quality Scoring:**
- 50% weight: Schema compliance (pass/fail)
- 50% weight: Completeness (required=2x, optional=1x)

**Features:**
- Schema validation using `jsonschema` library
- Completeness analysis (required vs optional fields)
- Detailed error reporting
- Quality thresholds for validation gating

---

## Pipeline Package

### 🔄 `pipeline/orchestrator.py`
**Main four-step pipeline orchestration**

```python
from src.pipeline import run_four_step_pipeline
from pathlib import Path

results = run_four_step_pipeline(
    pdf_path=Path("paper.pdf"),
    max_pages=20,
    llm_provider="openai",
    breakpoint_after_step=None  # or "classification", "extraction", etc.
)
```

**Pipeline Steps:**
1. Classification - Identify publication type
2. Extraction - Schema-based data extraction
3. Validation & Correction - Iterative loop until quality sufficient

**Iterative Validation-Correction:**

```python
from src.pipeline.orchestrator import run_validation_with_correction
from pathlib import Path

result = run_validation_with_correction(
    pdf_path=Path("paper.pdf"),
    extraction_result=extraction,
    classification_result=classification,
    llm_provider="openai",
    file_manager=file_manager,
    max_iterations=3,  # Default: 3 correction attempts
    quality_thresholds={
        'completeness_score': 0.90,
        'accuracy_score': 0.95,
        'schema_compliance_score': 0.95,
        'critical_issues': 0
    },
    progress_callback=None  # Optional: UI progress callback
)

# Returns:
{
    'best_extraction': dict,           # Best extraction result
    'best_validation': dict,           # Validation of best extraction
    'iterations': list[dict],          # All iteration history with metrics
    'final_status': str,               # "passed" | "max_iterations_reached" | "failed_*"
    'iteration_count': int,            # Total iterations performed
    'best_iteration': int,             # Iteration number of best result (0-based index)
    'improvement_trajectory': list[float]  # Quality scores per iteration
}
```

**Final Status Codes:**
- `passed`: Quality thresholds met
- `max_iterations_reached`: Max iterations reached, using best result
- `early_stopped_degradation`: Stopped due to quality degradation (2 consecutive)
- `failed_schema_validation`: Schema validation failed (<50% quality)
- `failed_llm_error`: LLM API error after 3 retries
- `failed_invalid_json`: Correction produced invalid JSON
- `failed_unexpected_error`: Unexpected error occurred

**Quality Assessment:**
- Composite score: 40% completeness + 40% accuracy + 20% schema compliance
- Best iteration selected based on: (1) no critical issues, (2) highest quality score, (3) highest completeness

---

### 🔍 `pipeline/validation_runner.py`
**Dual validation strategy execution**

```python
from src.pipeline.validation_runner import run_dual_validation

validation_result = run_dual_validation(
    extraction_result=extracted_data,
    pdf_path=Path("paper.pdf"),
    max_pages=20,
    publication_type="interventional_trial",
    llm=llm_provider,
    console=console
)
```

**Validation Tiers:**
1. **Schema Validation** (always) - Fast, local, free
2. **LLM Validation** (conditional) - Only if quality ≥ 50%

---

### 📁 `pipeline/file_manager.py`
**Pipeline file I/O management**

```python
from src.pipeline import PipelineFileManager

file_manager = PipelineFileManager(pdf_path)
classification_file = file_manager.save_json(data, "classification")
extraction_file = file_manager.save_json(data, "extraction")
```

**File Naming:**
- Pattern: `{pdf_stem}-{step}.json`
- Example: `sample_paper-classification.json`

---

## Web UI Package

### 🌐 `streamlit_app/`
**Streamlit web interface components**

- `screens/` - UI screens (intro, upload, settings)
- `session_state.py` - State management
- `file_management.py` - File operations
- `json_viewer.py` - JSON result display
- `result_checker.py` - Result validation UI

---

## 🔄 Pipeline Flow

```
PDF File (≤100 pages, ≤32 MB)
    ↓
┌─────────────────────────────────────────────┐
│ 1. Classification (PDF upload)              │
│    llm.generate_json_with_pdf()             │
│    Output: classification.json              │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ 2. Extraction (PDF upload)                  │
│    llm.generate_json_with_pdf()             │
│    Output: extraction.json                  │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ 3a. Schema Validation (local)               │
│     validate_extraction_quality()           │
└─────────────────────────────────────────────┘
    ↓ (if quality ≥ 50%)
┌─────────────────────────────────────────────┐
│ 3b. LLM Validation (PDF upload)             │
│     llm.generate_json_with_pdf()            │
│     Output: validation.json                 │
└─────────────────────────────────────────────┘
    ↓ (if validation failed)
┌─────────────────────────────────────────────┐
│ 4. Correction (PDF upload)                  │
│    llm.generate_json_with_pdf()             │
│    Output: extraction-corrected.json        │
└─────────────────────────────────────────────┘
```

---

## 💡 PDF Upload Strategy

### Why Direct PDF Upload?

**Previous approach:** Text extraction with PyMuPDF
- ❌ Tables lost or mangled
- ❌ Images and charts ignored
- ❌ Formatting information lost
- ✅ Cheap (~500 tokens/page)

**Current approach:** Direct PDF upload to LLM
- ✅ Complete table structure preserved
- ✅ Images and charts analyzed visually
- ✅ Formatting and layout preserved
- ⚠️ More expensive (~1,500-3,000 tokens/page)

**Trade-off:** 3-6x cost increase for complete data fidelity, critical for medical research papers.

---

## 📂 Output Structure

Pipeline outputs saved in `tmp/` directory:

```
tmp/
├── {pdf_stem}-classification.json
├── {pdf_stem}-extraction.json
├── {pdf_stem}-validation.json
├── {pdf_stem}-extraction-corrected.json    # If needed
└── {pdf_stem}-validation-corrected.json    # Final validation
```

---

## 📚 Dependencies

**Core:**
- `openai>=1.51.0` - OpenAI API with Responses API
- `anthropic>=0.25.0` - Anthropic Claude API
- `pydantic>=2.7` - Data validation
- `python-dotenv>=1.0` - Environment configuration

**Validation:**
- `jsonschema>=4.20` - JSON schema validation

**Utilities:**
- `tenacity>=8.2` - Retry logic
- `rich` - Console formatting

**Note:** PyMuPDF removed - no longer using text extraction!

---

## 🔗 Related Documentation

- **[../ARCHITECTURE.md](../ARCHITECTURE.md)** - System architecture and design decisions
- **[../CONTRIBUTING.md](../CONTRIBUTING.md)** - Development workflow and guidelines
- **[../DEVELOPMENT.md](../DEVELOPMENT.md)** - Development and debugging
- **[../VALIDATION_STRATEGY.md](../VALIDATION_STRATEGY.md)** - Dual validation approach
- **[../prompts/README.md](../prompts/README.md)** - Prompt engineering guidelines
- **[../schemas/readme.md](../schemas/readme.md)** - Schema design and bundling
- **[../README.md](../README.md)** - Setup and usage instructions
