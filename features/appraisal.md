# Feature: Critical Appraisal met Iteratieve Validation & Correction

**Status**: In Progress - Fase 1 & 2 Complete, Testing Pending
**Branch**: `feature/appraisal`
**Created**: 2025-11-04
**Updated**: 2025-11-10 (v1.2 - Fase 1 & 2 geïmplementeerd: orchestrator + prompts)
**Author**: Rob Tolboom (met Claude Code)

**Samenvatting**
- Iteratieve critical appraisal-stap beoordeelt automatisch risk of bias, GRADE en toepasbaarheid voor alle ondersteunde publicatietypes en levert gestandaardiseerde JSON-output.
- Grootste risico is inconsistent LLM-gedrag; mitigaties omvatten strikte validation/correction prompts, configurabele kwaliteitsdrempels en regressietests per tool.

## Scope

**In scope**
- Iteratieve appraisal-stap na extraction/validation, inclusief validatie- en correctieprompts.
- Ondersteuning voor interventional, observational, evidence synthesis, prediction_prognosis én diagnostic (gedeelde prompt), plus editorials.
- Opslag, selectie en rapportage van appraisal-iteraties in CLI en Streamlit UI.

**Out of scope**
- Nieuwe LLM-providers of non-LLM rule engines voor appraisal.
- Uitbreiding van extraction-stap of schema’s buiten `appraisal.schema.json`.
- Volledige automatisering van evidence grading voor diagnostische workflows buiten PROBAST/QUADAS.

---

## Probleemstelling

### Huidige Situatie

De pipeline extraheert gestructureerde data uit medische literatuur met validation/correction, maar voert **geen systematische quality assessment** uit:

- **Extraction & Validation** (huidige pipeline):
  - PDF → Structured JSON (extraction)
  - Schema validatie + LLM validatie (completeness, accuracy)
  - Iteratieve correctie tot kwaliteit voldoende
  - **Output**: Gevalideerde extractie (facts, numbers, study design)

- **Geen Critical Appraisal**:
  - ❌ Geen risk of bias beoordeling (RoB 2, ROBINS-I)
  - ❌ Geen certainty of evidence rating (GRADE)
  - ❌ Geen prediction model quality (PROBAST)
  - ❌ Geen systematic review quality (AMSTAR 2, ROBIS)
  - ❌ Geen argument quality assessment (editorials)

### Pijnpunten

1. **Geen Quality Signal**: Gebruiker weet niet of geëxtraheerde studie methodologisch betrouwbaar is
2. **Handmatige Appraisal Vereist**: Clinici moeten elk paper handmatig beoordelen met RoB/GRADE tools
3. **Geen Evidence Grading**: Kan sterkte van bewijs niet automatisch classificeren voor rapporten/podcast
4. **Incomplete Output**: Extraction zonder appraisal is onvoldoende voor evidence-based decision making
5. **Inconsistente Beoordelingen**: Handmatige appraisal is subjectief en tijdrovend

### Motivatie

Evidence-based medicine vereist **systematische critical appraisal**:

- ✅ **Risk of Bias**: Interne validiteit van studie (RoB 2 voor RCTs, ROBINS-I voor observational)
- ✅ **Certainty of Evidence**: GRADE ratings voor clinical recommendations
- ✅ **Applicability**: Externe validiteit (generalizability naar doelpopulatie)
- ✅ **Prediction Model Quality**: PROBAST voor prognostic/diagnostic models
- ✅ **Systematic Review Quality**: AMSTAR 2 + ROBIS voor meta-analyses
- ✅ **Argument Quality**: Evidence basis en logical consistency voor editorials

**Voordelen automatische appraisal:**
- Snelle, consistente, transparante kwaliteitsbeoordeling
- Structured output (JSON) bruikbaar voor downstream analysis
- Iteratieve correctie verhoogt appraisal betrouwbaarheid
- Essentieel voor geautomatiseerde evidence synthesis en rapporten

---

## Gewenste Situatie

### Pipeline Workflow (met Appraisal)

```
┌──────────────────────────────────────────────────────────────────┐
│  HUIDIGE PIPELINE                                                │
└──────────────────────────────────────────────────────────────────┘
  1. Classification → publication_type
  2. Extraction → extraction.json
  3. Validation & Correction → validated_extraction.json (iterative)
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  NIEUWE STAP: CRITICAL APPRAISAL (Iterative)                     │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────────┐
  │  APPRAISAL             │
  │  (study type routing)  │
  └────────────────────────┘
           │
           ├─ interventional_trial → Appraisal-interventional.txt (RoB 2 / ROBINS-I)
           ├─ observational_analytic → Appraisal-observational.txt (ROBINS-I/E)
           ├─ evidence_synthesis → Appraisal-evidence-synthesis.txt (AMSTAR 2 + ROBIS)
           ├─ prediction_prognosis OR diagnostic → Appraisal-prediction.txt (PROBAST)
           └─ editorials_opinion → Appraisal-editorials.txt (Argument quality)

**Note**: `diagnostic` study type uses the same prediction_prognosis prompt (shared PROBAST-like assessment).
           │
           ▼
  ┌────────────────────────┐
  │  APPRAISAL VALIDATION  │
  │  (Appraisal-validation)│
  └────────────────────────┘
           │
           ▼
     Quality Sufficient?
           │
    ┌──────┴──────┐
   JA            NEE
    │              │
    ▼              ▼
  ┌─────┐   Iterations < MAX?
  │ OK  │          │
  └─────┘    ┌─────┴─────┐
            JA           NEE
             │             │
             ▼             ▼
    ┌─────────────────┐  ┌──────────┐
    │  CORRECTION     │  │ STOP MAX │
    │  (Appraisal-    │  │  (select │
    │   correction)   │  │   best)  │
    └─────────────────┘  └──────────┘
             │
             └──[LOOP BACK TO APPRAISAL VALIDATION]
           │
           ▼
  appraisal.json (best iteration)
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  DOWNSTREAM PIPELINE                                             │
└──────────────────────────────────────────────────────────────────┘
  4. Report Generation (uses extraction + appraisal)
  5. Podcast Script (integrates quality assessment)
```

