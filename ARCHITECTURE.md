# Architecture Documentation

## System Overview

PDFtoPodcast is a **medical literature data extraction pipeline** that uses LLM vision capabilities to extract structured data from PDF research papers with complete fidelity. The system prioritizes **preserving tables, figures, and complex formatting** that are critical for medical research.

### Core Design Principles

1. **Vision-First Approach**: Direct PDF upload to LLMs (no text extraction) preserves visual data
2. **Schema-Driven Extraction**: JSON Schema enforcement ensures consistent, structured outputs
3. **Dual Validation**: Combined schema + LLM validation for cost-effective quality control
4. **Publication-Type Specialization**: Different schemas for different research types
5. **Provider Abstraction**: Support for multiple LLM providers (OpenAI, Claude)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                           │
│                    (run_pipeline.py CLI)                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Pipeline Orchestrator                         │
│                  (run_four_step_pipeline)                        │
│                                                                   │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐   │
│  │   Step 1  │─▶│   Step 2  │─▶│   Step 3  │─▶│   Step 4  │   │
│  │Classify   │  │ Extract   │  │ Validate  │  │  Correct  │   │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │   LLM Layer  │ │ Schema Layer │ │Validation Lyr│
    │              │ │              │ │              │
    │ • OpenAI    │ │ • Loader     │ │ • Schema Val │
    │ • Claude    │ │ • Bundler    │ │ • LLM Val    │
    │ • PDF Upload│ │ • Validator  │ │ • Quality    │
    └──────────────┘ └──────────────┘ └──────────────┘
            │               │               │
            └───────────────┴───────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │  File Manager    │
                  │  (PDF-based)     │
                  └──────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │  tmp/        │
                    │  (outputs)   │
                    └──────────────┘
```

---

## Component Architecture

### 1. Pipeline Orchestrator (`run_pipeline.py`)

**Responsibilities:**
- Coordinate 4-step extraction workflow
- Handle breakpoints for testing
- Manage intermediate file I/O
- Display user-friendly progress

**Key Functions:**
- `run_four_step_pipeline()`: Main orchestration logic
- `run_dual_validation()`: Implements two-tier validation strategy
- `check_breakpoint()`: Testing support

**Design Decisions:**
- **Why 4 steps?** Separation of concerns: classify → extract → validate → correct
- **Why breakpoints?** Enable step-by-step testing without full pipeline runs
- **Why PDF filename-based naming?** Consistent file tracking across pipeline stages, works without DOI

---

### 2. LLM Provider Layer (`src/llm.py`)

**Architecture Pattern:** Abstract Base Class + Concrete Implementations

```python
BaseLLMProvider (ABC)
    ├── OpenAIProvider
    └── ClaudeProvider
```

**Key Interface:**
```python
class BaseLLMProvider:
    def generate_json_with_pdf(
        pdf_path: Path,
        schema: Dict,
        system_prompt: str,
        max_pages: Optional[int],
        schema_name: str
    ) -> Dict[str, Any]
