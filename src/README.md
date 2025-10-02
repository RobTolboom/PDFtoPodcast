# 📁 src/ — Core Module Documentation

This directory contains the core modules for the **PDFtoPodcast** medical literature extraction pipeline. The pipeline uses direct PDF upload to LLMs (no text extraction) to preserve tables, images, charts, and formatting.

---

## 🏗️ Architecture Overview

The pipeline follows a **four-step extraction workflow**:
1. **Classification** - Identify publication type and extract metadata
2. **Extraction** - Schema-based structured data extraction
3. **Validation** - Dual validation (schema + LLM semantic)
4. **Correction** - Fix issues identified during validation

All steps use **direct PDF upload** (OpenAI vision API / Claude document API) to ensure complete data fidelity.

---

## 📦 Module Overview

### ⚙️ `config.py`
**Purpose:** Configuration management for LLM providers

**Key features:**
- Multi-provider support (OpenAI & Claude)
- Environment variable configuration via `.env`
- PDF processing limits (100 pages, 32 MB)
- Timeout and token limit settings

**Usage:**
```python
from src.config import llm_settings
print(llm_settings.openai_model)  # 'gpt-4o'
print(llm_settings.max_pdf_pages)  # 100
```

---

### 🤖 `llm.py`
**Purpose:** Multi-provider LLM abstraction layer with PDF upload support

**Key features:**
- Abstract `BaseLLMProvider` interface
- OpenAI provider (GPT-4o vision API)
- Claude provider (document API)
- Three generation modes:
  - `generate_text()` - Free-form text
  - `generate_json()` - Generic JSON (no schema)
  - `generate_json_with_schema()` - Schema-enforced JSON
  - `generate_json_with_pdf()` - PDF upload with structured output ⭐ NEW
- Automatic retry logic with exponential backoff
- Base64 PDF encoding and upload
- 32 MB file size validation

**Usage:**
```python
from src.llm import get_llm_provider
from src.schemas_loader import load_schema

llm = get_llm_provider("openai")
schema = load_schema("interventional_trial")

# Direct PDF upload with structured output
data = llm.generate_json_with_pdf(
    pdf_path="paper.pdf",
    schema=schema,
    system_prompt="Extract clinical trial data",
    max_pages=20
)
```

---

### 📄 `prompts.py`
**Purpose:** Prompt template loading from `prompts/` directory

**Key features:**
- Load classification prompt (`Classification.txt`)
- Load type-specific extraction prompts (5 publication types)
- Load validation prompt (`Extraction-validation.txt`)
- Load correction prompt (`Extraction-correction.txt`)
- Error handling with `PromptLoadError`

**Supported publication types:**
- `interventional_trial` - RCTs, clinical trials
- `observational_analytic` - Cohort, case-control studies
- `evidence_synthesis` - Meta-analyses, systematic reviews
- `prediction_prognosis` - Prediction models, prognostic studies
- `editorials_opinion` - Editorials, commentaries

**Usage:**
```python
from src.prompts import load_classification_prompt, load_extraction_prompt

classification_prompt = load_classification_prompt()
extraction_prompt = load_extraction_prompt("interventional_trial")
```

---

### 🗂️ `schemas_loader.py`
**Purpose:** JSON Schema loading and management

**Key features:**
- Load bundled JSON schemas (all $refs resolved)
- Schema caching for performance
- OpenAI compatibility validation
- Support for 7 schema types:
  - 5 extraction schemas (publication-type specific)
  - 1 classification schema (metadata & type)
  - 1 validation schema (quality report)

**Usage:**
```python
from src.schemas_loader import load_schema, validate_schema_compatibility

schema = load_schema("interventional_trial")
compatibility = validate_schema_compatibility(schema)
print(f"Estimated tokens: {compatibility['estimated_tokens']}")
```

**Schema mapping:**
- `interventional_trial` → `interventional_trial_bundled.json`
- `observational_analytic` → `observational_analytic_bundled.json`
- `evidence_synthesis` → `evidence_synthesis_bundled.json`
- `prediction_prognosis` → `prediction_prognosis_bundled.json`
- `editorials_opinion` → `editorials_opinion_bundled.json`
- `classification` → `classification.schema.json`
- `validation` → `validation.schema.json`

---

### ✅ `validation.py`
**Purpose:** Schema-based validation utilities