### Belangrijkste Veranderingen

1. **Nieuwe Pipeline Stap**: Appraisal na validation/correction, vóór report/podcast
2. **Study Type Routing**: 5 classification types → 5 appraisal prompts (tool-specific)
   - Classification types: `interventional_trial`, `observational_analytic`, `evidence_synthesis`, `prediction_prognosis`, `editorials_opinion`
   - Note: `diagnostic` studies in extraction schema share the `prediction_prognosis` appraisal prompt
3. **Iteratieve Loop**: Appraisal → Validation → Correction → ... tot kwaliteit voldoende
4. **Tool-Specific Assessment**:
   - RCTs → RoB 2 (5 domains: randomization, deviations, missing data, measurement, selection)
   - Nonrandomized → ROBINS-I (7 domains: confounding, selection, classification, deviations, missing, measurement, selection)
   - Meta-analyses → AMSTAR 2 (16 items) + ROBIS (4 domains)
   - Prediction models → PROBAST (4 domains × risk + applicability)
   - Editorials → Argument quality (evidence type, support strength, counterarguments)

5. **Quality Thresholds**: Configurable stop criteria voor logical consistency, completeness, evidence support

---

## Technisch Ontwerp

### 1. Schema Design

**Existing Schema**: `schemas/appraisal.schema.json` (v1.0, 462 lines)

- ✅ **Self-contained**: No external $refs to common.schema.json → **NO bundling needed**
- ✅ **Study type support**: 6 types in schema (`interventional_trial`, `observational_analytic`, `diagnostic`, `prediction_prognosis`, `evidence_synthesis`, `editorials_opinion`)
  - Note: Schema study_type values must align with classification output
  - `diagnostic` is valid in extraction schema and uses prediction_prognosis appraisal prompt
- ✅ **Tool coverage**:
  - RoB 2 / ROBINS-I/E (interventional/observational)
  - QUADAS-2/C (diagnostic accuracy)
  - PROBAST (prediction/prognosis)
  - AMSTAR 2 + ROBIS (systematic reviews)
- ✅ **Structured domains**: risk_of_bias, analysis_issues, causal_strategy, probast, amstar2, robis, synthesis_quality, argument_quality
- ✅ **21 top-level properties** with comprehensive $defs (SourceRef, RiskOfBiasDomain, RobisDomain)

**Key Schema Properties**:
```json
{
  "appraisal_version": "v1.0",
  "study_id": "...",
  "study_type": "interventional_trial|observational_analytic|evidence_synthesis|prediction_prognosis|editorials_opinion|diagnostic",
  "tool": {
    "name": "RoB 2|ROBINS-I|PROBAST|...",
    "version": "...",
    "variant": "parallel-RCT|cluster|crossover|...",
    "judgement_scale": "rob2|robins|quadas|probast"
  },
  "risk_of_bias": {
    "overall": "Low risk|Some concerns|High risk|...",
    "domains": [
      {
        "domain": "randomization_process|...",
        "judgement": "Low risk|Some concerns|High risk",
        "rationale": "...",
        "source_refs": [...]
      }
    ]
  },
  "grade_per_outcome": [...],
  "applicability": {...},
  "bottom_line": {
    "short": "...",
    "for_podcast": "..."
  }
}
```

### 2. Prompt Architecture

**Appraisal Prompts** (✅ Already implemented):
- `prompts/Appraisal-interventional.txt` - RoB 2 critical appraisal (70 lines)
- `prompts/Appraisal-observational.txt` - ROBINS-I/E assessment (61 lines)
- `prompts/Appraisal-evidence-synthesis.txt` - AMSTAR 2 + meta-analysis quality (73 lines)
- `prompts/Appraisal-prediction.txt` - PROBAST + performance evaluation (69 lines, gedeeld door prediction_prognosis en diagnostic)
- `prompts/Appraisal-editorials.txt` - Argument quality assessment (53 lines)

**New Prompts Needed**:

#### A. `prompts/Appraisal-validation.txt`
**Purpose**: Validate appraisal JSON for logical consistency, completeness, evidence support

**Input**:
- APPRAISAL_JSON: Critical appraisal output
- EXTRACTION_JSON: Original extraction (context for evidence checking)
- APPRAISAL_SCHEMA: appraisal.schema.json

**Verification Checks**:
1. **Logical Consistency**
   - Overall judgement = worst domain judgement? (RoB 2/ROBINS-I rule)
   - GRADE downgrades consistent with RoB assessment?
     - **Note**: Full GRADE validation is complex (requires MID thresholds, I² interpretation, publication bias assessment)
     - Initial validation: Check basic consistency (RoB "High risk" → GRADE downgrade for risk of bias)
     - Future enhancement: Rule-based GRADE assistance (CI width → imprecision, I² → inconsistency)
   - Tool choice appropriate for study design? (RCT → RoB 2, Nonrandomized → ROBINS-I)
   - Predicted bias direction consistent with domain rationale?

2. **Completeness Assessment**
   - All required domains assessed? (RoB 2: 5, ROBINS-I: 7, PROBAST: 4, AMSTAR 2: 16)
   - All outcomes from extraction appraised? (grade_per_outcome matches outcomes[])
   - Rationales present and substantive?
     - Minimum length: 50 characters (not 20)
     - Domain-specific keywords present (e.g., RoB 2 randomization → "allocation", "sequence generation", "baseline")
     - Boilerplate detection: Flag phrases like "No information provided", "Unclear from paper", "Not reported"
   - Applicability fields populated when relevant?

