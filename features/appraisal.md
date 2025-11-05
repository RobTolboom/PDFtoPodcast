# Feature: Critical Appraisal met Iteratieve Validation & Correction

**Status**: Planned - Feature Document Complete, Implementation Pending
**Branch**: `feature/appraisal`
**Created**: 2025-11-04
**Updated**: 2025-11-04 (v1.0 - Initial specification)
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

### User Stories

- Als clinicus wil ik direct zien hoe betrouwbaar de gevonden studies zijn zodat ik sneller evidence kan wegen tijdens MDO’s.
- Als data-analist wil ik appraisal-scores en rationales in JSON zodat ik downstream analyses en dashboards kan voeden zonder handwerk.
- Als product owner wil ik automatisch inzicht in kwaliteitsproblemen zodat ik kan beslissen of een podcastscript door mag naar publicatie.

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
          ├─ prediction_prognosis | diagnostic → Appraisal-prediction.txt (PROBAST)
           └─ editorials_opinion → Appraisal-editorials.txt (Argument quality)
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
2. **Study Type Routing**: 5 publication types → 5 appraisal prompts (tool-specific; diagnostic valt samen met prediction)
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
- ✅ **Study type support**: 6 types (interventional, observational, diagnostic, prediction_prognosis, evidence_synthesis, editorial_opinion)
  - Note: Pipeline routeert diagnostic studies via prediction_prognosis (zelfde prompt)
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
  "study_type": "interventional|observational|...",
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
   - Tool choice appropriate for study design? (RCT → RoB 2, Nonrandomized → ROBINS-I)
   - Predicted bias direction consistent with domain rationale?

2. **Completeness Assessment**
   - All required domains assessed? (RoB 2: 5, ROBINS-I: 7, PROBAST: 4, AMSTAR 2: 16)
   - All outcomes from extraction appraised? (grade_per_outcome matches outcomes[])
   - Rationales present and substantive? (>20 chars, not boilerplate)
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