```

**Design Decisions:**
- **Why abstraction?** Easy to add new providers (Gemini, local models, etc.)
- **Why direct PDF upload?** Preserves tables/figures (critical for medical data)
- **Cost trade-off:** 3-6x more tokens than text extraction, but 100% fidelity

**Provider Comparison:**

| Feature | OpenAI (GPT-5) | Claude (Opus/Sonnet) |
|---------|----------------|----------------------|
| PDF Support | ✅ Base64 | ✅ Base64 + media type |
| Max Pages | 100 | 100 |
| Max Size | 32 MB | 32 MB |
| Token Cost/Page | ~2,000 | ~2,000 |
| Structured Output | `response_format` | Native JSON mode |

---

### 3. Schema Management Layer (`src/schemas_loader.py`)

**Responsibilities:**
- Load JSON schemas from `schemas/` directory
- Validate schema compatibility with LLM providers
- Estimate token usage for schemas

**Key Functions:**
- `load_schema(schema_name: str) -> Dict`: Load and cache schemas
- `validate_schema_compatibility(schema: Dict) -> Dict`: Check OpenAI compatibility
- `estimate_schema_tokens(schema: Dict) -> int`: Token estimation

**Schema Architecture:**

```
schemas/
├── classification.schema.json           # Step 1 output
├── validation.schema.json               # Step 3 output
├── interventional_trial_bundled.json    # Step 2 (RCT, trials)
├── observational_analytic_bundled.json  # Step 2 (cohort, case-control)
├── evidence_synthesis_bundled.json      # Step 2 (meta-analysis)
├── prediction_prognosis_bundled.json    # Step 2 (ML models)
└── editorials_opinion_bundled.json      # Step 2 (commentary)
```

**Design Decisions:**
- **Why bundled schemas?** Inline all `$ref` for LLM compatibility
- **Why separate schemas per type?** Medical research requires domain-specific fields
- **Why JSON Schema?** Industry standard, validation tooling, LLM native support

---

### 4. Validation Layer (`src/validation.py`)

**Two-Tier Validation Strategy:**

#### Tier 1: Schema Validation (Always Runs)
- **Speed:** Milliseconds
- **Cost:** Free (local validation)
- **Coverage:** ~80% of errors (structural)
- **Implementation:** `jsonschema` library

```python
def validate_extraction_quality(
    data: Dict,
    schema: Dict,
    strict: bool = False
) -> Dict:
    # Returns quality score (0.0-1.0)
    # Checks: schema compliance, completeness, required fields
```

#### Tier 2: LLM Validation (Conditional)
- **Trigger:** Only if schema quality ≥ 50%
- **Speed:** 30-60 seconds
- **Cost:** ~$0.20-$3.00 per validation
- **Coverage:** ~20% of errors (semantic, hallucinations)

**Design Rationale:**
- **Why two tiers?** Cost optimization - don't spend $3 validating broken JSON
- **Why 50% threshold?** Empirical balance between cost and quality
- **Why LLM validation at all?** Schema can't catch hallucinations or medical inaccuracies

**Quality Score Calculation:**
```python
quality_score = (
    0.5 * schema_compliance +    # Valid JSON structure
    0.3 * completeness +         # Required fields filled
    0.2 * field_coverage         # Optional fields filled
)
```

---

### 5. Prompt Management (`src/prompts.py`)

**Responsibilities:**
- Load prompt templates from `prompts/` directory
- Map publication types to correct prompts
- Cache prompts for performance

**Prompt Architecture:**

```
prompts/
├── Classification.txt                    # Step 1: Identify type
├── Extraction-prompt-interventional.txt  # Step 2: Extract RCT data
├── Extraction-prompt-observational.txt   # Step 2: Extract cohort data
├── Extraction-prompt-synthesis.txt       # Step 2: Extract meta-analysis
├── Extraction-prompt-prediction.txt      # Step 2: Extract ML models
├── Extraction-prompt-editorials.txt      # Step 2: Extract commentary
├── Extraction-validation.txt             # Step 3: Validate accuracy
└── Extraction-correction.txt             # Step 4: Fix issues
```

**Design Decisions:**
- **Why separate files?** Version control, easier collaboration, prompt testing
- **Why type-specific prompts?** Medical terminology differs by research type
- **Why not in code?** Prompts are product logic, not implementation details

---

### 6. File Management (`PipelineFileManager`)

**Responsibilities:**
- PDF filename-based file naming
- Consistent file naming across steps
- Automatic `tmp/` directory management

**Naming Convention:**
```
{pdf_stem}-{step}.json
{pdf_stem}-{step}-{status}.json