3. **Evidence Support**
   - Judgements traceable to extraction data? (e.g., RoB randomization domain references study_design.randomization)
   - Source_refs valid? (page numbers, table IDs match extraction sources)
   - GRADE downgrades justified by quantitative data? (e.g., imprecision → wide CI in extraction)
   - Performance metrics (PROBAST) match extraction results?

4. **Schema Compliance**
   - Required fields present (appraisal_version, study_id, study_type, tool, risk_of_bias)?
   - Enum values exact match? ("Low risk" not "low", "Some concerns" not "some concerns")
   - Correct judgement scale for tool? (RoB 2: Low risk/Some concerns/High risk; ROBINS-I: Low/Moderate/Serious/Critical)
   - Cross-references resolve? (outcome_id in grade_per_outcome exists in extraction.outcomes[])

**Output**: Validation report JSON (similar to extraction validation schema)
```json
{
  "validation_version": "v1.0",
  "validation_summary": {
    "overall_status": "passed|warning|failed",
    "logical_consistency_score": 0.95,
    "completeness_score": 0.90,
    "evidence_support_score": 0.92,
    "schema_compliance_score": 1.0,
    "critical_issues": 0,
    "quality_score": 0.94
  },
  "issues": [
    {
      "severity": "critical|moderate|minor",
      "category": "logical_inconsistency|missing_domain|unsupported_judgement|schema_violation",
      "field_path": "risk_of_bias.overall",
      "description": "Overall judgement 'Low risk' contradicts domain 'randomization_process: High risk'",
      "recommendation": "Set overall to 'High risk' per RoB 2 worst-domain rule"
    }
  ]
}
```

**Scoring Thresholds** (default):
- `logical_consistency_score >= 0.90`
- `completeness_score >= 0.85`
- `evidence_support_score >= 0.90`
- `schema_compliance_score >= 0.95`
- `critical_issues == 0`

**Note on Scoring Architecture**:
- **Thresholds** = Minimum requirements for stopping (all must pass to reach "passed" status)
- **Weights** = Relative importance for ranking iterations (used in quality_score formula)
- Example: `schema_compliance_score` has high threshold (0.95) but low weight (0.15) because it's a strict requirement but less important for differentiating between passing iterations

**Scoreberekening**:
- Iedere subscoreschaal loopt van 0.0-1.0 en wordt afgerond op twee decimalen in het rapport.
- `quality_score = 0.35 * logical_consistency_score + 0.25 * completeness_score + 0.25 * evidence_support_score + 0.15 * schema_compliance_score`.
- **Critical issues handling**:
  - Zodra `critical_issues > 0`:
    - `overall_status` → `"failed"` (overrides all other checks)
    - `schema_compliance_score` → `0.0` (reflects schema failure)
    - `quality_score` capped at 0.69 (prevents selection as best iteration)
- `overall_status = passed` wanneer alle drempels gehaald worden, `warning` bij maximaal twee lichte afwijkingen (<=0.05 onder drempel) zonder critical issues, `failed` in alle overige gevallen.
- De orchestrator gebruikt `quality_score` als primaire ranking voor iteraties, met de bestaande tie-breakers voor consistentiecontrole.

**Overall Status**:
- "passed": Alle drempels gehaald.
- "warning": Maximaal twee drempels <=0.05 onder target en geen critical issues.
- "failed": Meer afwijkingen of `critical_issues > 0` (heeft prioriteit boven score).

#### B. `prompts/Appraisal-correction.txt`
**Purpose**: Correct appraisal JSON based on validation issues

**Input**:
- VALIDATION_REPORT: Issues from appraisal validation
- ORIGINAL_APPRAISAL: Flawed appraisal JSON
- EXTRACTION_JSON: Extraction data (for re-checking evidence)
- APPRAISAL_SCHEMA: appraisal.schema.json

**Correction Workflow**:
1. **Fix Logical Inconsistencies**
   - Recalculate overall judgement per tool rules (worst domain wins)
   - Align GRADE downgrades with RoB assessment
   - Fix predicted bias directions based on domain rationales

2. **Complete Missing Data**
   - Add missing domain assessments
   - Add missing outcome appraisals (from extraction.outcomes[])
   - Expand sparse rationales with evidence from extraction

3. **Strengthen Evidence Support**
   - Re-check extraction for supporting data
   - Add/correct source_refs
   - Quantify judgements with extraction metrics (e.g., "Wide CI: 0.5-2.1" for imprecision)

4. **Schema Compliance Fixes**
   - Correct enum casing
   - Add missing required fields
   - Remove disallowed properties
   - Validate cross-references

**Output**: Corrected appraisal JSON (ready for re-validation)

### 3. API Design

#### New High-Level Function