**Scoreberekening**:
- Iedere subscoreschaal loopt van 0.0-1.0 en wordt afgerond op twee decimalen in het rapport.
- `quality_score = 0.35 * logical_consistency_score + 0.25 * completeness_score + 0.25 * evidence_support_score + 0.15 * schema_compliance_score`.
- Zodra `critical_issues > 0` wordt `overall_status` direct `failed` en wordt `quality_score` begrensd op maximaal 0.69 (iteratie kan niet als beste geselecteerd worden).
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
        max_iterations: Maximum correction attempts (default: 3)
            Example: max_iterations=3 means up to 4 total iterations (iter 0,1,2,3)
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

    Routes to appropriate prompt:
    - interventional_trial → Appraisal-interventional.txt
    - observational_analytic → Appraisal-observational.txt
    - evidence_synthesis → Appraisal-evidence-synthesis.txt
    - prediction_prognosis → Appraisal-prediction.txt
    - editorials_opinion → Appraisal-editorials.txt

    Returns: appraisal JSON
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
    Select best appraisal iteration based on validation scores.

    Ranking:
    1. Highest logical_consistency_score (most important)
    2. Lowest critical_issues
    3. Highest completeness_score
    4. Highest evidence_support_score

    Returns: best iteration dict with appraisal + validation
    """
```

### 4. File Management

**Appraisal File Naming** (consistent with extraction/validation):

```
/output/<pdf_name>/
  ├── extraction_iter_0.json          # Initial extraction
  ├── validation_iter_0.json          # Validation of extraction
  ├── extraction_iter_1.json          # Corrected extraction
  ├── validation_iter_1.json
  ├── extraction_best.json            # Selected best extraction
  ├── validation_best.json
  │
  ├── appraisal_iter_0.json          # Initial appraisal (NEW)
  ├── appraisal_validation_iter_0.json  # Validation of appraisal (NEW)
  ├── appraisal_iter_1.json          # Corrected appraisal (NEW)
  ├── appraisal_validation_iter_1.json
  ├── appraisal_best.json            # Selected best appraisal (NEW)
  └── appraisal_validation_best.json
```

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

---

## Implementatie Fases

### Fase 1: Core Appraisal Loop (Orchestrator)
**Goal**: Implement iterative appraisal with validation/correction

**Deliverables**:
- [ ] `src/pipeline/orchestrator.py`:
  - `run_appraisal_with_correction()` (main function)
  - `run_appraisal()` (single appraisal with routing)
  - `validate_appraisal()` (validation wrapper)
  - `correct_appraisal()` (correction wrapper)
  - `select_best_appraisal_iteration()` (best selection)
- [ ] Prompt routing logic (5 publication types → 5 appraisal prompts)
- [ ] Quality threshold evaluation
- [ ] Iteration loop with stop criteria

**Testing**:
- Unit tests: each helper function
- Integration test: full loop with mock LLM responses

**Acceptance**:
- Appraisal loop runs to completion
- Best iteration selected correctly
- Quality thresholds enforced

### Fase 2: Prompt Development
**Goal**: Write new validation and correction prompts

**Deliverables**:

| Prompt | Doel | Kerninput | Output |
| --- | --- | --- | --- |
| `prompts/Appraisal-validation.txt` | Controleert appraisal op logische consistentie, volledigheid, evidence support en schema-compliance | `APPRAISAL_JSON`, `EXTRACTION_JSON`, `APPRAISAL_SCHEMA` | Validation report met scores, issues-lijst en overall status |
| `prompts/Appraisal-correction.txt` | Corrigeert appraisal o.b.v. validation issues, vult ontbrekende elementen aan en herstelt schemafouten | `VALIDATION_REPORT`, `ORIGINAL_APPRAISAL`, `EXTRACTION_JSON`, `APPRAISAL_SCHEMA` | Verbeterde appraisal JSON klaar voor her-validatie |

**Testing**:
- Manual validation with test cases (RCT with RoB 2 issues, meta-analysis with AMSTAR issues)
- Verify validation catches known errors
- Verify correction fixes validation issues

**Acceptance**:
- Validation prompt identifies all issue types
- Correction prompt fixes issues without breaking schema
- Prompts work with all 5 study types

### Fase 3: File Management & Logging
**Goal**: Save/load appraisal iterations with full traceability

**Deliverables**:
- [ ] Extend `PipelineFileManager`:
  - `save_appraisal_iteration()`
  - `load_appraisal_iteration()`
  - `save_best_appraisal()`
  - `get_appraisal_iterations()`
- [ ] Iteration numbering (appraisal_iter_0.json, etc.)
- [ ] Best file naming (appraisal_best.json)
- [ ] Logging: iteration metrics, improvement trajectory

**Testing**:
- File creation/loading for all iterations
- Concurrent access safety
- Directory structure validation

**Acceptance**:
- All iterations saved with correct naming
- Load functions retrieve correct data
- Logs show iteration progress

### Fase 4: Backward Compatibility
**Goal**: Support standalone appraisal (no iteration) for legacy/manual use

**Deliverables**:
- [ ] `run_appraisal()` standalone function (no correction loop)
- [ ] Flag: `enable_iterative_correction: bool` (default: True)
- [ ] Backward-compatible file naming (appraisal.json without iterations)

**Testing**:
- Standalone appraisal without validation/correction
- Pipeline runs with/without iterative appraisal
- File structure compatible with legacy code

**Acceptance**:
- Users can run single appraisal if desired
- Existing scripts/notebooks still work
- Documentation covers both modes

### Fase 5: UI Integration (Streamlit)
**Goal**: Add appraisal step to Streamlit execution screen

**Deliverables**:
- [ ] New execution step: "Appraisal" (after Validation/Correction)
- [ ] Real-time progress updates during iterations
- [ ] Display appraisal results:
  - Risk of bias summary (overall + domains)
  - GRADE certainty per outcome
  - Tool used (RoB 2, ROBINS-I, PROBAST, AMSTAR 2)
  - Bottom line for podcast
- [ ] Iteration history visualization
- [ ] Manual re-run option

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
- Results display correctly for all 5 study types
- Iteration history accessible

**Acceptance**:
- Appraisal step integrated in execution flow
- Results clearly presented
- Users can review iteration history

### Fase 6: CLI Support
**Goal**: Add appraisal step to CLI pipeline

**Deliverables**:
- [ ] `run_pipeline.py`:
  - New step: `--step appraisal`
  - Integration in full pipeline run
  - Progress output for iterations
- [ ] CLI output formatting (summary table)
- [ ] Error handling and user feedback

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
- CLI runs appraisal step successfully
- Error messages clear and actionable
- Output formatting readable

**Acceptance**:
- CLI supports appraisal step
- Full pipeline includes appraisal
- Documentation updated

### Fase 7: Testing & Documentation
**Goal**: Comprehensive testing and documentation

**Deliverables**:
- [ ] Unit tests:
  - Appraisal routing (5 study types)
  - Validation scoring
  - Correction logic
  - Best iteration selection
  - File management
- [ ] Integration tests:
  - Full appraisal loop with mock LLM
  - All 5 study types
  - Edge cases (max iterations, validation failures)
- [ ] Documentation:
  - Update `README.md` (appraisal step description)
  - Update `ARCHITECTURE.md` (appraisal component)
  - Update `API.md` (new orchestrator functions)
  - Add `docs/appraisal.md` (detailed guide with tool descriptions)
- [ ] CHANGELOG.md bijwerken onder “Unreleased” en de verplichte acties uit `change_management` in `CLAUDE.md` uitvoeren (inclusief communicatie naar stakeholders).
- [ ] Test data:
  - Sample appraisals for each study type
  - Known issues for validation testing

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
**Test PDF**: RCT with clear RoB domains
**Expected**:
- Tool: RoB 2
- 5 domains assessed
- Overall judgement = worst domain
- GRADE per outcome (starts at High for RCT)

**Validation Issues to Test**:
- Overall judgement inconsistent with domain
- Missing domain assessment
- Rationale missing/sparse
- Incorrect enum casing ("low risk" vs "Low risk")

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
- Require extraction quality_score ≥ 0.90 before appraisal
- Appraisal prompt includes PDF_CONTENT (optional) for direct verification
- Validation checks extraction-appraisal alignment
- Document extraction dependencies in appraisal warnings

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