Examples:
sample_paper-classification.json
sample_paper-extraction.json
sample_paper-validation.json
sample_paper-extraction-corrected.json
sample_paper-validation-corrected.json
```

**Design Decisions:**
- **Why PDF stem instead of DOI?** Not all papers have DOIs, consistent naming
- **Why tmp/ directory?** Clear separation of intermediate vs final outputs
- **Why JSON?** Human-readable, schema-validatable, widely supported

---

### 7. Web Interface (`app.py`)

**Platform:** Streamlit web application

**Responsibilities:**
- User-friendly PDF upload interface
- Pipeline configuration UI
- Real-time progress tracking
- Results visualization and download

**Key Features:**
- **Upload Management**:
  - Drag-and-drop PDF upload
  - Duplicate detection via file hashing
  - Previously uploaded files library
  - File size validation (10 MB limit)

- **Pipeline Control**:
  - Select which steps to run
  - View existing results per step
  - Delete and re-run individual steps
  - Configure LLM provider and page limits

- **Results Viewing**:
  - JSON viewer with syntax highlighting
  - Step-by-step result inspection
  - File metadata display

**Design Decisions:**
- **Why Streamlit?** Rapid prototyping, Python-native, easy deployment
- **Why local file storage?** Privacy, no cloud dependencies, user control
- **Why manifest system?** Track uploads, enable duplicate detection

**Usage:**
```bash
streamlit run app.py
```

---

## Data Flow

### Step 1: Classification

```
PDF → LLM (vision) → JSON
             ↓
{
  "publication_type": "interventional_trial",
  "metadata": {
    "doi": "10.1234/example",
    "title": "...",
    "authors": [...]
  }
}
```

**Purpose:** Determine which extraction schema to use in Step 2

---

### Step 2: Extraction

```
PDF + Type-Specific Schema → LLM (vision) → Structured JSON
                 ↓
{
  "schema_version": "v2.0",
  "metadata": {...},
  "study_design": {...},
  "population": {...},
  "interventions": [...],
  "outcomes": [...],
  "results": {...}
}
```

**Purpose:** Extract complete structured data with tables/figures preserved

---

### Step 3: Validation (Dual-Tier)

```
Extraction JSON → Schema Validation → Quality Score
                        ↓
                  Score ≥ 50%?
                        ↓
                       Yes
                        ↓
PDF + Extraction → LLM Validation → Validation Report
                        ↓
{
  "verification_summary": {
    "overall_status": "passed|failed",
    "completeness_score": 0.95,
    "accuracy_score": 0.88
  },
  "issues": [...]
}
```

**Purpose:** Ensure quality before expensive correction step

---

### Step 4: Correction (Conditional)

```
If validation.overall_status == "failed":

    PDF + Extraction + Validation Report → LLM → Corrected JSON
                            ↓
    Corrected JSON → Validation (repeat Step 3)
```

**Purpose:** Fix identified issues and re-validate

---

## Configuration Management (`src/config.py`)

**Environment Variables:**

```python
# LLM Provider Selection
OPENAI_API_KEY: str          # Required for OpenAI
ANTHROPIC_API_KEY: str       # Required for Claude

# Model Configuration
OPENAI_MODEL: str            # Default: gpt-5
ANTHROPIC_MODEL: str         # Default: claude-3-5-sonnet-20241022

# Token Limits
OPENAI_MAX_TOKENS: int       # Default: 4096
ANTHROPIC_MAX_TOKENS: int    # Default: 4096

# Behavior
LLM_TEMPERATURE: float       # Default: 0.0 (deterministic)
LLM_TIMEOUT: int            # Default: 120 seconds

# PDF Constraints (API limits)
MAX_PDF_PAGES: int          # Default: 100
MAX_PDF_SIZE_MB: int        # Default: 32
```

**Design Decisions:**
- **Why .env?** Secrets management, environment-specific config
- **Why defaults in code?** Fail-safe if .env missing
- **Why temperature=0.0?** Reproducible extractions for research

---

## Error Handling Strategy

### Exception Hierarchy

```python
LLMError                    # Base for all LLM issues
├── APIError               # Provider API failures
├── TimeoutError           # Request timeout
└── ValidationError        # Response validation