**Key features:**
- Schema validation using `jsonschema` library
- Quality scoring (schema compliance + completeness)
- Completeness analysis (required vs optional fields)
- Validation reporting with detailed error messages

**Usage:**
```python
from src.validation import validate_extraction_quality
from src.schemas_loader import load_schema

schema = load_schema("interventional_trial")
results = validate_extraction_quality(data, schema)

print(f"Quality: {results['quality_score']:.1%}")
print(f"Compliant: {results['schema_compliant']}")
```

**Quality scoring:**
- 50% weight: Schema compliance (pass/fail)
- 50% weight: Completeness (weighted: required=2x, optional=1x)

---

## 🔄 Pipeline Flow

```
PDF File (≤100 pages, ≤32 MB)
    ↓
┌─────────────────────────────────────────────┐
│ 1. Classification (PDF upload)              │
│    - Identify publication type              │
│    - Extract metadata (DOI, authors, etc)   │
│    Output: classification.schema.json       │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ 2. Extraction (PDF upload)                  │
│    - Type-specific schema                   │
│    - Tables, figures, complete data         │
│    Output: {type}_bundled.json              │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ 3a. Schema Validation (local, fast)         │
│     - Structure check                       │
│     - Type validation                       │
│     - Quality score calculation             │
└─────────────────────────────────────────────┘
    ↓ (if quality ≥ 50%)
┌─────────────────────────────────────────────┐
│ 3b. LLM Validation (PDF upload, conditional)│
│     - Semantic accuracy check               │
│     - Completeness assessment               │
│     - Hallucination detection               │
│     Output: validation.schema.json          │
└─────────────────────────────────────────────┘
    ↓ (if validation failed)
┌─────────────────────────────────────────────┐
│ 4. Correction (PDF upload, optional)        │
│    - Fix identified issues                  │
│    - Re-extract missing data                │
│    - Re-validate corrected output           │
└─────────────────────────────────────────────┘
```

---

## 💡 PDF Upload Strategy

### Why PDF Upload?
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

### Cost-Benefit Analysis
- **Cost:** 3-6x more tokens per page
- **Benefit:** Complete data fidelity
- **Worth it for:** Medical research papers where tables contain critical trial results

### API Limits (OpenAI & Claude)
- Maximum 100 pages per PDF
- Maximum 32 MB file size
- Base64 encoding used for upload

---

## 📂 Output Structure

Pipeline outputs are saved in `tmp/` directory with DOI-based naming:

```
tmp/
├── {doi}-classification.json          # Step 1 output
├── {doi}-extraction.json               # Step 2 output
├── {doi}-validation.json               # Step 3 output
├── {doi}-extraction-corrected.json     # Step 4 output (if needed)
└── {doi}-validation-corrected.json     # Final validation (if corrected)
```

**DOI-based naming example:**
- DOI: `10.1186/s12871-025-02345-6`
- Files: `10-1186-s12871-025-02345-6-classification.json`

---

## 🛠️ Development

### Adding a New Module

1. Create module in `src/`
2. Add comprehensive docstring
3. Import in `run_pipeline.py` if needed
4. Update this README

### Testing Schemas

```bash
# Test schema loading
python -c "from src.schemas_loader import load_schema; \
           schema = load_schema('classification'); \
           print('✓ Schema loaded')"

# Validate all schemas
python -c "from src.schemas_loader import get_all_available_schemas; \
           schemas = get_all_available_schemas(); \
           print(f'✓ {len(schemas)} schemas available')"
```

---

## 📚 Dependencies

- `openai>=1.51.0` - OpenAI API client with vision support
- `anthropic>=0.25.0` - Anthropic Claude API client
- `jsonschema>=4.20` - JSON schema validation
- `tenacity>=8.2` - Retry logic with backoff
- `python-dotenv>=1.0` - Environment configuration
- `pydantic>=2.7` - Data validation
- `rich` - Console formatting
- `structlog` - Structured logging

**Note:** PyMuPDF removed - no longer using text extraction!

---

## 🔗 Related Documentation

- `../VALIDATION_STRATEGY.md` - Dual validation approach explained
- `../prompts/README.md` - Prompt engineering guidelines
- `../schemas/readme.md` - Schema design and bundling
- Project root README - Setup and usage instructions