```python
# src/pipeline/orchestrator.py

def run_appraisal_with_correction(
    extraction_result: dict,
    classification_result: dict,
    llm_provider: str,
    file_manager: PipelineFileManager,
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    progress_callback: Callable | None = None,
) -> dict:
    """
    Run critical appraisal with automatic iterative correction until quality is sufficient.

    Workflow:
        1. Route to appropriate appraisal prompt based on publication_type
        2. Run appraisal (e.g., RoB 2 for RCTs)
        3. Validate appraisal (logical consistency, completeness, evidence support)
        4. If quality insufficient and iterations < max:
           - Run correction
           - Validate corrected appraisal
           - Repeat until quality OK or max iterations reached
        5. Select best iteration based on quality metrics
        6. Return best appraisal + validation + iteration history

    Args:
        extraction_result: Validated extraction JSON (input for appraisal)
        classification_result: Classification result (for publication_type routing)
        llm_provider: LLM provider name ("openai" | "claude")
        file_manager: File manager for saving appraisal iterations
        max_iterations: Maximum correction attempts after initial appraisal (default: 3)
            Iteration 0: Initial appraisal + validation
            Iterations 1-N: Correction attempts (if quality insufficient)
            Example: max_iterations=3 → up to 4 total LLM calls (iter 0,1,2,3)
            Note: Also called "max_correction_iterations" conceptually
        quality_thresholds: Custom thresholds, defaults to:
            {
                'logical_consistency_score': 0.90,
                'completeness_score': 0.85,
                'evidence_support_score': 0.90,
                'schema_compliance_score': 0.95,
                'critical_issues': 0
            }
        progress_callback: Optional callback for progress updates

    Returns:
        dict: {
            'best_appraisal': dict,  # Best appraisal result
            'best_validation': dict,  # Validation of best appraisal
            'iterations': list[dict],  # All iteration history with metrics
            'final_status': str,  # "passed" | "max_iterations_reached" | "failed"
            'iteration_count': int,  # Total iterations performed
            'improvement_trajectory': list[float],  # Quality scores per iteration
        }

    Raises:
        SchemaLoadError: If appraisal.schema.json cannot be loaded or is invalid
        ValueError: If schema validation fails on any iteration
        LLMProviderError: If LLM calls fail
        UnsupportedPublicationType: If publication_type not in {interventional_trial, observational_analytic, evidence_synthesis, prediction_prognosis, editorials_opinion}

    Example:
        >>> appraisal_result = run_appraisal_with_correction(
        ...     extraction_result=extraction,
        ...     classification_result=classification,
        ...     llm_provider="openai",
        ...     file_manager=file_mgr,
        ...     max_iterations=3
        ... )
        >>> appraisal_result['final_status']
        'passed'
        >>> appraisal_result['best_appraisal']['risk_of_bias']['overall']
        'Some concerns'
    """
```

#### Helper Functions

```python
def run_appraisal(
    extraction_result: dict,
    publication_type: str,
    llm_provider: str,
    appraisal_schema: dict,
) -> dict:
    """
    Run single appraisal (no iteration).

    Routes to appropriate prompt based on publication_type using _get_appraisal_prompt_name().

    Returns: appraisal JSON

    Raises:
        UnsupportedPublicationType: If publication_type not supported for appraisal
    """

def _get_appraisal_prompt_name(publication_type: str) -> str:
    """
    Map publication_type to appraisal prompt filename.

    Args:
        publication_type: Classification result publication type

    Returns:
        Prompt filename (without .txt extension)

    Raises:
        UnsupportedPublicationType: If publication_type has no appraisal support

    Mapping:
        - interventional_trial → Appraisal-interventional
        - observational_analytic → Appraisal-observational
        - evidence_synthesis → Appraisal-evidence-synthesis
        - prediction_prognosis → Appraisal-prediction
        - editorials_opinion → Appraisal-editorials

    Note: Classification type 'overig' is not supported and will raise exception.
    """

def validate_appraisal(
    appraisal_result: dict,
    extraction_result: dict,
    appraisal_schema: dict,
    llm_provider: str,
) -> dict:
    """
    Validate appraisal JSON using Appraisal-validation.txt prompt.

    Checks:
    - Logical consistency (overall = worst domain)
    - Completeness (all domains, all outcomes)
    - Evidence support (rationales match extraction)
    - Schema compliance (enums, required fields)

    Returns: validation report JSON
    """

def correct_appraisal(
    appraisal_result: dict,
    validation_report: dict,
    extraction_result: dict,
    appraisal_schema: dict,
    llm_provider: str,
) -> dict:
    """
    Correct appraisal JSON using Appraisal-correction.txt prompt.

    Fixes issues from validation_report:
    - Logical inconsistencies
    - Missing domains/outcomes
    - Weak evidence support
    - Schema violations

    Returns: corrected appraisal JSON
    """

def select_best_appraisal_iteration(iterations: list[dict]) -> dict:
    """
    Select best appraisal iteration using quality_score ranking.

    Primary ranking metric: quality_score (weighted composite)
        quality_score = 0.35 * logical_consistency_score
                      + 0.25 * completeness_score
                      + 0.25 * evidence_support_score
                      + 0.15 * schema_compliance_score

    Tie-breakers (in order):
        1. No critical_issues (mandatory filter)
        2. Highest completeness_score
        3. Lowest iteration number (prefer earlier success)

    Returns: best iteration dict with appraisal + validation
    """
```

### 4. File Management

**Appraisal File Naming** (consistent with extraction/validation):

```
tmp/
  ├── paper-extraction0.json          # Initial extraction
  ├── paper-validation0.json          # Validation of extraction
  ├── paper-extraction1.json          # Corrected extraction
  ├── paper-validation1.json
  ├── paper-extraction-best.json      # Selected best extraction
  ├── paper-validation-best.json
  │
  ├── paper-appraisal0.json          # Initial appraisal (NEW)
  ├── paper-appraisal_validation0.json  # Validation of appraisal (NEW)
  ├── paper-appraisal1.json          # Corrected appraisal (NEW)
  ├── paper-appraisal_validation1.json
  ├── paper-appraisal-best.json      # Selected best appraisal (NEW)
  └── paper-appraisal_validation-best.json
```

**Note**: Files are stored in `tmp/` directory with pattern `{pdf_filename}-{step}{iteration_num}.json` for iterations and `{pdf_filename}-{step}-best.json` for best selections. This matches the existing PipelineFileManager implementation exactly.