SchemaLoadError            # Schema file issues
PromptLoadError            # Prompt file issues
ValidationError            # Data validation issues
```

### Error Recovery Strategy

| Error Type | Recovery Strategy | User Impact |
|-----------|-------------------|-------------|
| Schema validation fails | Skip LLM validation, go to correction | Faster failure, lower cost |
| LLM API timeout | Retry once with exponential backoff | Slight delay |
| Invalid JSON response | Re-prompt with error message | One retry |
| Missing schema file | Fail fast with clear error | Cannot proceed |
| PDF too large | Fail fast with size limit error | User must split PDF |

---

## Performance Considerations

### Token Usage Optimization

**Per 20-page Paper:**
- Classification: ~40K tokens ($0.20)
- Extraction: ~40K tokens ($0.20)
- Validation: ~40K tokens ($0.20)
- Correction: ~40K tokens ($0.20)

**Total:** ~160K tokens, $0.80-$3.00 per paper (provider dependent)

### Caching Strategy

1. **Schema Caching:** Load once per pipeline run
2. **Prompt Caching:** Load once per pipeline run
3. **No LLM Response Caching:** Medical data too sensitive

### Breakpoint System for Development

```python
BREAKPOINT_AFTER_STEP = "extraction"  # Stop after any step for testing
```

**Benefits:**
- Test individual steps without full pipeline
- Save LLM costs during development
- Faster iteration cycles

---

## Security Architecture

### Data Handling
- **No data persistence:** All data in `tmp/` (user responsibility to move)
- **No cloud storage:** Entirely local file system
- **API keys:** Environment variables only, never committed

### PDF Security
- **No server upload:** PDFs sent directly to LLM providers (OpenAI/Anthropic)
- **Size limits enforced:** Prevent memory exhaustion attacks
- **No arbitrary code execution:** PDF parsing done by LLM providers

---

## Extensibility Points

### Adding a New LLM Provider

1. Create new class inheriting from `BaseLLMProvider`
2. Implement `generate_json_with_pdf()` method
3. Register in `get_llm_provider()` factory function
4. Add environment variables to `src/config.py`

### Adding a New Publication Type

1. Create extraction prompt: `prompts/Extraction-prompt-{type}.txt`
2. Create schema: `schemas/{type}.schema.json`
3. Bundle schema: `schemas/{type}_bundled.json`
4. Update `SCHEMA_MAPPING` in `src/schemas_loader.py`
5. Update `prompt_mapping` in `src/prompts.py`
6. Add to `classification.schema.json` enum

### Adding a New Validation Check

1. Extend `validate_extraction_quality()` in `src/validation.py`
2. Update quality score calculation weights
3. Document in `VALIDATION_STRATEGY.md`

---

## Testing Architecture

### Test Pyramid

```
         ┌─────────────┐
         │   E2E       │  ← Few (expensive, slow)
         │   Tests     │
         └─────────────┘
       ┌─────────────────┐
       │  Integration    │  ← Some (medium cost)
       │  Tests          │
       └─────────────────┘
     ┌───────────────────────┐
     │   Unit Tests          │  ← Many (cheap, fast)
     └───────────────────────┘
```

### Mocking Strategy

- **LLM calls:** Mock with fixtures for fast unit tests
- **File I/O:** Use temporary directories
- **Schemas:** Use simplified test schemas

---

## Dependencies

### Core Dependencies
- `openai`: OpenAI API client
- `anthropic`: Claude API client
- `jsonschema`: Schema validation
- `rich`: CLI UI/UX
- `python-dotenv`: Environment management

### Development Dependencies
- `pytest`: Testing framework
- `black`: Code formatting
- `ruff`: Linting
- `mypy`: Type checking

---

## Future Architecture Considerations

### Potential Improvements

1. **Batch Processing:** Process multiple PDFs in parallel
2. **Result Caching:** Cache LLM responses (with consent)
3. **Streaming:** Stream large PDFs in chunks
4. **Web Interface:** Streamlit/Gradio UI
5. **Database Storage:** Store extractions in structured DB
6. **API Server:** FastAPI wrapper for cloud deployment
7. **Webhook Support:** Async processing with callbacks

### Scalability Constraints

- **Current:** Single-threaded, local processing
- **Bottleneck:** LLM API rate limits (not our code)
- **Max throughput:** ~50-100 papers/hour (provider dependent)

---

## Related Documentation

- `VALIDATION_STRATEGY.md` - Detailed validation design
- `README.md` - User-facing documentation
- `src/README.md` - Module-level documentation
- `prompts/README.md` - Prompt engineering guidelines
- `schemas/readme.md` - Schema design principles
