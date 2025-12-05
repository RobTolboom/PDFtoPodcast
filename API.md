# API Reference

**Medical Literature Extraction Pipeline**

This document provides a comprehensive reference for all public APIs in the medical literature extraction pipeline. For implementation details and architecture, see [`ARCHITECTURE.md`](ARCHITECTURE.md). For feature specifications, see [`features/`](features/).

---

## Table of Contents

1. [Pipeline Orchestration](#1-pipeline-orchestration)
2. [File Management](#2-file-management)
3. [Validation](#3-validation)
4. [Schema Handling](#4-schema-handling)
5. [Prompt Handling](#5-prompt-handling)
6. [LLM Integration](#6-llm-integration)
7. [Utilities](#7-utilities)
8. [CLI Entry Point](#8-cli-entry-point)

---

## 1. Pipeline Orchestration

**Module**: `src/pipeline/orchestrator.py`

### Main Pipeline Functions

#### `run_four_step_pipeline()`

Execute complete 4-step pipeline (classification, extraction, validation/correction, appraisal).

**Signature:**
```python
def run_four_step_pipeline(
    pdf_path: Path,
    max_pages: int | None = None,
    llm_provider: str = "openai",
    breakpoint_after_step: str | None = None,
    have_llm_support: bool = True,
    steps_to_run: list[str] | None = None,
    progress_callback: Callable[[str, str, dict], None] | None = None
) -> dict[str, Any]
```

**Parameters:**
- `pdf_path`: Path to PDF file to process
- `max_pages`: Limit pages processed (default: all pages)
- `llm_provider`: LLM provider to use (`"openai"` or `"claude"`)
- `breakpoint_after_step`: Optional step name to stop after (for testing)
- `have_llm_support`: Whether LLM is available (for testing with mocks)
- `steps_to_run`: Optional list to filter which steps execute
- `progress_callback`: Optional callback for UI updates (`callback(step_name, status, data)`)

**Returns:**
Dictionary with keys for each completed step:
- `classification_result`: Publication type and metadata
- `extraction_result`: Structured data extraction
- `validation_correction_result`: Best extraction after validation/correction
- `appraisal_result`: Critical appraisal (risk of bias, GRADE ratings)

**Raises:**
- `FileNotFoundError`: If PDF file not found
- `ValidationError`: If step dependencies not met
- `LLMProviderError`: If LLM calls fail

**Example:**
```python
from pathlib import Path
from src.pipeline.orchestrator import run_four_step_pipeline

results = run_four_step_pipeline(
    pdf_path=Path("paper.pdf"),
    llm_provider="openai",
    max_pages=None  # Process all pages
)

print(results['classification_result']['publication_type'])  # "interventional_trial"
print(results['appraisal_result']['best_appraisal']['risk_of_bias']['overall'])  # "Low risk"
```

---

#### `run_single_step()`

Execute individual pipeline step with dependency validation.

**Signature:**
```python
def run_single_step(
    step_name: str,
    pdf_path: Path,
    max_pages: int | None,
    llm_provider: str,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None = None,
    previous_results: dict[str, Any] | None = None,
    max_correction_iterations: int | None = None,
    quality_thresholds: dict[str, Any] | None = None,
    enable_iterative_correction: bool = True
) -> dict[str, Any]
```

**Parameters:**
- `step_name`: Step to execute (`"classification"`, `"extraction"`, `"validation_correction"`, `"appraisal"`)
- `pdf_path`: Path to PDF file
- `max_pages`: Page limit (None = all)
- `llm_provider`: LLM provider name
- `file_manager`: File manager instance for loading/saving
- `progress_callback`: Optional callback for progress updates
- `previous_results`: Results from previous steps (auto-loaded from disk if None)
- `max_correction_iterations`: Max iterations for validation_correction or appraisal (default: 3)
- `quality_thresholds`: Custom quality thresholds (dict with threshold names as keys)
- `enable_iterative_correction`: Enable iterative correction loops (default: True)

**Returns:**
Step-specific result dictionary

**Raises:**
- `ValidationError`: If dependencies not met (e.g., extraction requires classification)
- `UnsupportedPublicationType`: If publication type not supported for step
- `LLMProviderError`: If LLM calls fail

**Example:**
```python
from src.pipeline.file_manager import PipelineFileManager

file_mgr = PipelineFileManager(pdf_path=Path("paper.pdf"))

# Run classification only
classification = run_single_step(
    step_name="classification",
    pdf_path=Path("paper.pdf"),
    max_pages=None,
    llm_provider="openai",
    file_manager=file_mgr
)

# Run appraisal (requires classification + extraction to exist)
appraisal = run_single_step(
    step_name="appraisal",
    pdf_path=Path("paper.pdf"),
    max_pages=None,
    llm_provider="openai",
    file_manager=file_mgr,
    max_correction_iterations=3,
    quality_thresholds={
        'logical_consistency_score': 0.90,
        'completeness_score': 0.85
    }
)
```

---

### Validation & Correction Functions

#### `run_validation_with_correction()`

Iterative validation loop with automatic correction until quality sufficient.

**Signature:**
```python
def run_validation_with_correction(
    pdf_path: Path,
    extraction_result: dict,
    classification_result: dict,
    llm_provider: str,
    file_manager: PipelineFileManager,
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    progress_callback: Callable | None = None
) -> dict
```

**Parameters:**
- `pdf_path`: Path to PDF file (for re-extraction context)
- `extraction_result`: Initial extraction JSON
- `classification_result`: Classification result (for publication type)
- `llm_provider`: LLM provider name
- `file_manager`: File manager for saving iterations
- `max_iterations`: Max correction attempts (default: 3)
- `quality_thresholds`: Custom thresholds (default: `completeness_score` ≥0.90, `accuracy_score` ≥0.95, `schema_compliance_score` ≥0.95)
- `progress_callback`: Optional callback for UI updates

**Returns:**
Dictionary with keys:
- `best_extraction`: Highest-quality extraction JSON
- `best_validation`: Validation report of best extraction
- `iterations`: List of all iterations with metrics
- `final_status`: `"passed"` | `"max_iterations_reached"` | `"failed"`
- `iteration_count`: Total iterations performed
- `improvement_trajectory`: List of quality scores per iteration

**Example:**
```python
result = run_validation_with_correction(
    pdf_path=Path("paper.pdf"),
    extraction_result=initial_extraction,
    classification_result=classification,
    llm_provider="openai",
    file_manager=file_mgr,
    max_iterations=3
)

if result['final_status'] == 'passed':
    best_extraction = result['best_extraction']
    quality_score = result['best_validation']['quality_score']
    print(f"Quality achieved: {quality_score:.2f}")
```

**See also:** [`features/iterative-validation-correction.md`](features/iterative-validation-correction.md)

---

### Appraisal Functions

#### `run_appraisal_with_correction()`

Critical appraisal with iterative validation/correction (risk of bias, GRADE assessment).

**Signature:**
```python
def run_appraisal_with_correction(
    extraction_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm_provider: str,
    file_manager: PipelineFileManager,
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    progress_callback: Callable[[str, str, dict], None] | None = None
) -> dict[str, Any]
```

**Parameters:**
- `extraction_result`: Validated extraction JSON (input for appraisal)
- `classification_result`: Classification result (for publication_type routing)
- `llm_provider`: LLM provider name
- `file_manager`: File manager for saving appraisal iterations
- `max_iterations`: Max correction attempts (default: 3)
- `quality_thresholds`: Custom thresholds (default: `logical_consistency_score` ≥0.90, `completeness_score` ≥0.85, `evidence_support_score` ≥0.90, `schema_compliance_score` ≥0.95)
- `progress_callback`: Optional callback for UI updates

**Returns:**
Dictionary with keys:
- `best_appraisal`: Best appraisal result (risk of bias, GRADE ratings, applicability)
- `best_validation`: Validation of best appraisal
- `iterations`: All iteration history with metrics
- `final_status`: `"passed"` | `"max_iterations_reached"` | `"failed"`
- `iteration_count`: Total iterations performed
- `improvement_trajectory`: Quality scores per iteration

**Study Type Routing:**
Routes to appropriate appraisal tool based on `publication_type`:
- `interventional_trial` → RoB 2 (Cochrane Risk of Bias tool)
- `observational_analytic` → ROBINS-I (Risk Of Bias In Non-randomized Studies)
- `evidence_synthesis` → AMSTAR 2 + ROBIS (systematic review quality)
- `prediction_prognosis` → PROBAST (Prediction model Risk Of Bias ASsessment Tool)
- `diagnostic` → PROBAST/QUADAS (shares prediction prompt)
- `editorials_opinion` → Argument quality assessment

**Example:**
```python
appraisal_result = run_appraisal_with_correction(
    extraction_result=validated_extraction,
    classification_result=classification,
    llm_provider="openai",
    file_manager=file_mgr,
    max_iterations=3
)

if appraisal_result['final_status'] == 'passed':
    appraisal = appraisal_result['best_appraisal']
    print(f"Tool: {appraisal['tool']['name']}")  # "RoB 2"
    print(f"Risk of bias: {appraisal['risk_of_bias']['overall']}")  # "Low risk"

    for outcome in appraisal['grade_per_outcome']:
        print(f"{outcome['outcome_name']}: {outcome['certainty']}")  # "High"
```

**See also:** [`features/appraisal.md`](features/appraisal.md)

---

### Report Generation Functions

#### `run_report_with_correction()`

Generate structured report with iterative validation/correction loop.

**Signature:**
```python
def run_report_with_correction(
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm: BaseLLMProvider,
    file_manager: PipelineFileManager,
    language: str = "en",
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    progress_callback: Callable[[str, str, dict], None] | None = None,
) -> dict[str, Any]
```

**Parameters:**
- `extraction_result`: Validated extraction JSON
- `appraisal_result`: Validated appraisal JSON
- `classification_result`: Classification result (for publication_type + metadata)
- `llm`: Instantiated LLM provider
- `file_manager`: File manager for saving report iterations
- `language`: Report language (`"en"`)
- `max_iterations`: Max correction attempts (default: 3)
- `quality_thresholds`: Custom thresholds (default: `accuracy_score` ≥0.95, `completeness_score` ≥0.85, `cross_reference_consistency_score` ≥0.90, `data_consistency_score` ≥0.90, `schema_compliance_score` ≥0.95)
- `progress_callback`: Optional callback for UI updates

**Returns:**
Dictionary with keys:
- `best_report`: Best report JSON (block-based structure)
- `best_validation`: Validation of best report
- `iterations`: All iteration history with metrics
- `final_status`: `"passed"` | `"max_iterations_reached"` | `"blocked"`
- `iteration_count`: Total iterations performed
- `improvement_trajectory`: Quality scores per iteration

**Dependency Gating:**
Blocks if upstream quality insufficient:
- Extraction quality < 0.70 → blocked
- Appraisal missing Risk of Bias → blocked
- Appraisal validation failed → blocked

**Example:**
```python
from src.pipeline.orchestrator import run_report_with_correction
from src.llm import get_llm_provider

llm = get_llm_provider("openai")
report_result = run_report_with_correction(
    extraction_result=extraction,
    appraisal_result=appraisal,
    classification_result=classification,
    llm=llm,
    file_manager=file_mgr,
    language="en",
    max_iterations=3
)

if report_result['final_status'] == 'passed':
    report = report_result['best_report']
    print(f"Sections: {len(report['sections'])}")
    print(f"Quality: {report_result['best_validation']['validation_summary']['quality_score']:.2f}")
```

**See also:** [`features/report-generation.md`](features/report-generation.md), [`docs/report.md`](docs/report.md)

---

#### `run_report_generation()`

Single-pass report generation (no correction loop).

**Signature:**
```python
def run_report_generation(
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm: BaseLLMProvider,
    report_schema: dict[str, Any],
    language: str = "en",
) -> dict[str, Any]
```

**Parameters:**
- `extraction_result`: Validated extraction JSON
- `appraisal_result`: Validated appraisal JSON
- `classification_result`: Classification result
- `llm`: Instantiated LLM provider
- `report_schema`: Report JSON schema
- `language`: Report language (`"en"`)

**Returns:**
Report JSON conforming to `report.schema.json`

**Example:**
```python
from src.pipeline.orchestrator import run_report_generation
from src.schemas_loader import load_schema

report_schema = load_schema("report")
report = run_report_generation(
    extraction_result=extraction,
    appraisal_result=appraisal,
    classification_result=classification,
    llm=llm,
    report_schema=report_schema,
    language="en"
)
```

---

#### `is_report_quality_sufficient()`

Check if report validation meets quality thresholds.

**Signature:**
```python
def is_report_quality_sufficient(
    validation_result: dict | None,
    thresholds: dict | None = None
) -> bool
```

**Parameters:**
- `validation_result`: Validation report from report validation
- `thresholds`: Custom thresholds (default: see `run_report_with_correction()`)

**Returns:**
`True` if all thresholds met and `critical_issues == 0`, `False` otherwise

**Quality Metrics:**
- **Accuracy** (35%): Data matches extraction/appraisal exactly
- **Completeness** (30%): All required sections present
- **Cross-reference consistency** (10%): Table/figure refs resolve
- **Data consistency** (10%): Numbers consistent across sections
- **Schema compliance** (15%): Valid JSON structure

---

#### `run_appraisal_single_pass()`

Single appraisal + validation cycle without iterative correction.

**Signature:**
```python
def run_appraisal_single_pass(
    extraction_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm_provider: str,
    file_manager: PipelineFileManager,
    quality_thresholds: dict | None = None,
    progress_callback: Callable[[str, str, dict], None] | None = None
) -> dict[str, Any]
```

**Parameters:**
Same as `run_appraisal_with_correction()` except no `max_iterations`

**Returns:**
Dictionary with:
- `best_appraisal`: Single appraisal result
- `best_validation`: Validation of appraisal
- `iterations`: Single iteration (for consistency)
- `final_status`: `"passed"` | `"failed"`
- `iteration_count`: Always 1

**Use Case:**
Faster option when iterative correction not needed (e.g., high-quality extractions, time-sensitive workflows).

**Example:**
```python
# CLI usage: --appraisal-single-pass
appraisal = run_appraisal_single_pass(
    extraction_result=extraction,
    classification_result=classification,
    llm_provider="openai",
    file_manager=file_mgr
)
```

---

### Quality Assessment Functions

#### `is_quality_sufficient()`

Check if extraction validation meets quality thresholds.

**Signature:**
```python
def is_quality_sufficient(
    validation_result: dict | None,
    thresholds: dict | None = None
) -> bool
```

**Parameters:**
- `validation_result`: Validation report from extraction validation
- `thresholds`: Custom thresholds (default: `completeness_score` ≥0.90, `accuracy_score` ≥0.95, `schema_compliance_score` ≥0.95, `critical_issues` =0)

**Returns:**
`True` if all thresholds met, `False` otherwise

**Example:**
```python
validation = validate_extraction(...)
if is_quality_sufficient(validation):
    print("Quality acceptable - no correction needed")
else:
    print("Quality insufficient - running correction")
```

---

#### `is_appraisal_quality_sufficient()`

Check if appraisal validation meets quality thresholds.

**Signature:**
```python
def is_appraisal_quality_sufficient(
    validation_result: dict | None,
    thresholds: dict | None = None
) -> bool
```

**Parameters:**
- `validation_result`: Validation report from appraisal validation
- `thresholds`: Custom thresholds (default: `logical_consistency_score` ≥0.90, `completeness_score` ≥0.85, `evidence_support_score` ≥0.90, `schema_compliance_score` ≥0.95, `critical_issues` =0)

**Returns:**
`True` if all thresholds met, `False` otherwise

**Quality Metrics:**
- **Logical consistency** (35%): Overall judgement = worst domain (RoB 2/ROBINS-I), GRADE consistent with RoB
- **Completeness** (25%): All domains assessed, all outcomes appraised, rationales substantive
- **Evidence support** (25%): Judgements traceable to extraction, source_refs valid
- **Schema compliance** (15%): Enum values exact, required fields present

---

### Exception Classes

#### `UnsupportedPublicationType`

Raised when publication type not supported for specific operation.

**Signature:**
```python
class UnsupportedPublicationType(ValueError):
    pass
```

**Example:**
```python
try:
    appraisal = run_appraisal_with_correction(extraction, classification, ...)
except UnsupportedPublicationType as e:
    print(f"Publication type not supported for appraisal: {e}")
```

---

## 2. File Management

**Module**: `src/pipeline/file_manager.py`

### `class PipelineFileManager`

Manages consistent file naming and storage for pipeline steps.

**Constructor:**
```python
def __init__(self, pdf_path: Path)
```

**Parameters:**
- `pdf_path`: Path to PDF file being processed

**Creates:**
- `tmp/` directory if not exists
- File identifier from PDF filename (or DOI if in classification result)

**Example:**
```python
from pathlib import Path
from src.pipeline.file_manager import PipelineFileManager

file_mgr = PipelineFileManager(pdf_path=Path("research_paper.pdf"))
# identifier = "research_paper-20250112_143022"
```

---

### Methods

#### `get_filename()`

Generate consistent filenames for pipeline steps.

**Signature:**
```python
def get_filename(
    step: str,
    iteration_number: int | None = None,
    status: str = ""
) -> Path
```

**Parameters:**
- `step`: Step name (`"classification"`, `"extraction"`, `"validation"`, `"appraisal"`, `"appraisal_validation"`)
- `iteration_number`: Iteration number (None for non-iterative steps)
- `status`: Optional status suffix (`"best"`, `"final"`)

**Returns:**
Path in format `tmp/{identifier}-{step}{iteration}.json`

**Examples:**
```python
file_mgr.get_filename("classification")
# → tmp/paper-classification.json

file_mgr.get_filename("extraction", iteration_number=0)
# → tmp/paper-extraction0.json

file_mgr.get_filename("appraisal", status="best")
# → tmp/paper-appraisal-best.json
```

---

#### `save_json()` / `load_json()`

Save/load JSON data with consistent filename.

**Signatures:**
```python
def save_json(
    data: dict[Any, Any],
    step: str,
    iteration_number: int | None = None,
    status: str = ""
) -> Path

def load_json(
    step: str,
    iteration_number: int | None = None,
    status: str = ""
) -> dict[str, Any] | None
```

**Parameters:**
Same as `get_filename()`

**Returns:**
- `save_json()`: Path to saved file
- `load_json()`: Dictionary or None if file not found

**Example:**
```python
# Save classification result
path = file_mgr.save_json(
    data=classification_result,
    step="classification"
)

# Load best extraction
extraction = file_mgr.load_json(
    step="extraction",
    status="best"
)
```

---

#### `save_appraisal_iteration()` / `load_appraisal_iteration()`

Convenience wrappers for appraisal iteration files.

**Signatures:**
```python
def save_appraisal_iteration(
    iteration: int,
    appraisal_result: dict[str, Any],
    validation_result: dict[str, Any] | None = None
) -> tuple[Path, Path | None]

def load_appraisal_iteration(
    iteration: int
) -> tuple[dict[str, Any], dict[str, Any] | None]
```

**Returns:**
- `save_appraisal_iteration()`: Tuple of (appraisal_path, validation_path)
- `load_appraisal_iteration()`: Tuple of (appraisal_dict, validation_dict)

**Raises:**
- `FileNotFoundError`: If appraisal file doesn't exist (in `load_appraisal_iteration()`)

**Example:**
```python
# Save iteration 1
paths = file_mgr.save_appraisal_iteration(
    iteration=1,
    appraisal_result=appraisal,
    validation_result=validation
)
# → (tmp/paper-appraisal1.json, tmp/paper-appraisal_validation1.json)

# Load iteration 1
appraisal, validation = file_mgr.load_appraisal_iteration(iteration=1)
```

---

#### `save_best_appraisal()`

Save best appraisal iteration with `-best` suffix.

**Signature:**
```python
def save_best_appraisal(
    appraisal_result: dict[str, Any],
    validation_result: dict[str, Any]
) -> tuple[Path, Path]
```

**Returns:**
Tuple of (appraisal_path, validation_path)

**Example:**
```python
paths = file_mgr.save_best_appraisal(
    appraisal_result=best_appraisal,
    validation_result=best_validation
)
# → (tmp/paper-appraisal-best.json, tmp/paper-appraisal_validation-best.json)
```

---

#### `get_appraisal_iterations()`

Get metadata for all appraisal iterations.

**Signature:**
```python
def get_appraisal_iterations() -> list[dict[str, Any]]
```

**Returns:**
List of dictionaries with keys:
- `iteration_num`: Iteration number (int)
- `appraisal_file`: Appraisal file path (Path)
- `validation_file`: Validation file path (Path)
- `appraisal_exists`: Whether appraisal file exists (bool)
- `validation_exists`: Whether validation file exists (bool)
- `created_time`: File creation timestamp (float, from appraisal file)

**Example:**
```python
iterations = file_mgr.get_appraisal_iterations()
for it in iterations:
    print(f"Iteration {it['iteration_num']}: exists={it['appraisal_exists']}")
```

---

## 3. Validation

**Modules**: `src/pipeline/validation_runner.py`, `src/validation.py`

### Dual Validation Strategy

#### `run_dual_validation()`

Two-tier validation strategy: schema validation (always) + conditional LLM validation.

**Signature:**
```python
def run_dual_validation(
    extraction_result: dict[str, Any],
    pdf_path: Path,
    max_pages: int | None,
    publication_type: str,
    llm: BaseLLMProvider,
    console: Console,
    schema_quality_threshold: float = SCHEMA_QUALITY_THRESHOLD,
    banner_label: str | None = None
) -> dict[str, Any]
```

**Parameters:**
- `extraction_result`: Extraction JSON to validate
- `pdf_path`: Path to PDF (for LLM validation context)
- `max_pages`: Page limit
- `publication_type`: Publication type for schema selection
- `llm`: LLM provider instance
- `console`: Rich console for output
- `schema_quality_threshold`: Minimum schema quality to trigger LLM validation (default: 0.5)
- `banner_label`: Optional label for console output

**Process:**
1. **Schema validation** (always runs - fast, cheap):
   - JSON schema validation (Draft 2020-12)
   - Completeness assessment (required/optional fields)
   - Quality score = 50% schema compliance + 50% completeness

2. **LLM semantic validation** (conditional - only if schema quality ≥ threshold):
   - Hallucination detection (compare extraction to PDF)
   - Accuracy assessment (verify quantitative data)
   - Field-level validation (check each major section)

**Returns:**
Combined validation dictionary with keys:
- `schema_validation`: Schema validation results
- `verification_summary`: LLM validation summary (if triggered)
- `quality_assessment`: Quality scores
- `overall_status`: `"passed"` | `"warning"` | `"failed"`

**Cost Optimization:**
LLM validation only triggered when extraction has decent structure (≥50% schema quality). This avoids expensive LLM calls for garbage extractions.

**Example:**
```python
from src.pipeline.validation_runner import run_dual_validation
from src.llm import get_llm_provider

llm = get_llm_provider("openai")
validation = run_dual_validation(
    extraction_result=extraction,
    pdf_path=Path("paper.pdf"),
    max_pages=None,
    publication_type="interventional_trial",
    llm=llm,
    console=console
)

if validation['overall_status'] == 'passed':
    print("Validation passed - no correction needed")
```

**Constants:**
```python
SCHEMA_QUALITY_THRESHOLD = 0.5  # 50%
```

---

### Schema Validation Functions

#### `validate_with_schema()`

Validate data against JSON schema (Draft 2020-12).

**Signature:**
```python
def validate_with_schema(
    data: dict[str, Any],
    schema: dict[str, Any],
    strict: bool = True
) -> tuple[bool, list[str]]
```

**Parameters:**
- `data`: Dictionary to validate
- `schema`: JSON schema (Draft 2020-12)
- `strict`: Raise `ValidationError` if validation fails (default: True)

**Returns:**
Tuple of (`is_valid`, `errors`)

**Raises:**
- `ValidationError`: If `strict=True` and validation fails

**Example:**
```python
from src.validation import validate_with_schema
from src.schemas_loader import load_schema

schema = load_schema("interventional_trial")
is_valid, errors = validate_with_schema(extraction, schema, strict=False)

if not is_valid:
    for error in errors:
        print(f"Schema error: {error}")
```

---

#### `validate_extraction_quality()`

Comprehensive quality validation (schema + completeness).

**Signature:**
```python
def validate_extraction_quality(
    data: dict[str, Any],
    schema: dict[str, Any],
    strict: bool = False
) -> dict[str, Any]
```

**Parameters:**
- `data`: Dictionary to validate
- `schema`: JSON schema
- `strict`: Raise exception on failure (default: False)

**Returns:**
Dictionary with keys:
- `schema_compliant`: Boolean
- `validation_errors`: List of error messages
- `completeness`: Completeness statistics (from `check_data_completeness()`)
- `quality_score`: Float (50% schema + 50% completeness)

**Quality Score Formula:**
```
quality_score = 0.5 * schema_compliance + 0.5 * completeness_score
```

**Example:**
```python
from src.validation import validate_extraction_quality

quality = validate_extraction_quality(extraction, schema)
print(f"Quality: {quality['quality_score']:.2%}")
print(f"Completeness: {quality['completeness']['completeness_score']:.2%}")
```

---

#### `check_required_fields()` / `check_data_completeness()`

Check field presence and completeness statistics.

**Signatures:**
```python
def check_required_fields(
    data: dict[str, Any],
    required_fields: list[str]
) -> tuple[bool, list[str]]

def check_data_completeness(
    data: dict[str, Any],
    schema: dict[str, Any]
) -> dict[str, Any]
```

**Returns:**
- `check_required_fields()`: Tuple of (`all_present`, `missing_fields`)
- `check_data_completeness()`: Dictionary with `completeness_score`, field statistics

**Example:**
```python
from src.validation import check_required_fields, check_data_completeness

# Check specific fields
all_present, missing = check_required_fields(
    data=extraction,
    required_fields=["metadata", "study_design", "outcomes"]
)

# Full completeness analysis
completeness = check_data_completeness(extraction, schema)
print(f"Required fields: {completeness['required_fields_present']}/{completeness['required_fields_total']}")
```

---

#### `create_validation_report()`

Create human-readable validation report.

**Signature:**
```python
def create_validation_report(
    validation_results: dict[str, Any]
) -> str
```

**Returns:**
Multi-line formatted text report

**Example:**
```python
report = create_validation_report(validation)
print(report)
# Output:
# ===== VALIDATION REPORT =====
# Schema Compliant: ✓
# Quality Score: 0.92
# Completeness: 0.95
# ...
```

---

### Exception Classes

#### `ValidationError`

Raised when validation fails.

**Signature:**
```python
class ValidationError(Exception):
    pass
```

---

## 4. Schema Handling

**Module**: `src/schemas_loader.py`

### `load_schema()`

Load bundled JSON schema for publication type (with caching).

**Signature:**
```python
def load_schema(publication_type: str) -> dict[str, Any]
```

**Parameters:**
- `publication_type`: Schema identifier

**Supported Types:**
- **Extraction schemas**: `interventional_trial`, `observational_analytic`, `evidence_synthesis`, `prediction_prognosis`, `editorials_opinion`
- **Pipeline schemas**: `classification`, `validation`, `appraisal`, `appraisal_validation`, `report`, `report_validation`

**Returns:**
JSON schema dictionary (Draft 2020-12)

**Caching:**
Schemas are cached in memory after first load for performance.

**Raises:**
- `SchemaLoadError`: If schema not found or invalid JSON

**Example:**
```python
from src.schemas_loader import load_schema

schema = load_schema("interventional_trial")
print(schema['title'])  # "Interventional Trial Schema"
```

---

### `get_schema_info()`

Get schema metadata without loading full schema.

**Signature:**
```python
def get_schema_info(publication_type: str) -> dict[str, Any]
```

**Returns:**
Dictionary with keys:
- `title`: Schema title
- `schema_id`: Schema identifier
- `required_fields`: List of required top-level fields
- `description`: Schema description

**Example:**
```python
info = get_schema_info("interventional_trial")
print(info['title'])  # "Interventional Trial Schema"
print(info['required_fields'])  # ['metadata', 'study_design', 'outcomes']
```

---

### `validate_schema_compatibility()`

Check OpenAI structured outputs compatibility.

**Signature:**
```python
def validate_schema_compatibility(
    schema: dict[str, Any]
) -> dict[str, Any]
```

**Returns:**
Dictionary with keys:
- `compatible`: Boolean
- `warnings`: List of compatibility warnings
- `estimated_tokens`: Estimated token count for schema

**Checks:**
- Schema size (max 100KB for OpenAI structured outputs)
- `additionalProperties: false` enforcement
- External `$ref` references (not supported)
- Advanced JSON Schema features (e.g., `$defs` with cycles)

**Example:**
```python
schema = load_schema("interventional_trial")
compat = validate_schema_compatibility(schema)

if not compat['compatible']:
    print(f"Schema incompatible with OpenAI structured outputs")
    for warning in compat['warnings']:
        print(f"  - {warning}")
```

---

### `get_all_available_schemas()` / `get_supported_publication_types()`

Query available schemas.

**Signatures:**
```python
def get_all_available_schemas() -> dict[str, dict[str, Any]]
def get_supported_publication_types() -> list[str]
```

**Returns:**
- `get_all_available_schemas()`: Dictionary mapping publication types to schema info
- `get_supported_publication_types()`: List of publication type identifiers

**Example:**
```python
types = get_supported_publication_types()
print(types)  # ['interventional_trial', 'observational_analytic', ...]

all_schemas = get_all_available_schemas()
for pub_type, info in all_schemas.items():
    print(f"{pub_type}: {info['title']}")
```

---

### `schema_exists()` / `clear_schema_cache()`

Utility functions.

**Signatures:**
```python
def schema_exists(publication_type: str) -> bool
def clear_schema_cache() -> None
```

**Example:**
```python
if schema_exists("interventional_trial"):
    schema = load_schema("interventional_trial")

# Clear cache (useful for testing/development)
clear_schema_cache()
```

---

### Exception Classes

#### `SchemaLoadError`

Error loading schema files.

**Signature:**
```python
class SchemaLoadError(Exception):
    pass
```

---

## 5. Prompt Handling

**Module**: `src/prompts.py`

### Extraction Pipeline Prompts

#### `load_classification_prompt()`

Load classification prompt.

**Signature:**
```python
def load_classification_prompt() -> str
```

**Returns:**
Prompt text from `prompts/Classification.txt`

**Raises:**
- `PromptLoadError`: If prompt file not found

---

#### `load_extraction_prompt()`

Load extraction prompt based on publication type.

**Signature:**
```python
def load_extraction_prompt(publication_type: str) -> str
```

**Supported Types:**
- `interventional_trial` → `Extraction-prompt-interventional.txt`
- `observational_analytic` → `Extraction-prompt-observational.txt`
- `evidence_synthesis` → `Extraction-prompt-evidence-synthesis.txt`
- `prediction_prognosis` → `Extraction-prompt-prediction.txt`
- `editorials_opinion` → `Extraction-prompt-editorials.txt`

**Raises:**
- `PromptLoadError`: If type not supported or file not found

---

#### `load_validation_prompt()` / `load_correction_prompt()`

Load validation/correction prompts for extraction.

**Signatures:**
```python
def load_validation_prompt() -> str
def load_correction_prompt() -> str
```

**Files:**
- `prompts/Extraction-validation.txt`
- `prompts/Extraction-correction.txt`

---

### Appraisal Prompts

#### `load_appraisal_prompt()`

Load appraisal prompt based on publication type.

**Signature:**
```python
def load_appraisal_prompt(publication_type: str) -> str
```

**Supported Types:**
- `interventional_trial` → `Appraisal-interventional.txt` (RoB 2)
- `observational_analytic` → `Appraisal-observational.txt` (ROBINS-I)
- `evidence_synthesis` → `Appraisal-evidence-synthesis.txt` (AMSTAR 2 + ROBIS)
- `prediction_prognosis` → `Appraisal-prediction.txt` (PROBAST)
- `diagnostic` → `Appraisal-prediction.txt` (shares with prediction - PROBAST/QUADAS)
- `editorials_opinion` → `Appraisal-editorials.txt`

**Note:**
`diagnostic` type shares prompt with `prediction_prognosis` (both use PROBAST-like assessment).

---

#### `load_appraisal_validation_prompt()` / `load_appraisal_correction_prompt()`

Load validation/correction prompts for appraisal.

**Signatures:**
```python
def load_appraisal_validation_prompt() -> str
def load_appraisal_correction_prompt() -> str
```

**Files:**
- `prompts/Appraisal-validation.txt`
- `prompts/Appraisal-correction.txt`

---

### Report Prompts

#### `load_report_generation_prompt()`

Load report generation prompt.

**Signature:**
```python
def load_report_generation_prompt() -> str
```

**File:** `prompts/Report-generation.txt`

---

#### `load_report_validation_prompt()` / `load_report_correction_prompt()`

Load validation/correction prompts for reports.

**Signatures:**
```python
def load_report_validation_prompt() -> str
def load_report_correction_prompt() -> str
```

**Files:**
- `prompts/Report-validation.txt`
- `prompts/Report-correction.txt`

---

### Utility Functions

#### `get_all_available_prompts()` / `validate_prompt_directory()`

Query available prompts.

**Signatures:**
```python
def get_all_available_prompts() -> dict[str, str]
def validate_prompt_directory() -> dict[str, bool]
```

**Returns:**
- `get_all_available_prompts()`: Dictionary mapping prompt names to descriptions
- `validate_prompt_directory()`: Dictionary mapping filenames to existence boolean

**Example:**
```python
prompts = get_all_available_prompts()
for name, desc in prompts.items():
    print(f"{name}: {desc}")

# Check if all prompts present
validation = validate_prompt_directory()
missing = [name for name, exists in validation.items() if not exists]
if missing:
    print(f"Missing prompts: {missing}")
```

---

### Exception Classes

#### `PromptLoadError`

Error loading prompt files.

**Signature:**
```python
class PromptLoadError(Exception):
    pass
```

---

## 6. LLM Integration

**Modules**: `src/llm/__init__.py`, `src/llm/base.py`

### Factory Function

#### `get_llm_provider()`

Factory to instantiate LLM provider (OpenAI or Claude).

**Signature:**
```python
def get_llm_provider(
    provider: str | LLMProvider,
    settings: LLMSettings | None = None
) -> BaseLLMProvider
```

**Parameters:**
- `provider`: Provider name (`"openai"` or `"claude"`) or `LLMProvider` enum
- `settings`: Optional custom settings (uses global settings if None)

**Returns:**
`OpenAIProvider` or `ClaudeProvider` instance

**Raises:**
- `LLMError`: If unsupported provider
- `LLMProviderError`: If initialization fails (e.g., missing API key)

**Example:**
```python
from src.llm import get_llm_provider

llm = get_llm_provider("openai")
response = llm.generate_text("Summarize this abstract...", system_prompt="You are a medical expert.")
```

---

### Convenience Functions

#### `generate_text()`

Generate free-form text using specified provider.

**Signature:**
```python
def generate_text(
    prompt: str,
    provider: str | LLMProvider = None,
    system_prompt: str | None = None,
    **kwargs
) -> str
```

**Parameters:**
- `prompt`: User prompt text
- `provider`: Provider name (uses default from settings if None)
- `system_prompt`: Optional system prompt
- `**kwargs`: Additional provider-specific arguments

**Returns:**
Generated text response

**Example:**
```python
from src.llm import generate_text

summary = generate_text(
    prompt="Summarize the key findings from this study...",
    provider="openai",
    system_prompt="You are a medical expert."
)
```

---

#### `generate_json_with_schema()`

Generate schema-conforming JSON.

**Signature:**
```python
def generate_json_with_schema(
    prompt: str,
    schema: dict[str, Any],
    provider: str | LLMProvider = None,
    system_prompt: str | None = None,
    schema_name: str | None = None,
    **kwargs
) -> dict[str, Any]
```

**Parameters:**
- `prompt`: User prompt text
- `schema`: JSON schema (Draft 2020-12)
- `provider`: Provider name
- `system_prompt`: Optional system prompt
- `schema_name`: Optional schema name for OpenAI structured outputs
- `**kwargs`: Additional arguments

**Returns:**
Dictionary conforming to schema

**Schema Compliance:**
- **OpenAI**: Guaranteed via structured outputs (native JSON mode)
- **Claude**: Validated via prompt engineering + post-validation

**Example:**
```python
from src.llm import generate_json_with_schema
from src.schemas_loader import load_schema

schema = load_schema("interventional_trial")
extraction = generate_json_with_schema(
    prompt=f"Extract data from this PDF: {pdf_text}",
    schema=schema,
    provider="openai",
    system_prompt="Extract structured data from medical research papers.",
    schema_name="interventional_trial_extraction"
)
```

---

### Base Provider Class

#### `class BaseLLMProvider(ABC)`

Abstract base class for LLM providers.

**Abstract Methods:**

##### `generate_text()`

Generate free-form text response.

**Signature:**
```python
@abstractmethod
def generate_text(
    prompt: str,
    system_prompt: str | None = None,
    **kwargs
) -> str
```

---

##### `generate_json_with_schema()`

Generate structured JSON conforming to schema.

**Signature:**
```python
@abstractmethod
def generate_json_with_schema(
    prompt: str,
    schema: dict[str, Any],
    system_prompt: str | None = None,
    schema_name: str | None = None,
    **kwargs
) -> dict[str, Any]
```

---

##### `generate_json_with_pdf()`

Generate structured JSON from PDF using vision capabilities.

**Signature:**
```python
@abstractmethod
def generate_json_with_pdf(
    pdf_path: Union[Path, str],
    schema: dict[str, Any],
    system_prompt: str | None = None,
    max_pages: int | None = None,
    schema_name: str | None = None,
    **kwargs
) -> dict[str, Any]
```

**PDF Upload Support:**
- **OpenAI**: Supports PDF upload (100 page, 32 MB limits)
- **Claude**: Supports PDF upload (100 page, 32 MB limits)

**Vision Capabilities:**
Preserves tables, figures, charts, and formatting (critical for medical research PDFs).

**Cost:**
~1,500-3,000 tokens per page (3-6x text extraction)

**Example:**
```python
llm = get_llm_provider("openai")
extraction = llm.generate_json_with_pdf(
    pdf_path=Path("paper.pdf"),
    schema=schema,
    system_prompt="Extract structured data from this medical research paper.",
    max_pages=None  # Process all pages
)
```

---

### Exception Classes

#### `LLMError` / `LLMProviderError`

LLM-related exceptions.

**Signatures:**
```python
class LLMError(Exception):
    """Base exception for LLM-related errors"""
    pass

class LLMProviderError(LLMError):
    """Error with specific LLM provider"""
    pass
```

---

## 7. Utilities

**Module**: `src/pipeline/utils.py`

### `doi_to_safe_filename()`

Convert DOI to filesystem-safe string.

**Signature:**
```python
def doi_to_safe_filename(doi: str) -> str
```

**Returns:**
DOI with slashes/colons replaced by hyphens

**Example:**
```python
safe_doi = doi_to_safe_filename("10.1234/test.article")
# → "10-1234-test-article"
```

---

### `get_file_identifier()`

Get file identifier, preferring DOI over PDF stem + timestamp.

**Signature:**
```python
def get_file_identifier(
    classification_result: dict[str, Any],
    pdf_path: Path
) -> str
```

**Returns:**
Safe DOI (if available in classification) or fallback identifier

**Example:**
```python
identifier = get_file_identifier(classification, Path("paper.pdf"))
# If DOI present: "10-1234-test-article"
# Otherwise: "paper-20250112_143022"
```

---

### `get_next_step()` / `check_breakpoint()`

Pipeline control utilities.

**Signatures:**
```python
def get_next_step(current_step: str) -> str
def check_breakpoint(
    step_name: str,
    results: dict[str, Any],
    file_manager: PipelineFileManager,
    breakpoint_after_step: str | None = None
) -> bool
```

**Returns:**
- `get_next_step()`: Next step name or `"None"` if last/invalid
- `check_breakpoint()`: True if breakpoint triggered (stop), False otherwise

**Example:**
```python
next_step = get_next_step("classification")
# → "extraction"

should_stop = check_breakpoint(
    step_name="extraction",
    results=results,
    file_manager=file_mgr,
    breakpoint_after_step="extraction"
)
# → True (stop after extraction)
```

---

## 8. CLI Entry Point

**Module**: `run_pipeline.py`

### `main()`

CLI entry point for pipeline execution.

**Command-line Arguments:**

#### Required Arguments
- `pdf`: Path to PDF file

#### Optional Arguments
- `--max-pages`: Limit number of pages (default: all pages)
- `--keep-tmp`: Keep intermediate files (flag, default: False)
- `--llm-provider`: Choose LLM provider (choices: `openai`, `claude`, default: `openai`)
- `--step`: Run specific step (choices: `classification`, `extraction`, `validation`, `correction`, `validation_correction`, `appraisal`, `report_generation`)

#### Validation/Correction Thresholds
- `--max-iterations`: Max correction attempts for validation_correction (default: 3)
- `--completeness-threshold`: Min completeness score (0.0-1.0, default: 0.90)
- `--accuracy-threshold`: Min accuracy score (0.0-1.0, default: 0.95)
- `--schema-threshold`: Min schema compliance (0.0-1.0, default: 0.95)

#### Appraisal Thresholds
- `--appraisal-max-iter`: Max appraisal iterations (default: 3)
- `--appraisal-logical-threshold`: Min logical consistency for appraisal (0.0-1.0, default: 0.90)
- `--appraisal-completeness-threshold`: Min completeness for appraisal (0.0-1.0, default: 0.85)
- `--appraisal-evidence-threshold`: Min evidence support for appraisal (0.0-1.0, default: 0.90)
- `--appraisal-schema-threshold`: Min schema compliance for appraisal (0.0-1.0, default: 0.95)
- `--appraisal-single-pass`: Skip iterative correction for appraisal (flag, default: False)

#### Report Generation Options
- `--report-language`: Report language (choices: `en`, default: `en`)
- `--report-renderer`: Rendering engine (choices: `latex`, `weasyprint`, default: `latex`)
- `--report-compile-pdf` / `--no-report-compile-pdf`: Enable/disable PDF compilation (default: enabled)
- `--enable-figures` / `--disable-figures`: Enable/disable figure generation (default: enabled)
- `--skip-report`: Skip report generation in full pipeline (flag)

---

### Usage Examples

#### Full Pipeline
```bash
# Run complete 5-step pipeline with defaults
python run_pipeline.py paper.pdf

# Use Claude with custom page limit
python run_pipeline.py paper.pdf --llm-provider claude --max-pages 50

# Skip report generation (4-step pipeline)
python run_pipeline.py paper.pdf --skip-report
```

#### Single Step Execution
```bash
# Run classification only
python run_pipeline.py paper.pdf --step classification

# Run validation/correction with custom thresholds
python run_pipeline.py paper.pdf --step validation_correction \
  --max-iterations 2 \
  --completeness-threshold 0.85

# Run appraisal with custom settings
python run_pipeline.py paper.pdf --step appraisal \
  --appraisal-max-iter 5 \
  --appraisal-logical-threshold 0.95
```

#### Appraisal Modes
```bash
# Iterative appraisal (default)
python run_pipeline.py paper.pdf --step appraisal --appraisal-max-iter 3

# Single-pass appraisal (faster, no correction)
python run_pipeline.py paper.pdf --step appraisal --appraisal-single-pass
```

#### Report Generation
```bash
# Run report generation only (requires existing extraction + appraisal)
python run_pipeline.py paper.pdf --step report_generation

# Custom language and renderer
python run_pipeline.py paper.pdf --step report_generation --report-language en --report-renderer weasyprint

# LaTeX source only (no PDF compilation)
python run_pipeline.py paper.pdf --step report_generation --no-report-compile-pdf

# Disable figure generation
python run_pipeline.py paper.pdf --step report_generation --disable-figures
```

---

## Cross-References & Dependencies

### Pipeline Flow Dependencies

1. **Classification** (no dependencies)
   - Outputs: `publication_type`, `metadata`

2. **Extraction** (requires: classification)
   - Inputs: `classification_result["publication_type"]` → routes to extraction prompt
   - Outputs: Structured data conforming to publication type schema

3. **Validation** (requires: extraction, classification)
   - Inputs: `extraction_result`, `classification_result["publication_type"]` → routes to schema
   - Outputs: Quality assessment with scores

4. **Correction** (requires: validation, extraction, classification)
   - Inputs: `validation_result`, `extraction_result`, `classification_result`
   - Outputs: Improved extraction

5. **Appraisal** (requires: extraction, classification)
   - Inputs: `extraction_result`, `classification_result["publication_type"]` → routes to appraisal prompt
   - Outputs: Risk of bias assessment, GRADE ratings, applicability

6. **Report Generation** (requires: classification, extraction, appraisal)
   - Inputs: `classification_result`, `extraction_result`, `appraisal_result`
   - Outputs: Block-based report JSON, rendered PDF/LaTeX/Markdown
   - Dependency gating: Blocks if extraction quality < 0.70 or appraisal missing RoB

### Key Data Flows

- `classification_result["publication_type"]` → routes to appropriate extraction/appraisal prompts
- `validation_result["quality_score"]` → determines if correction needed
- `file_manager.identifier` → consistent naming across all output files
- `progress_callback(step_name, status, data)` → UI updates during execution

### Quality Thresholds (Configurable)

#### Extraction Validation
- `completeness_score` ≥ 0.90 (90%)
- `accuracy_score` ≥ 0.95 (95%)
- `schema_compliance_score` ≥ 0.95 (95%)

#### Appraisal Validation
- `logical_consistency_score` ≥ 0.90 (90%) - weight: 35%
- `completeness_score` ≥ 0.85 (85%) - weight: 25%
- `evidence_support_score` ≥ 0.90 (90%) - weight: 25%
- `schema_compliance_score` ≥ 0.95 (95%) - weight: 15%

#### Report Validation
- `accuracy_score` ≥ 0.95 (95%) - weight: 35%
- `completeness_score` ≥ 0.85 (85%) - weight: 30%
- `cross_reference_consistency_score` ≥ 0.90 (90%) - weight: 10%
- `data_consistency_score` ≥ 0.90 (90%) - weight: 10%
- `schema_compliance_score` ≥ 0.95 (95%) - weight: 15%

#### Schema Quality Threshold
- `SCHEMA_QUALITY_THRESHOLD` = 0.5 (50%) - triggers LLM validation in dual validation

---

## Additional Resources

- **Architecture**: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- **Feature Specifications**: [`features/`](features/)
  - Appraisal: [`features/appraisal.md`](features/appraisal.md)
  - Report Generation: [`features/report-generation.md`](features/report-generation.md)
  - Validation/Correction: [`features/iterative-validation-correction.md`](features/iterative-validation-correction.md)
- **Usage Guide**: [`README.md`](README.md)
- **Appraisal Guide**: [`docs/appraisal.md`](docs/appraisal.md)
- **Report Guide**: [`docs/report.md`](docs/report.md)
- **LaTeX Templates**: [`templates/latex/vetrix/`](templates/latex/vetrix/)
- **Changelog**: [`CHANGELOG.md`](CHANGELOG.md)