**File Manager Methods** (extend existing PipelineFileManager):

```python
class PipelineFileManager:
    # ... existing methods ...

    def save_appraisal_iteration(
        self,
        iteration: int,
        appraisal_result: dict,
        validation_result: dict | None = None,
    ) -> tuple[Path, Path | None]:
        """Save appraisal iteration files"""

    def load_appraisal_iteration(
        self,
        iteration: int,
    ) -> tuple[dict, dict | None]:
        """Load appraisal iteration files"""

    def save_best_appraisal(
        self,
        appraisal_result: dict,
        validation_result: dict,
    ) -> tuple[Path, Path]:
        """Save selected best appraisal"""

    def get_appraisal_iterations(self) -> list[dict]:
        """Get all appraisal iterations with metadata"""
```

### 5. Schema Loader Integration

**No changes needed** - `appraisal.schema.json` is self-contained (no $refs to common.schema.json).

Direct loading:
```python
from pathlib import Path
import json

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"
appraisal_schema_path = SCHEMAS_DIR / "appraisal.schema.json"

with open(appraisal_schema_path) as f:
    appraisal_schema = json.load(f)
```

**No bundling required** ✅

### 6. Diagnostic Study Routing (Special Case)

**Context**: Diagnostic accuracy studies have a unique workflow:

- **Extraction**: Uses diagnostic-specific schema with QUADAS-2/QUADAS-C tools
- **Classification**: May output `diagnostic` as publication_type (not in standard 5 types)
- **Appraisal**: Shares the **prediction_prognosis prompt** (`Appraisal-prediction.txt`)

**Rationale**: PROBAST (for prediction models) and QUADAS (for diagnostic tests) have similar structure:
- Both assess Risk of Bias and Applicability across multiple domains
- Both evaluate performance (discrimination for prediction, sensitivity/specificity for diagnostic)
- Shared prompt handles both via tool-specific language

**Implementation**:
```python
# In _get_appraisal_prompt_name():
if publication_type == 'diagnostic':
    return 'Appraisal-prediction'  # Shared with prediction_prognosis
```

**Schema handling**:
- `study_type` in extraction: `"diagnostic"`
- `study_type` in appraisal output: `"diagnostic"` (preserved from extraction)
- `tool.name` in appraisal: `"QUADAS-2"` or `"QUADAS-C"` (diagnostic-specific)
- Prompt used: `Appraisal-prediction.txt` (shared with PROBAST)

**Note**: This is distinct from `prediction_prognosis` classification output, which uses the same prompt but for prediction models (PROBAST tool).

---

## Implementatie Fases

### Fase 1: Core Appraisal Loop (Orchestrator) ✅ COMPLEET
**Goal**: Implement iterative appraisal with validation/correction

**Deliverables**:
- [x] `src/pipeline/orchestrator.py`:
  - [x] `run_appraisal_with_correction()` (main function) - lines 2263-2605
  - [x] `_run_appraisal_step()` (single appraisal with routing) - lines 1879-2007
  - [x] `_run_appraisal_validation_step()` (validation wrapper) - lines 2010-2130
  - [x] `_run_appraisal_correction_step()` (correction wrapper) - lines 2133-2260
  - [x] `_select_best_appraisal_iteration()` (best selection) - lines 641-708
- [x] Prompt routing logic (6 publication types → 5 appraisal prompts, diagnostic shares prediction)
- [x] Quality threshold evaluation - `is_appraisal_quality_sufficient()` lines 574-638
- [x] Iteration loop with stop criteria (max iterations + quality degradation)
- [x] `src/schemas_loader.py`: Added "appraisal" to SCHEMA_MAPPING
- [x] `src/pipeline/orchestrator.py`: Added appraisal dispatch to `run_single_step()`
- [x] `src/pipeline/orchestrator.py`: Updated `_validate_step_dependencies()` for appraisal
- [x] `src/pipeline/orchestrator.py`: Fixed `_detect_quality_degradation()` for appraisal metrics

**Testing**:
- [x] Unit tests: `test_execution_screen.py` updated for 4-step pipeline
- [x] Integration test: full loop with mock LLM responses (✅ COMPLETE - 12 tests in `tests/integration/test_appraisal_full_loop.py`)

**Acceptance**:
- [x] Appraisal loop runs to completion (code complete, 12 integration tests passing)
- [x] Best iteration selected correctly (weighted quality_score)
- [x] Quality thresholds enforced (4 subscores + critical issues)
- [x] All code quality checks pass (make format, make lint, make test-fast)

### Fase 2: Prompt Development ✅ COMPLEET
**Goal**: Write new validation and correction prompts

**Deliverables**:

| Prompt | Doel | Kerninput | Output | Status |
| --- | --- | --- | --- | --- |
| `prompts/Appraisal-validation.txt` | Controleert appraisal op logische consistentie, volledigheid, evidence support en schema-compliance | `APPRAISAL_JSON`, `EXTRACTION_JSON`, `APPRAISAL_SCHEMA` | Validation report met scores, issues-lijst en overall status | ✅ COMPLEET (224 lines) |
| `prompts/Appraisal-correction.txt` | Corrigeert appraisal o.b.v. validation issues, vult ontbrekende elementen aan en herstelt schemafouten | `VALIDATION_REPORT`, `ORIGINAL_APPRAISAL`, `EXTRACTION_JSON`, `APPRAISAL_SCHEMA` | Verbeterde appraisal JSON klaar voor her-validatie | ✅ COMPLEET (389 lines) |

