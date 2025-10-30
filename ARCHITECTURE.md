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

## 🔗 Quick Navigation

| Section | Description |
|---------|-------------|
| [High-Level Architecture](#high-level-architecture) | System overview and component diagram |
| [Component Architecture](#component-architecture) | Detailed module descriptions |
| [Data Flow](#data-flow) | Four-step pipeline data flow |
| [Medical Standards & Compliance](#medical-standards--compliance) | International reporting standards (CONSORT, PRISMA, TRIPOD, STROBE) |
| [Configuration Management](#configuration-management) | Environment variables and settings |
| [Error Handling Strategy](#error-handling-strategy) | Exception hierarchy and recovery |
| [Performance Considerations](#performance-considerations) | Token optimization and caching |
| [Security Architecture](#security-architecture) | Data handling and PDF security |
| [Extensibility Points](#extensibility-points) | Adding providers, types, validation |
| [Testing Architecture](#testing-architecture) | Test pyramid and mocking strategy |

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

### 1. Pipeline Orchestrator (`src/pipeline/orchestrator.py`)

**Responsibilities:**
- Coordinate 3-step extraction workflow (with iterative correction)
- Provide modular step execution API
- Handle breakpoints for testing
- Manage intermediate file I/O
- Display user-friendly progress

**Key Functions:**
- `run_single_step()`: Execute one pipeline step with dependency validation
- `run_four_step_pipeline()`: Backwards-compatible wrapper for CLI/batch usage
- `run_validation_with_correction()`: **NEW** - Iterative validation-correction loop
- `_run_classification_step()`: Private classification logic
- `_run_extraction_step()`: Private extraction logic
- `_run_validation_step()`: Private validation logic
- `_run_correction_step()`: Private correction logic
- `is_quality_sufficient()`: Check if validation meets quality thresholds
- `_select_best_iteration()`: Select best result when max iterations reached
- `_detect_quality_degradation()`: Early stopping for degrading quality

**Design Decisions:**
- **Why 3 steps?** Default pipeline: classify → extract → validate_correct (iterative)
- **Why iterative correction?** Progressive improvement until quality thresholds met
- **Why keep 4-step option?** Backward compatibility for CLI and existing workflows
- **Why modular functions?** Enables step-by-step execution with UI updates (Streamlit)
- **Why quality thresholds?** Configurable stopping criteria (completeness, accuracy, schema compliance)
- **Why early stopping?** Prevent wasted LLM calls when corrections degrade quality
- **Why best iteration selection?** Ensure we always return highest quality result
- **Why public API?** Single source of truth used by both CLI and web interface
- **Why breakpoints?** Enable step-by-step testing without full pipeline runs
- **Why PDF filename-based naming?** Consistent file tracking across pipeline stages, works without DOI

---

#### Dual-Mode Execution Architecture

**Problem:** Streamlit and CLI have different execution models:
- **CLI:** Runs all 4 steps in sequence, displays final results
- **Streamlit:** Needs real-time UI updates between steps

**Solution:** Modular architecture with two execution modes:

##### Mode 1: Step-by-Step Execution (Streamlit)

**Implementation:** `src/streamlit_app/screens/execution.py`

```python
# Execute one step at a time with UI refresh between steps
current_step_index = st.session_state.execution["current_step_index"]
steps_to_run = ["classification", "extraction", "validation", "correction"]

current_step = steps_to_run[current_step_index]

# Run single step
step_result = run_single_step(
    step_name=current_step,
    pdf_path=pdf_path,
    max_pages=max_pages,
    llm_provider=llm_provider,
    file_manager=file_manager,
    progress_callback=callback,
    previous_results=st.session_state.execution["results"],
)

# Store result and increment index
st.session_state.execution["results"][current_step] = step_result
st.session_state.execution["current_step_index"] += 1

# Rerun to refresh UI and execute next step
st.rerun()
```

**Benefits:**
- ✅ UI refreshes after each step
- ✅ User sees real-time progress (Classification → Extraction → Validation → Correction)
- ✅ Step status indicators update immediately
- ✅ Works within Streamlit's top-to-bottom execution model

**State Tracking:**
- `current_step_index`: Which step to execute next (0-3)
- `results`: Dict accumulating results from completed steps
- `step_status`: Per-step status (pending/running/success/failed)

##### Mode 2: Batch Execution (CLI)

**Implementation:** `src/pipeline/orchestrator.py`

```python
def run_four_step_pipeline(...) -> dict[str, Any]:
    """Execute all 4 steps in sequence (backwards compatible)."""
    results = {}
    file_manager = PipelineFileManager(pdf_path)

    all_steps = ["classification", "extraction", "validation", "correction"]

    for step_name in all_steps:
        # Run single step using same API as Streamlit
        step_result = run_single_step(
            step_name=step_name,
            pdf_path=pdf_path,
            max_pages=max_pages,
            llm_provider=llm_provider,
            file_manager=file_manager,
            progress_callback=progress_callback,
            previous_results=results,
        )

        # Store result and continue to next step
        results[step_name] = step_result

        # Check for breakpoint or early exit
        if check_breakpoint(...) or publication_type == "overig":
            return results

    return results
```

**Benefits:**
- ✅ Single source of truth - both modes use `run_single_step()`
- ✅ No code duplication between CLI and web interface
- ✅ Backwards compatible with existing CLI usage
- ✅ Preserves all existing functionality (breakpoints, filtering, error handling)

**Comparison:**

| Aspect | CLI Mode | Streamlit Mode |
|--------|----------|----------------|
| **Execution** | All steps in one script run | One step per script run |
| **UI Updates** | Only at completion | After each step |
| **Rerun Behavior** | N/A | `st.rerun()` after each step |
| **State Management** | Local variables | Session state |
| **Use Case** | Batch processing, testing | Interactive user experience |
| **Code Reuse** | ✅ Both use `run_single_step()` | ✅ Both use `run_single_step()` |

**Architecture Benefits:**
1. **DRY Principle:** Single implementation of step execution logic
2. **Testability:** Test `run_single_step()` once, both modes benefit
3. **Maintainability:** Bug fixes apply to both CLI and Streamlit
4. **Flexibility:** Easy to add new execution modes (API server, batch queue, etc.)

---

#### Iterative Validation-Correction Loop

**Problem:** Single correction pass may not achieve sufficient quality.

**Solution:** Iterative loop with quality assessment and early stopping.

**Workflow:**
1. Validate extraction (schema + LLM)
2. Check quality against thresholds (completeness ≥0.90, accuracy ≥0.95, schema ≥0.95, critical_issues=0)
3. If insufficient quality and iterations < max:
   - Run correction with validation feedback
   - Validate corrected extraction
   - Repeat from step 2
4. Early stopping if quality degrades for 2 consecutive iterations
5. Select best iteration based on composite quality score

**Quality Assessment:**
```python
# Composite quality score (used for ranking)
overall_quality = (
    completeness_score * 0.40 +      # Coverage of PDF data
    accuracy_score * 0.40 +           # Correctness (no hallucinations)
    schema_compliance_score * 0.20    # Structural correctness
)
```

**Final Status Codes:**
- `passed`: Quality thresholds met
- `max_iterations_reached`: Max iterations reached, using best result
- `early_stopped_degradation`: Stopped due to quality degradation
- `failed_schema_validation`: Schema validation failed (<50% quality)
- `failed_llm_error`: LLM API error after 3 retries
- `failed_invalid_json`: Correction produced invalid JSON
- `failed_unexpected_error`: Unexpected error occurred

**File Naming Convention:**
```
tmp/
├── paper-extraction.json                # Initial extraction (iter 0)
├── paper-validation.json                # Initial validation (iter 0)
├── paper-extraction-corrected1.json     # Corrected extraction (iter 1)
├── paper-validation-corrected1.json     # Validation of corrected (iter 1)
├── paper-extraction-corrected2.json     # Second correction (iter 2)
└── paper-validation-corrected2.json     # Final validation (iter 2)
```

**Error Handling:**
- LLM failures: 3 retries with exponential backoff (1s, 2s, 4s)
- Schema failures (<50% quality): Immediate stop, no correction
- Invalid JSON: Return best previous iteration
- Unexpected errors: Graceful degradation, return best iteration so far

---

### 2. LLM Provider Layer (`src/llm/`)

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

## Medical Standards & Compliance

### International Reporting Standards

PDFtoPodcast schemas and prompts are designed to comply with major international reporting guidelines:

#### CONSORT 2010 (Interventional Trials)

**Coverage in Schema:**
- Complete 25-item checklist support
- Randomization sequence generation
- Allocation concealment mechanism
- Blinding implementation
- Sample size calculation
- CONSORT flow diagram structure
- Protocol deviations tracking

**Key Features:**
```json
{
  "consort_reporting": {
    "version": "CONSORT 2010",
    "claimed": true,
    "items": [
      {"item_id": "1a", "reported": "yes", "location": "Page 3"},
      {"item_id": "6a", "reported": "partial", "location": "Methods"}
    ]
  }
}
```

#### PRISMA 2020 (Systematic Reviews)

**Coverage in Schema:**
- 27-item PRISMA checklist
- PRISMA flow diagram (identification, screening, eligibility, included)
- Search strategy documentation
- Study selection criteria
- Risk of bias assessment
- Certainty of evidence (GRADE)

**PRISMA Flow Structure:**
```json
{
  "prisma_flow": {
    "identification": {
      "database_results": 1543,
      "register_results": 23,
      "other_sources": 5
    },
    "screening": {"records_screened": 1571, "excluded": 1432},
    "eligibility": {"full_text_assessed": 139, "excluded": 98},
    "included": {"studies_included": 41}
  }
}
```

#### TRIPOD (Prediction Models)

**Coverage in Schema:**
- 22-item TRIPOD checklist
- TRIPOD-AI extensions for ML/AI models
- Model development documentation
- Internal/external validation
- Performance metrics (discrimination, calibration)
- Clinical utility assessment

**Key Sections:**
- Predictor definitions with measurement methods
- Missing data handling
- Model specification (equation, algorithm)
- C-statistic, AUC-ROC with confidence intervals
- Calibration plots and Brier scores
- Decision curve analysis

#### STROBE (Observational Studies)

**Coverage in Schema:**
- 22-item STROBE checklist
- Study design specification
- Setting and participants
- Variables and data sources
- Bias assessment
- Quantitative variables handling

**Extensions:**
- STROBE-ME (Molecular Epidemiology)
- STROBE-RDS (Respondent-Driven Sampling)
- STROBE-Vet (Veterinary research)

---

### Quality Assessment & Risk of Bias Tools

#### RoB 2.0 (Cochrane Risk of Bias for RCTs)

**Five Domains Supported:**
1. Randomization process
2. Deviations from intended interventions
3. Missing outcome data
4. Measurement of the outcome
5. Selection of reported result

**Schema Structure:**
```json
{
  "risk_of_bias": {
    "tool": "RoB_2.0",
    "domains": [
      {
        "domain": "randomization_process",
        "judgment": "low|some_concerns|high",
        "rationale": "Adequate sequence generation and allocation concealment"
      }
    ],
    "overall": "low"
  }
}
```

#### ROBINS-I (Risk of Bias for Non-Randomized Studies)

**Seven Domains:**
1. Confounding
2. Selection of participants
3. Classification of interventions
4. Deviations from intended interventions
5. Missing data
6. Measurement of outcomes
7. Selection of reported result

**Advanced Features:**
- Pre-intervention confounding assessment
- Post-intervention confounding (time-varying)
- Target trial framework alignment

#### PROBAST (Prediction Model Risk of Bias)

**Four Domains:**
1. Participants
2. Predictors
3. Outcome
4. Analysis

**Applicability Assessment:**
- Target population representativeness
- Predictor definitions consistency
- Outcome definitions appropriateness

#### AMSTAR-2 (Systematic Review Quality)

**16 Items with Critical Domains:**
- Protocol registration (#2)
- Comprehensive search (#4)
- Study selection justification (#7)
- Risk of bias assessment (#9)
- Appropriate meta-analysis methods (#11)
- Publication bias assessment (#15)

**Rating Scale:**
- High quality
- Moderate quality
- Low quality
- Critically low quality

---

### Advanced Methodological Support

#### Target Trial Emulation (Observational Studies)

**Framework Support:**
```json
{
  "study_design": {
    "target_trial_emulation": true,
    "new_user_design": true,
    "prevalent_user_bias_risk": "low",
    "grace_period_days": 30,
    "immortal_time_handling": "time-varying_exposure"
  }
}
```

**Key Concepts:**
- New user design (vs prevalent user)
- Grace periods for exposure ascertainment
- Immortal time bias mitigation
- Time-zero alignment
- Active comparator selection

#### Causal Inference Methods

**Supported Approaches:**
- Propensity score matching/weighting (IPTW, SMR)
- Instrumental variable analysis
- Regression discontinuity designs
- Difference-in-differences
- Marginal structural models (MSMs)
- G-methods (g-formula, g-estimation)

**Schema Example:**
```json
{
  "propensity_score": {
    "method": "IPTW",
    "matching_ratio": 1.0,
    "caliper": 0.2,
    "variables": ["age", "sex", "baseline_severity"],
    "balance_assessment": "standardized_differences",
    "ps_overlap_ok": true
  }
}
```

#### Competing Risks Analysis

**Methods Supported:**
- Cause-specific hazards
- Subdistribution hazards (Fine-Gray)
- Cumulative incidence functions

**Schema Structure:**
```json
{
  "outcomes": [
    {
      "outcome_id": "mortality",
      "event_competing_risks_present": true,
      "competing_events": ["cardiovascular_death", "non_cardiovascular_death"]
    }
  ],
  "competing_risks_method": "Fine-Gray"
}
```

---

### Data Source Prioritization Strategy

#### Main Text Priority Over Abstract

**Rationale:**
- Abstracts have word limits (~250-350 words)
- Critical details often only in full text
- Tables/figures not summarized in abstracts
- Complete methodology in Methods sections

**Extraction Priority Order:**

1. **Methods Section** (Highest Priority)
   - Complete study design
   - Inclusion/exclusion criteria
   - Sample size calculations
   - Statistical analysis plans
   - Randomization procedures

2. **Results Section**
   - Complete numerical data
   - Tables with all outcomes
   - CONSORT/PRISMA flow diagrams
   - Adverse events tables
   - Sensitivity analyses

3. **Tables and Figures**
   - Baseline characteristics (complete)
   - Primary outcome results with CIs
   - Secondary outcomes
   - Subgroup analyses
   - Forest plots (meta-analyses)

4. **Discussion Section**
   - Limitations
   - Clinical implications
   - Generalizability
   - Comparison with other studies

5. **Abstract** (Lowest Priority)
   - Use for verification only
   - Cross-check key numbers
   - Identify discrepancies

**Implementation in Prompts:**
All extraction prompts (v2.3+) explicitly instruct:
> "Prioritize Methods/Results sections over Abstract. Only use Abstract to verify or when main text is unclear."

---

### Document Processing & PDF Strategy

#### Direct PDF Upload Approach

**Architecture Decision:**
Instead of text extraction (PyMuPDF, pdfplumber), upload PDFs directly to vision-capable LLMs.

**Trade-offs:**

| Aspect | Text Extraction | PDF Upload (Current) |
|--------|----------------|----------------------|
| **Token Cost** | ~500/page | ~1,500-3,000/page |
| **Tables** | Often mangled | Perfect preservation |
| **Figures** | Lost | Analyzed visually |
| **Formatting** | Lost | Preserved |
| **Use Case** | Simple docs | Medical research |

**Cost Analysis:**
- 3-6x more expensive per page
- BUT: 100% data fidelity for medical research
- Critical for clinical trials (tables = results)

#### PDF Processing Limits

**API Constraints (OpenAI & Claude):**
- Maximum 100 pages per PDF
- Maximum 32 MB file size
- Base64 encoding required
- ~2MB increase post-encoding

**Handling Large Documents:**
```python
# Automatic validation
if pdf_size_mb > 32:
    raise ValueError("PDF exceeds 32MB limit")
if page_count > 100:
    raise ValueError("PDF exceeds 100 pages")
```

**Workarounds:**
- Use `--max-pages` flag to process subset
- Split large PDFs manually
- Prioritize key sections (Methods, Results)

#### Source Reference Tracking

**SourceRef Structure:**
Every extracted field includes provenance:

```json
{
  "n_randomised": {
    "value": 342,
    "source": {
      "page": 5,
      "anchor": "CONSORT Flow Diagram, Figure 1",
      "bbox": {"x": 120, "y": 450, "width": 300, "height": 18}
    }
  }
}
```

**Components:**
- `page`: PDF page number (1-indexed)
- `anchor`: Human-readable location description
- `bbox`: Bounding box coordinates (optional, for precise location)

**Benefits:**
- Verify extraction accuracy
- Audit trail for medical data
- Enable manual review workflow
- Support disagreement resolution

---

### Evidence-Locked Extraction

**Principle:** Extract ONLY from PDF content, no external knowledge.

**Implementation:**
All prompts include explicit instructions:
> "Do NOT use external medical knowledge. Extract only what is explicitly stated in the PDF."

**Why Important for Medical Research:**
- Ensure reproducibility
- Prevent hallucinations
- Enable systematic reviews (no cherry-picking)
- Support regulatory submissions (FDA/EMA)

**Verification:**
The validation prompt cross-checks extracted data against PDF to detect:
- Hallucinated numbers
- External knowledge injection
- Misinterpretations
- Out-of-scope inferences

---

### International Trial Registry Support

**Global Coverage:**

| Registry | Region | Identifier Format | Example |
|----------|--------|-------------------|---------|
| ClinicalTrials.gov | USA | NCT + 8 digits | NCT02345678 |
| EudraCT | EU (legacy) | YYYY-NNNNNN-NN | 2019-123456-42 |
| EU-CTR | EU (new) | EUCTR + YYYY-NNNNNN-NN | EUCTR2019-123456-42 |
| CTIS | EU (latest) | CT + numeric | CT12345678 |
| UMIN-CTR | Japan | UMIN + 9 digits | UMIN000012345 |
| JPRN | Japan | jRCT + numeric | jRCT1234567890 |
| PACTR | Africa | PACTR + YMN | PACTR202301123456789 |
| IRCT | Iran | IRCT + YMN | IRCT20230112123456N1 |
| ANZCTR | Australia/NZ | ACTRN + N | ACTRN12345678901234 |

**Schema Support:**
```json
{
  "registration": {
    "registry": "UMIN-CTR",
    "identifier": "UMIN000012345",
    "url": "https://center.umin.ac.jp/...",
    "registration_date": "2023-01-15"
  }
}
```

---

### Anesthesiology Domain Specialization

**Classification Prompt Rules:**
The classification prompt includes domain-specific logic:

- Perioperative care studies → `interventional_trial`
- Pain management cohorts → `observational_analytic`
- Anesthesia technique comparisons → `interventional_trial`
- Outcome prediction models → `prediction_prognosis`
- Practice guideline commentaries → `editorials_opinion`
- Case series of complications → `overig`

**Domain-Specific Fields:**
```json
{
  "anesthesia_specific": {
    "asa_physical_status": ["I", "II", "III"],
    "procedures": ["general_anesthesia", "regional_anesthesia"],
    "outcomes": {
      "ponv": {"measured": true},
      "acute_pain": {"measured": true, "scale": "NRS"}
    }
  }
}
```

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