**Prompt Features**:
- [x] **Validation prompt (224 lines)**:
  - 4 verification categories: logical consistency (35%), completeness (25%), evidence support (25%), schema compliance (15%)
  - Tool-specific rules (RoB 2, ROBINS-I, PROBAST, AMSTAR 2, ROBIS)
  - Weighted quality_score formula
  - Critical issues handling (overrides all other checks)
  - Overall_status logic (passed/warning/failed)
- [x] **Correction prompt (389 lines)**:
  - 8 HARD RULES sections (schema compliance, source fidelity, tool-specific rules, GRADE consistency, etc.)
  - 6-step correction workflow
  - Tool-specific checklists for verification
  - UTF-8 character encoding instructions
  - Target state with validation thresholds
- [x] `src/prompts.py`: Loader functions ready (lines 151-236)

**Testing**:
- [x] Manual validation with test cases (✅ COVERED by integration tests: all 5 study types tested with edge cases)
- [x] Verify validation catches known errors (✅ COVERED by `test_appraisal_quality.py` and integration tests)
- [x] Verify correction fixes validation issues (✅ COVERED by correction iteration tests in `test_appraisal_full_loop.py`)

**Acceptance**:
- [x] Prompts created with comprehensive instructions
- [x] Validation prompt identifies all 4 issue categories
- [x] Correction prompt includes tool-specific workflows
- [x] Prompts tested with all 5 study types (✅ COVERED by integration tests: interventional, observational, evidence_synthesis, prediction, editorials)

### Fase 3: File Management & Logging ✅ COMPLEET
**Goal**: Save/load appraisal iterations with full traceability

**Deliverables**:
- [x] Extend `PipelineFileManager`:
  - `save_appraisal_iteration()`
  - `load_appraisal_iteration()`
  - `save_best_appraisal()`
  - `get_appraisal_iterations()`
- [x] Iteration numbering (paper-appraisal0.json, paper-appraisal_validation0.json, etc.)
- [x] Best file naming (paper-appraisal-best.json, paper-appraisal_validation-best.json)
- [x] Logging: iteration metrics, improvement trajectory (console output + metadata file)

**Testing**:
- File creation/loading for all iterations
- Concurrent access safety
- Directory structure validation

**Acceptance**:
- All iterations saved met correcte namen (`tmp/<id>-appraisal{n}.json`)
- Load functions halen juiste data terug
- Logs tonen iteration progress (console + `_pipeline_metadata`)

### Fase 4: Backward Compatibility
**Goal**: Support standalone appraisal (no iteration) for legacy/manual use

**Deliverables**:
- [x] `run_appraisal_single_pass()` helper (no correction loop)
- [x] Flag: `enable_iterative_correction: bool` (default: True) expose via CLI `--appraisal-single-pass` + Streamlit toggle
- [x] Backward-compatible file naming (`paper-appraisal.json` / `paper-appraisal_validation.json`)

**Testing**:
- Single-pass appraisal without correction
- CLI/Streamlit runs met én zonder iteraties
- Legacy file readers herkennen nog steeds de klassieke bestandsnamen

**Acceptance**:
- Users can run single appraisal if desired
- Existing scripts/notebooks still work
- Documentation covers beide modes (README + dit document)

### Fase 5: UI Integration (Streamlit) ✅ COMPLEET
**Goal**: Add appraisal step to Streamlit execution screen

**Deliverables**:
- [x] New execution step: "Appraisal" (after Validation/Correction)
- [x] Real-time progress updates during iterations
- [x] Display appraisal results:
  - Risk of bias summary (overall + domains)
  - GRADE certainty per outcome
  - Tool used (RoB 2, ROBINS-I, PROBAST, AMSTAR 2)
  - Bottom line for podcast
- [x] Iteration history visualization (table + line chart)
- [x] Manual re-run option (button reruns appraisal from UI)

**UI Mock**:
```
┌─────────────────────────────────────────────────────┐
│ 5. CRITICAL APPRAISAL                        ✅     │
├─────────────────────────────────────────────────────┤
│ Tool: RoB 2 (Parallel RCT, 2019-08-22)             │
│                                                     │
│ Risk of Bias: Some concerns                        │
│   • Randomization process: Low risk               │
│   • Deviations: Low risk                          │
│   • Missing outcome data: Some concerns           │
│   • Measurement: Low risk                         │
│   • Selection of reported result: Low risk        │
│                                                     │
│ GRADE Certainty (Primary Outcome):                │
│   • Pain at 24h: Moderate ⬇️⬇️                     │
│     Downgrades: Risk of bias (-1), Imprecision (-1)│
│                                                     │
│ Iterations: 2 (quality score: 0.94)               │
│ [View Details] [View Iteration History]           │
└─────────────────────────────────────────────────────┘
```

**Testing**:
- UI updates in real-time during appraisal
- Results display renders for all study types (covered via unit/UI tests)
- Iteration history accessible via table + chart; manual rerun tested interactief

**Acceptance**:
- Appraisal step integrated in execution flow
- Results clearly presented met risico/GRADE/bottom line
- Users can review iteration history en re-run appraisal

### Fase 6: CLI Support ✅ COMPLEET
**Goal**: Add appraisal step to CLI pipeline

**Deliverables**:
- [x] `run_pipeline.py`:
  - New step: `--step appraisal`
  - Integration in full pipeline run (ALL_PIPELINE_STEPS include appraisal)
  - Progress output voor iteraties + RoB/GRADE samenvatting
- [x] CLI output formatting (status + iteration metrics)
- [x] Error handling en user feedback (statusmeldingen, best iteration info)

**Example Usage**:
```bash
# Run full pipeline with appraisal
python run_pipeline.py paper.pdf --llm openai

# Run appraisal only (requires extraction)
python run_pipeline.py paper.pdf --step appraisal --llm openai

# Run with custom iteration limit
python run_pipeline.py paper.pdf --appraisal-max-iter 5
```

**Testing**:
- Handmatige CLI runs + unit-tests voor run_single_step (single-pass/iteratief)
- Foutpaden (TypeError) opgelost doordat signature extra args accepteert
- Output formatting beschreven in README + docs/appraisal.md

**Acceptance**:
- CLI ondersteunt appraisal (inclusief custom thresholds/iterations en single-pass modus)
- Full pipeline voert appraisal standaard uit
- Documentatie (README + docs/appraisal.md) bijgewerkt

### Fase 7: Testing & Documentation ✅ COMPLEET
**Goal**: Comprehensive testing and documentation

**Deliverables**:
- [x] Unit tests:
  - Appraisal routing/quality helpers (`tests/unit/test_appraisal_functions.py`, `test_appraisal_quality.py`)
  - Single-pass toggle coverage toegevoegd
  - File management helpers (`tests/unit/test_file_manager.py`)
- [x] Integration tests:
  - `tests/integration/test_appraisal_full_loop.py` (5 study types, max-iter/quality branches)
- [x] Documentation:
  - README sectie “Running the appraisal step”
  - `docs/appraisal.md` met volledige gids
  - Feature doc en changelog geüpdatet
- [x] CHANGELOG entries en release notes bijwerkt
- [x] Test data/fixtures:
  - Fixtures in `tests/integration/test_appraisal_full_loop.py` voor elke study type
  - JSON snippets in `docs/appraisal.md`

**Teststrategie**:
1. **Unit Tests**: Each function isolated
2. **Integration Tests**: Full appraisal loop
3. **End-to-End Tests**: CLI + UI with real PDFs
4. **Regression Tests**: Ensure extraction/validation still work

**Acceptance**:
- Test coverage ≥ 90% for appraisal code
- All tests pass
- Documentation complete and accurate

---

## Testing Strategie

### Test Cases by Study Type

#### 1. Interventional Trial (RoB 2)
**Test PDF**: RCT with clear RoB domains (e.g., parallel-group trial with patient-reported outcomes)

**Expected Output**:
- `tool.name`: "RoB 2"
- `tool.variant`: "parallel-RCT" (or "cluster-RCT", "crossover-RCT" depending on design)
- `risk_of_bias.domains`: 5 domains assessed:
  1. randomization_process (judgement + rationale + source_refs)
  2. deviations_from_intended_interventions
  3. missing_outcome_data
  4. measurement_of_outcome
  5. selection_of_reported_result
- `risk_of_bias.overall`: Worst domain judgement (e.g., "Some concerns" if any domain has concerns)
- `grade_per_outcome`: Array with GRADE rating for each outcome (starts at "High" certainty for RCTs, downgraded if RoB issues)
- Rationales: ≥50 chars, domain-specific keywords present, source_refs to extraction

**Validation Issues to Test**:
- Overall judgement inconsistent with domain (e.g., overall="Low risk" but domain="High risk")
- Missing domain assessment (only 4 of 5 domains present)
- Rationale missing/sparse (<50 chars or boilerplate "Not reported")
- Incorrect enum casing ("low risk" vs "Low risk")
- GRADE inconsistency (RoB "High risk" but no GRADE downgrade for risk of bias)

#### 2. Observational Analytic (ROBINS-I)
**Test PDF**: Cohort study with confounding issues
**Expected**:
- Tool: ROBINS-I
- 7 domains assessed
- Causal strategy populated (PS matching, IPTW, etc.)
- GRADE per outcome (starts at Low for observational)

#### 3. Evidence Synthesis (AMSTAR 2 + ROBIS)
**Test PDF**: Meta-analysis with I² and funnel plot
**Expected**:
- Tools: AMSTAR 2 + ROBIS
- AMSTAR 2: 16 items, critical items identified
- ROBIS: 4 domains
- Synthesis quality: heterogeneity, publication bias

#### 4. Prediction Prognosis (PROBAST)
**Test PDF**: Prediction model with C-statistic and calibration
**Expected**:
- Tool: PROBAST
- 4 domains × (risk of bias + applicability)
- Performance review: discrimination, calibration, clinical utility

#### 5. Editorials Opinion (Argument Quality)
**Test PDF**: Editorial with multiple claims
**Expected**:
- Argument quality per claim
- Evidence type classification
- Support strength assessment
- Counterarguments considered

### Edge Cases

1. **Max Iterations Reached**: Quality never sufficient → select best
2. **Schema Validation Failure**: Appraisal JSON invalid → correction fixes
3. **Missing Extraction Data**: Incomplete extraction → appraisal notes limitations
4. **Tool Mismatch**: RCT classified as observational → correct tool selected

### Performance Metrics

- **Appraisal time**: < 30s per iteration (GPT-4o)
- **Validation time**: < 15s per iteration
- **Correction time**: < 30s per iteration
- **Total appraisal loop**: < 2 minutes for 3 iterations

---

## Acceptatiecriteria

### Functioneel

1. **Appraisal runs voor alle 5 study types** met correcte toolselectie, inclusief gedeelde PROBAST-prompt voor prediction_prognosis + diagnostic
2. **Iterative correction** improves quality scores across iterations
3. **Best iteration selected** based on validation scores
4. **Quality thresholds enforced** (logical consistency, completeness, evidence support, schema compliance)
5. **File management** saves all iterations with correct naming
6. **UI integration** displays appraisal results clearly
7. **CLI support** runs appraisal step standalone or in full pipeline
8. **Backward compatibility** supports standalone appraisal without iteration

### Technisch

1. **No schema bundling** required (appraisal.schema.json is self-contained)
2. **Prompt routing** correctly maps publication_type to appraisal prompt
3. **Validation prompt** identifies all issue categories
4. **Correction prompt** fixes issues without breaking schema en houdt rekening met gedeelde prediction/diagnostic logica
5. **Error handling** graceful failures with clear messages
6. **Test coverage** ≥ 90% voor appraisal code
7. **Documentation** complete (README, ARCHITECTURE, API, appraisal guide)

### Kwaliteit

1. **Logical consistency**: Overall judgement matches worst domain (RoB 2/ROBINS-I rule)
2. **Completeness**: All required domains assessed, all outcomes appraised
3. **Evidence support**: Rationales reference extraction data with source_refs
4. **Schema compliance**: Enum values exact, required fields present
5. **GRADE alignment**: Downgrades consistent with RoB assessment

### Gebruikerservaring

1. **Clear progress indicators** during appraisal iterations
2. **Intuitive results display** (risk of bias summary, GRADE ratings)
3. **Iteration history accessible** for transparency
4. **Bottom line generated** for podcast script integration
5. **Error messages actionable** when appraisal fails

---

## Risico's en Mitigaties

### Risico 1: LLM Inconsistent Tool Application
**Beschrijving**: LLM applies RoB 2 rules incorrectly (e.g., doesn't follow "worst domain wins")

**Impact**: High - appraisal results unreliable

**Mitigatie**:
- Strong validation prompt with explicit rules
- Correction prompt enforces tool-specific algorithms
- Unit tests verify rule enforcement
- Consider rule-based post-processing for critical consistency checks

### Risico 2: Extraction Quality Affects Appraisal
**Beschrijving**: Poor extraction data leads to poor appraisal (garbage in, garbage out)

**Impact**: Medium - appraisal reflects extraction errors, not study quality

**Mitigatie**:
- Log warning if extraction quality_score < 0.90, but proceed with appraisal (don't block)
- Flag low-confidence appraisals for manual review (add `extraction_quality_warning` field)
- Appraisal prompt includes PDF_CONTENT (optional) for direct verification when extraction quality marginal
- Validation checks extraction-appraisal alignment (evidence support score)
- Document extraction dependencies in appraisal metadata and warnings

### Risico 3: Validation Too Lenient/Strict
**Beschrijving**: Quality thresholds not calibrated → too many iterations or false passes

**Impact**: Medium - wasted compute time or low-quality appraisals

**Mitigatie**:
- Default thresholds based on pilot testing
- Configurable thresholds for user tuning
- Logging shows improvement trajectory for threshold adjustment
- A/B testing on sample papers to calibrate

### Risico 4: Prompt Token Limits
**Beschrijving**: Large extraction + PDF_CONTENT + schema exceeds LLM context window

**Impact**: Medium - appraisal fails for complex papers

**Mitigatie**:
- Use extraction JSON only (no PDF_CONTENT) by default
- Truncate extraction to essential fields for appraisal
- Use long-context models (GPT-4o, Claude 3.5 Sonnet)
- Document max paper complexity supported

### Risico 5: Tool Coverage Gaps
**Beschrijving**: Some study designs don't map cleanly to tools (e.g., pragmatic trials, quasi-experimental)

**Impact**: Low - tool selection suboptimal for edge cases

**Mitigatie**:
- Appraisal prompt includes tool variant field (e.g., "pragmatic RCT")
- Fallback to closest tool with notes in applicability
- Document tool limitations in appraisal guide
- Future: add ROBINS-I-E for non-randomized experiments

### Risico 6: GRADE Downgrades Subjective
**Beschrijving**: LLM interpretation of imprecision/inconsistency varies

**Impact**: Medium - GRADE ratings inconsistent across similar studies

**Mitigatie**:
- Validation checks GRADE consistency with extraction metrics (CI width, I²)
- Correction prompt quantifies downgrades (e.g., "Imprecision: CI crosses null and MID")
- Consider rule-based GRADE assistance (CI width → imprecision)
- Document GRADE criteria in prompt with examples

---

## Open Vragen & Afhankelijkheden

Momenteel geen open vragen. Thresholds zijn vastgesteld, benodigde LLM-accounts zijn beschikbaar, UI-ontwerp volgt bestaande validatie/correctie-stijl en stakeholdercommunicatie valt binnen de bestaande change_management-afspraken.

---

## Volgende Stappen (na Feature Document Approval)

1. **Review Feature Document** met stakeholders
2. **Prioritize Phases** (suggested: 1 → 2 → 3 → 7, defer 4-6 for initial release)
3. **Start Phase 1**: Implement core appraisal loop in orchestrator
4. **Draft Prompts**: Write Appraisal-validation.txt and Appraisal-correction.txt
5. **Pilot Testing**: Test with sample papers (1 per study type)
6. **Iterate**: Refine prompts and thresholds based on pilot results

---

## Referenties

### Appraisal Tools Documentation
- **RoB 2**: https://www.riskofbias.info/welcome/rob-2-0-tool (Cochrane, 2019)
- **ROBINS-I**: https://www.riskofbias.info/welcome/robins-i-tool (Sterne et al., 2016)
- **PROBAST**: https://www.probast.org/ (Wolff et al., 2019)
- **AMSTAR 2**: https://amstar.ca/Amstar-2.php (Shea et al., 2017)
- **ROBIS**: https://www.bristol.ac.uk/population-health-sciences/projects/robis/ (Whiting et al., 2016)
- **GRADE**: https://www.gradeworkinggroup.org/ (Guyatt et al., 2008)

### Related Features
- `features/iterative-validation-correction.md` - Template for this feature
- `ARCHITECTURE.md` - Pipeline component documentation
- `schemas/appraisal.schema.json` - Appraisal output schema
- `prompts/Appraisal-*.txt` - Study type-specific appraisal prompts
