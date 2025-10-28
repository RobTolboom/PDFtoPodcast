# Feature: Iterative Validation & Correction Loop

**Status**: Planning
**Branch**: `feature/iterative-validation-correction`
**Created**: 2025-01-28
**Author**: Rob Tolboom (met Claude Code)

---

## Probleemstelling

### Huidige Situatie

De pipeline heeft aparte, losgekoppelde stappen voor validatie en correctie:

- **Validatie** (stap 3):
  - Schema validatie (structurele checks)
  - LLM validatie (semantische checks, completeness, accuracy)
  - Output: validatierapport met quality scores
  - **Probleem**: Als kwaliteit onvoldoende is → gebruiker moet handmatig correctiestap selecteren

- **Correctie** (stap 4):
  - Moet handmatig worden gekozen door gebruiker
  - Voert één correctiepoging uit
  - **Probleem**: Geen automatische re-validatie na correctie
  - **Probleem**: Als correctie onvoldoende is → geen tweede poging mogelijk

### Pijnpunten

1. **Handmatige interventie vereist**: Gebruiker moet pipeline onderbreken en opnieuw starten
2. **Geen iteratie**: Eén correctiepoging, daarna klaar (ook als nog steeds onvoldoende)
3. **Geen feedback loop**: Correctie → geen validatie → weten niet of het beter is geworden
4. **Suboptimale kwaliteit**: Als eerste correctie niet voldoende is, blijft output onder threshold
5. **Inefficiënt**: Meerdere handmatige runs nodig voor complexe papers

### Motivatie

Medische literatuurextractie vereist **hoge kwaliteit** (>90% compleet, >95% accuraat) voor betrouwbare analyse. Sommige papers zijn complex en vereisen meerdere correctie-iteraties om deze kwaliteit te bereiken. Automatische iteratie:

- ✅ Verhoogt output kwaliteit
- ✅ Vermindert handmatig werk
- ✅ Geeft duidelijke feedback over vooruitgang
- ✅ Stopt automatisch bij voldoende kwaliteit OF maximum iteraties

---

## Gewenste Situatie

### Nieuwe Workflow: Gecombineerde "Validation & Correction" Stap

```
┌─────────────────────────────────────────────────────────────┐
│  VALIDATION & CORRECTION (Iterative Loop)                   │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────┐
        │  Schema Validatie          │
        │  (Structurele checks)      │
        └────────────────────────────┘
                         │
                         ▼
              Quality Score < 50%?
                   │          │
                  JA         NEE
                   │          │
                   ▼          ▼
              ┌──────┐   ┌────────────────────┐
              │ STOP │   │  LLM Validatie     │
              │ FAIL │   │  (Semantic checks) │
              └──────┘   └────────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────────┐
                    │  Kwaliteit Beoordeling       │
                    │  - Completeness ≥ 90%?       │
                    │  - Accuracy ≥ 95%?           │
                    │  - Schema Compliance ≥ 95%?  │
                    │  - Critical Issues = 0?      │
                    └──────────────────────────────┘
                                  │
                        ┌─────────┴─────────┐
                       JA                  NEE
                        │                   │
                        ▼                   ▼
                   ┌────────┐      ┌─────────────────┐
                   │ KLAAR  │      │ Iteraties < MAX?│
                   │   ✅   │      └─────────────────┘
                   └────────┘              │
                                  ┌────────┴────────┐
                                 JA               NEE
                                  │                 │
                                  ▼                 ▼
                      ┌──────────────────┐    ┌──────────┐
                      │  CORRECTIE       │    │ STOP     │
                      │  Iteratie #N     │    │ MAX ⚠️   │
                      └──────────────────┘    └──────────┘
                                  │
                                  ▼
                      ┌──────────────────────┐
                      │ Schema Validatie     │
                      │ (van corrected)      │
                      └──────────────────────┘
                                  │
                                  ▼
                          Schema OK?
                          │      │
                         JA     NEE
                          │      │
                          │      ▼
                          │  ┌──────┐
                          │  │ STOP │
                          │  │ FAIL │
                          │  └──────┘
                          ▼
                  ┌────────────────────┐
                  │ LLM Validatie      │
                  │ (van corrected)    │
                  └────────────────────┘
                          │
                          ▼
                  [LOOP TERUG NAAR BEOORDELING]
```

### Belangrijkste Veranderingen

1. **Automatische Iteratie**: Validatie → Correctie → Validatie → ... tot kwaliteit voldoende
2. **Configureerbare Stop Criteria**:
   - Kwaliteit thresholds (completeness, accuracy, schema compliance)
   - Maximum aantal iteraties (default: 3)
3. **Intelligente Beste Versie Selectie**: Als MAX bereikt → kies beste iteratie
4. **Volledige Traceerbaarheid**: Alle iteraties worden opgeslagen met metrics

---

## Technisch Ontwerp

### 1. API Design

#### Nieuwe High-Level Functie

```python
# src/pipeline/orchestrator.py

def run_validation_with_correction(
    pdf_path: Path,
    extraction_result: dict,
    classification_result: dict,
    llm_provider: str,
    file_manager: PipelineFileManager,
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    progress_callback: Callable | None = None,
) -> dict:
    """
    Run validation with automatic iterative correction until quality is sufficient.

    Workflow:
        1. Validate extraction (schema + LLM)
        2. If quality insufficient and iterations < max:
           - Run correction
           - Validate corrected output
           - Repeat until quality OK or max iterations reached
        3. Select best iteration based on quality metrics
        4. Return best extraction + validation + iteration history

    Args:
        pdf_path: Path to source PDF
        extraction_result: Initial extraction JSON
        classification_result: Classification result (for publication type)
        llm_provider: LLM provider name ("openai" | "claude")
        file_manager: File manager for saving iterations
        max_iterations: Maximum correction iterations (default: 3)
        quality_thresholds: Custom thresholds, defaults to:
            {
                'completeness_score': 0.90,
                'accuracy_score': 0.95,
                'schema_compliance_score': 0.95,
                'critical_issues': 0
            }
        progress_callback: Optional callback for progress updates

    Returns:
        dict: {
            'best_extraction': dict,  # Best extraction result
            'best_validation': dict,  # Validation of best extraction
            'iterations': list[dict],  # All iteration history with metrics
            'final_status': str,  # "passed" | "max_iterations_reached" | "failed"
            'iteration_count': int,  # Total iterations performed
            'improvement_trajectory': list[float],  # Quality scores per iteration
        }

    Raises:
        ValueError: If schema validation fails on any iteration
        LLMProviderError: If LLM calls fail

    Example:
        >>> result = run_validation_with_correction(
        ...     pdf_path=Path("paper.pdf"),
        ...     extraction_result=extraction,
        ...     classification_result=classification,
        ...     llm_provider="openai",
        ...     file_manager=fm,
        ...     max_iterations=3
        ... )
        >>> result['final_status']  # "passed"
        >>> len(result['iterations'])  # 2 (initial + 1 correction)
        >>> result['best_extraction']  # Best quality extraction
    """
```

#### Backward Compatibility

Bestaande functies blijven bestaan voor CLI gebruik:

```python
def run_single_step(step_name: str, ...) -> dict:
    """
    Original function - blijft werken voor CLI en directe stap-aanroepen.

    Supported step_name values:
        - STEP_VALIDATION: Single validation run (no correction)
        - STEP_CORRECTION: Single correction run (no re-validation)
        - STEP_VALIDATION_CORRECTION: New iterative workflow
    """
    if step_name == STEP_VALIDATION:
        return _run_validation_step(...)  # Unchanged
    elif step_name == STEP_CORRECTION:
        return _run_correction_step(...)  # Unchanged
    elif step_name == STEP_VALIDATION_CORRECTION:
        return run_validation_with_correction(...)
    ...
```

**Constants uitbreiding**:
```python
# Pipeline step name constants (uitbreiding)
STEP_VALIDATION_CORRECTION = "validation_correction"

ALL_PIPELINE_STEPS = [
    STEP_CLASSIFICATION,
    STEP_EXTRACTION,
    STEP_VALIDATION_CORRECTION,  # Nieuwe gecombineerde stap
    # Note: STEP_VALIDATION en STEP_CORRECTION blijven beschikbaar voor CLI
]
```

### 2. Kwaliteit Assessment

#### Thresholds Configuratie

```python
# Default thresholds (configureerbaar via settings)
DEFAULT_QUALITY_THRESHOLDS = {
    'completeness_score': 0.90,      # ≥90% van PDF data geëxtraheerd
    'accuracy_score': 0.95,          # ≥95% correcte data (max 5% fouten)
    'schema_compliance_score': 0.95, # ≥95% schema compliant
    'critical_issues': 0             # Absoluut geen kritieke fouten
}

def is_quality_sufficient(
    validation_result: dict,
    thresholds: dict = DEFAULT_QUALITY_THRESHOLDS
) -> bool:
    """
    Check if validation quality meets thresholds for stopping iteration.

    Args:
        validation_result: Validation JSON with verification_summary
        thresholds: Quality thresholds to check against

    Returns:
        bool: True if ALL thresholds are met, False otherwise

    Example:
        >>> validation = {
        ...     'verification_summary': {
        ...         'completeness_score': 0.92,
        ...         'accuracy_score': 0.98,
        ...         'schema_compliance_score': 0.97,
        ...         'critical_issues': 0
        ...     }
        ... }
        >>> is_quality_sufficient(validation)  # True
    """
    summary = validation_result.get('verification_summary', {})

    return (
        summary.get('completeness_score', 0) >= thresholds['completeness_score'] and
        summary.get('accuracy_score', 0) >= thresholds['accuracy_score'] and
        summary.get('schema_compliance_score', 0) >= thresholds['schema_compliance_score'] and
        summary.get('critical_issues', 999) <= thresholds['critical_issues']
    )
```

#### Score Definities (uit validation prompt)

| Score | Definitie | Doel | Voorbeeld |
|-------|-----------|------|-----------|
| **completeness_score** | `(Extracted data points / Total relevant PDF data)` | Meet hoeveel van de PDF is overgenomen | 0.86 = 86% compleet |
| **accuracy_score** | `(Correct values / Total extracted values)` | Meet correctheid (geen hallucinaties) | 0.99 = 99% accuraat |
| **schema_compliance_score** | `(Compliant fields / Total schema fields)` | Meet schema naleving | 1.0 = 100% compliant |
| **critical_issues** | Count of CRITICAL severity issues | Fabricatie, grote fouten, ontbrekende verplichte velden | 0 = geen kritieke fouten |

### 3. Loop Logica

```python
def run_validation_with_correction(...) -> dict:
    """Main iterative loop implementation."""

    # Initialize
    iterations = []
    current_extraction = extraction_result
    iteration_num = 0

    # Default thresholds
    if quality_thresholds is None:
        quality_thresholds = DEFAULT_QUALITY_THRESHOLDS

    while iteration_num <= max_iterations:
        # Progress callback
        _call_progress_callback(
            progress_callback,
            STEP_VALIDATION_CORRECTION,
            "validation_starting",
            {'iteration': iteration_num}
        )

        # STEP 1: Validate current extraction
        validation_result = _run_validation_step(
            extraction_result=current_extraction,
            pdf_path=pdf_path,
            max_pages=None,
            classification_result=classification_result,
            llm=get_llm_provider(llm_provider),
            file_manager=file_manager,
            progress_callback=progress_callback
        )

        # Save validation with iteration suffix
        suffix = f"_corrected{iteration_num}" if iteration_num > 0 else ""
        validation_file = file_manager.save_json(
            validation_result,
            "validation",
            status=suffix or None
        )

        # Store iteration data
        iteration_data = {
            'iteration_num': iteration_num,
            'extraction': current_extraction,
            'validation': validation_result,
            'metrics': _extract_metrics(validation_result),
            'timestamp': datetime.now().isoformat()
        }
        iterations.append(iteration_data)

        # STEP 2: Check quality
        if is_quality_sufficient(validation_result, quality_thresholds):
            # SUCCESS: Quality is sufficient
            _call_progress_callback(
                progress_callback,
                STEP_VALIDATION_CORRECTION,
                "completed",
                {
                    'final_status': 'passed',
                    'iterations': iteration_num + 1,
                    'reason': 'quality_sufficient'
                }
            )

            return {
                'best_extraction': current_extraction,
                'best_validation': validation_result,
                'iterations': iterations,
                'final_status': 'passed',
                'iteration_count': iteration_num + 1,
                'improvement_trajectory': [it['metrics']['overall_quality'] for it in iterations]
            }

        # STEP 3: Check if we can do another correction
        if iteration_num >= max_iterations:
            # MAX REACHED: Select best iteration
            best = _select_best_iteration(iterations)

            _call_progress_callback(
                progress_callback,
                STEP_VALIDATION_CORRECTION,
                "completed",
                {
                    'final_status': 'max_iterations_reached',
                    'iterations': len(iterations),
                    'best_iteration': best['iteration_num'],
                    'reason': 'max_iterations'
                }
            )

            return {
                'best_extraction': best['extraction'],
                'best_validation': best['validation'],
                'iterations': iterations,
                'final_status': 'max_iterations_reached',
                'iteration_count': len(iterations),
                'improvement_trajectory': [it['metrics']['overall_quality'] for it in iterations],
                'warning': f'Maximum iterations ({max_iterations}) reached. Using best result (iteration {best["iteration_num"]}).'
            }

        # STEP 4: Run correction for next iteration
        iteration_num += 1

        _call_progress_callback(
            progress_callback,
            STEP_VALIDATION_CORRECTION,
            "correction_starting",
            {'iteration': iteration_num}
        )

        correction_result = _run_correction_step(
            extraction_result=current_extraction,
            validation_result=validation_result,
            pdf_path=pdf_path,
            max_pages=None,
            classification_result=classification_result,
            llm=get_llm_provider(llm_provider),
            file_manager=file_manager,
            progress_callback=progress_callback
        )

        # Save corrected extraction
        corrected_file = file_manager.save_json(
            correction_result['corrected_extraction'],
            "extraction",
            status=f"_corrected{iteration_num}"
        )

        # Update current extraction for next iteration
        current_extraction = correction_result['corrected_extraction']

        # Loop continues...
```

### 4. Beste Iteratie Selectie

```python
def _select_best_iteration(iterations: list[dict]) -> dict:
    """
    Select best iteration when max iterations reached but quality insufficient.

    Selection strategy:
        1. Prefer last iteration (usually best due to progressive improvement)
        2. If last iteration worse than previous: select iteration with highest quality
        3. Quality ranking: (no critical issues > completeness > accuracy > schema compliance)

    Args:
        iterations: List of iteration data dicts

    Returns:
        dict: Best iteration data with reason

    Example:
        >>> iterations = [
        ...     {'iteration_num': 0, 'metrics': {'overall_quality': 0.85, 'critical_issues': 0}},
        ...     {'iteration_num': 1, 'metrics': {'overall_quality': 0.92, 'critical_issues': 0}},
        ...     {'iteration_num': 2, 'metrics': {'overall_quality': 0.89, 'critical_issues': 1}},
        ... ]
        >>> best = _select_best_iteration(iterations)
        >>> best['iteration_num']  # 1 (highest quality, no critical issues)
    """
    if not iterations:
        raise ValueError("No iterations to select from")

    # Get last iteration
    last = iterations[-1]

    # Check if last is acceptable (no regression)
    if len(iterations) == 1:
        return {**last, 'selection_reason': 'only_iteration'}

    # Compare last with previous
    previous = iterations[-2]

    # Priority ranking for selection
    def quality_rank(iteration: dict) -> tuple:
        """
        Create sortable quality tuple.
        Returns: (critical_ok, completeness, accuracy, compliance)
        """
        metrics = iteration['metrics']
        return (
            metrics.get('critical_issues', 999) == 0,  # Boolean: True > False
            metrics.get('completeness_score', 0),
            metrics.get('accuracy_score', 0),
            metrics.get('schema_compliance_score', 0)
        )

    # Sort all iterations by quality (best first)
    sorted_iterations = sorted(
        iterations,
        key=quality_rank,
        reverse=True
    )

    best = sorted_iterations[0]

    # Determine reason
    if best['iteration_num'] == last['iteration_num']:
        reason = 'final_iteration_best'
    else:
        reason = f'quality_peaked_at_iteration_{best["iteration_num"]}'

    return {**best, 'selection_reason': reason}


def _extract_metrics(validation_result: dict) -> dict:
    """Extract key metrics from validation result for comparison."""
    summary = validation_result.get('verification_summary', {})

    return {
        'completeness_score': summary.get('completeness_score', 0),
        'accuracy_score': summary.get('accuracy_score', 0),
        'schema_compliance_score': summary.get('schema_compliance_score', 0),
        'critical_issues': summary.get('critical_issues', 0),
        'total_issues': summary.get('total_issues', 0),
        'overall_status': summary.get('overall_status', 'unknown'),
        # Derived composite score for ranking
        'overall_quality': (
            summary.get('completeness_score', 0) * 0.4 +
            summary.get('accuracy_score', 0) * 0.4 +
            summary.get('schema_compliance_score', 0) * 0.2
        )
    }
```

### 5. File Naming Structuur

```
tmp/
├── paper-123-extraction.json                  # Originele extractie (iteratie 0)
├── paper-123-validation.json                  # Eerste validatie (iteratie 0)
│
├── paper-123-extraction_corrected1.json       # Correctie iteratie 1
├── paper-123-validation_corrected1.json       # Validatie van correctie 1
│
├── paper-123-extraction_corrected2.json       # Correctie iteratie 2
├── paper-123-validation_corrected2.json       # Validatie van correctie 2
│
├── paper-123-extraction_corrected3.json       # Correctie iteratie 3 (MAX)
└── paper-123-validation_corrected3.json       # Finale validatie (iteratie 3)
```

**File Manager Updates**:

```python
# src/pipeline/file_manager.py

# Geen wijzigingen nodig - huidige API ondersteunt al status suffix:
file_manager.save_json(data, "extraction", status="_corrected1")
# → tmp/paper-123-extraction_corrected1.json
```

### 6. Progress Callbacks

Nieuwe callback events voor iterative loop:

```python
# Event types voor progress_callback
CALLBACK_EVENTS = {
    'validation_starting': "Starting validation (iteration {iteration})",
    'validation_completed': "Validation completed (iteration {iteration})",
    'correction_starting': "Starting correction (iteration {iteration})",
    'correction_completed': "Correction completed (iteration {iteration})",
    'quality_check': "Checking quality against thresholds",
    'iteration_complete': "Iteration {iteration} complete - Quality: {quality:.2%}",
    'max_iterations_warning': "Maximum iterations reached - selecting best result",
}
```

---

## UI/UX Ontwerp

### 1. Settings Screen Aanpassingen

```python
# src/streamlit_app/screens/settings.py

# Pipeline Steps selectie
st.markdown("#### Pipeline Steps")
steps_options = {
    "classification": "Step 1: Classification",
    "extraction": "Step 2: Extraction",
    "validation_correction": "Step 3: Validation & Correction (Iterative)",
}

selected_steps = st.multiselect(
    "Select pipeline steps to run:",
    options=list(steps_options.keys()),
    default=["classification", "extraction", "validation_correction"],
    format_func=lambda x: steps_options[x]
)

# Nieuwe configuratie sectie
st.markdown("#### Validation & Correction Settings")

col1, col2 = st.columns(2)
with col1:
    max_iterations = st.number_input(
        "Maximum correction iterations",
        min_value=1,
        max_value=5,
        value=3,
        help="Maximum number of correction attempts if quality is insufficient"
    )

with col2:
    st.caption("Quality Thresholds")

completeness_threshold = st.slider(
    "Completeness threshold",
    min_value=0.5,
    max_value=1.0,
    value=0.90,
    step=0.05,
    help="Minimum required completeness score (0.90 = 90%)"
)

accuracy_threshold = st.slider(
    "Accuracy threshold",
    min_value=0.5,
    max_value=1.0,
    value=0.95,
    step=0.05,
    help="Minimum required accuracy score (0.95 = 95%)"
)

schema_compliance_threshold = st.slider(
    "Schema compliance threshold",
    min_value=0.5,
    max_value=1.0,
    value=0.95,
    step=0.05,
    help="Minimum required schema compliance score"
)

# Store in session state
st.session_state.settings['max_correction_iterations'] = max_iterations
st.session_state.settings['quality_thresholds'] = {
    'completeness_score': completeness_threshold,
    'accuracy_score': accuracy_threshold,
    'schema_compliance_score': schema_compliance_threshold,
    'critical_issues': 0  # Fixed - always 0
}
```

### 2. Execution Screen Aanpassingen

```python
# src/streamlit_app/screens/execution.py

def display_validation_correction_progress(iteration_data: dict):
    """
    Display progress for iterative validation & correction step.

    Shows:
    - Current iteration number
    - Quality metrics per iteration
    - Progress indicator
    - Iteration history with comparison
    """

    st.markdown("### Step 3: Validation & Correction")

    iterations = iteration_data.get('iterations', [])
    current_iteration = len(iterations)
    max_iterations = st.session_state.settings.get('max_correction_iterations', 3)

    # Progress bar
    progress = min(current_iteration / (max_iterations + 1), 1.0)
    st.progress(progress)
    st.caption(f"Iteration {current_iteration} of {max_iterations + 1} (initial + {max_iterations} corrections)")

    # Iteration history
    if iterations:
        st.markdown("#### Iteration History")

        # Create comparison table
        import pandas as pd

        history_data = []
        for it in iterations:
            metrics = it.get('metrics', {})
            history_data.append({
                'Iteration': it['iteration_num'],
                'Status': it.get('validation', {}).get('verification_summary', {}).get('overall_status', 'unknown'),
                'Completeness': f"{metrics.get('completeness_score', 0):.1%}",
                'Accuracy': f"{metrics.get('accuracy_score', 0):.1%}",
                'Schema': f"{metrics.get('schema_compliance_score', 0):.1%}",
                'Critical Issues': metrics.get('critical_issues', 0),
                'Overall Quality': f"{metrics.get('overall_quality', 0):.1%}"
            })

        df = pd.DataFrame(history_data)
        st.dataframe(df, use_container_width=True)

        # Quality trend chart
        st.markdown("#### Quality Improvement Trajectory")

        chart_data = pd.DataFrame({
            'Iteration': [it['iteration_num'] for it in iterations],
            'Completeness': [it['metrics']['completeness_score'] for it in iterations],
            'Accuracy': [it['metrics']['accuracy_score'] for it in iterations],
            'Schema Compliance': [it['metrics']['schema_compliance_score'] for it in iterations],
        }).set_index('Iteration')

        st.line_chart(chart_data)

        # Current iteration details (expandable)
        with st.expander(f"📋 Iteration {current_iteration - 1} Details", expanded=True):
            latest = iterations[-1]
            validation = latest.get('validation', {})
            summary = validation.get('verification_summary', {})

            # Metrics with color coding
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                comp_score = summary.get('completeness_score', 0)
                comp_threshold = st.session_state.settings['quality_thresholds']['completeness_score']
                comp_status = "✅" if comp_score >= comp_threshold else "⚠️"
                st.metric(
                    f"{comp_status} Completeness",
                    f"{comp_score:.1%}",
                    delta=f"Target: {comp_threshold:.0%}"
                )

            with col2:
                acc_score = summary.get('accuracy_score', 0)
                acc_threshold = st.session_state.settings['quality_thresholds']['accuracy_score']
                acc_status = "✅" if acc_score >= acc_threshold else "⚠️"
                st.metric(
                    f"{acc_status} Accuracy",
                    f"{acc_score:.1%}",
                    delta=f"Target: {acc_threshold:.0%}"
                )

            with col3:
                schema_score = summary.get('schema_compliance_score', 0)
                schema_threshold = st.session_state.settings['quality_thresholds']['schema_compliance_score']
                schema_status = "✅" if schema_score >= schema_threshold else "⚠️"
                st.metric(
                    f"{schema_status} Schema",
                    f"{schema_score:.1%}",
                    delta=f"Target: {schema_threshold:.0%}"
                )

            with col4:
                critical = summary.get('critical_issues', 0)
                critical_status = "✅" if critical == 0 else "❌"
                st.metric(
                    f"{critical_status} Critical Issues",
                    critical
                )

            # Show top issues if any
            issues = validation.get('issues', [])
            if issues:
                st.markdown("**Top Issues to Address:**")
                for i, issue in enumerate(issues[:5], 1):
                    severity = issue.get('severity', 'unknown')
                    emoji = {'critical': '🔴', 'moderate': '🟡', 'minor': '🟢'}.get(severity, '⚪')
                    st.write(f"{i}. {emoji} **{issue.get('category', 'Unknown')}**: {issue.get('description', 'No description')}")

    # Final status message
    final_status = iteration_data.get('final_status')
    if final_status == 'passed':
        st.success(f"✅ Quality sufficient after {current_iteration} iteration(s)!")
    elif final_status == 'max_iterations_reached':
        best_iter = iteration_data.get('best_iteration_num', current_iteration - 1)
        st.warning(f"⚠️ Maximum iterations reached. Using best result from iteration {best_iter}.")
        st.info("Consider reviewing the output manually or adjusting quality thresholds.")
```

### 3. Step Status Display

Update step status indicator:

```python
def init_execution_state():
    """Initialize execution state in session state."""

    # Update step_status structure
    if "step_status" not in st.session_state:
        st.session_state.step_status = {
            step: {
                "status": "pending",
                "start_time": None,
                "end_time": None,
                "result": None,
                "error": None,
                "elapsed_seconds": None,
                "verbose_data": {},
                # NEW: Voor validation_correction stap
                "iterations": [],  # Track iteration history
                "current_iteration": 0,
            }
            for step in ALL_PIPELINE_STEPS
        }
```

---

## Configuratie & Settings

### Session State Updates

```python
# src/streamlit_app/__init__.py

def init_session_state():
    """Initialize all session state variables."""

    # Existing settings...

    # NEW: Validation & Correction settings
    if 'max_correction_iterations' not in st.session_state.settings:
        st.session_state.settings['max_correction_iterations'] = 3

    if 'quality_thresholds' not in st.session_state.settings:
        st.session_state.settings['quality_thresholds'] = {
            'completeness_score': 0.90,
            'accuracy_score': 0.95,
            'schema_compliance_score': 0.95,
            'critical_issues': 0
        }
```

### Configuratie File Support (Optioneel)

Voor CLI/batch processing - configuratie via YAML/JSON:

```yaml
# config/pipeline_config.yaml

validation_correction:
  enabled: true
  max_iterations: 3
  quality_thresholds:
    completeness_score: 0.90
    accuracy_score: 0.95
    schema_compliance_score: 0.95
    critical_issues: 0

  # Optionele advanced settings
  early_stopping: true  # Stop als 2 iteraties geen verbetering
  save_all_iterations: true  # Bewaar alle tussenresultaten
```

---

## Implementatie Strategie

### Fase 1: Core Loop Logic (Week 1)

**Doel**: Implementeer basis iterative loop zonder UI

1. ✅ Feature branch aanmaken
2. ✅ Feature document (dit document)
3. **Implementatie**:
   - [ ] `run_validation_with_correction()` functie
   - [ ] `is_quality_sufficient()` helper
   - [ ] `_select_best_iteration()` helper
   - [ ] `_extract_metrics()` helper
   - [ ] Constants update (`STEP_VALIDATION_CORRECTION`)
4. **Testing**:
   - [ ] Unit tests voor loop logica
   - [ ] Unit tests voor quality assessment
   - [ ] Unit tests voor best iteration selection
   - [ ] Mock tests met verschillende scenario's

**Deliverable**: Werkende loop logica met tests

### Fase 2: File Management & Persistence (Week 1-2)

**Doel**: Iteraties correct opslaan en laden

1. **Implementatie**:
   - [ ] File naming met iteratie suffixes (verifiëren dat dit al werkt)
   - [ ] Iteratie metadata bijhouden in JSON
   - [ ] Lazy loading van iteraties (niet alle in geheugen)
2. **Testing**:
   - [ ] File saving tests
   - [ ] File loading tests
   - [ ] Iteratie traceability tests

**Deliverable**: Alle iteraties worden correct opgeslagen met metadata

### Fase 3: Backward Compatibility (Week 2)

**Doel**: Bestaande code blijft werken

1. **Implementatie**:
   - [ ] Update `run_single_step()` voor nieuwe stap
   - [ ] CLI blijft ondersteunen oude `--step validation` en `--step correction`
   - [ ] Bestaande tests blijven slagen
2. **Testing**:
   - [ ] Regression tests voor oude API
   - [ ] CLI tests voor alle step combinaties

**Deliverable**: Backward compatible API

### Fase 4: Streamlit UI Integration (Week 2-3)

**Doel**: UI voor iterative loop

1. **Implementatie**:
   - [ ] Settings screen: max_iterations, thresholds
   - [ ] Execution screen: iteratie progress display
   - [ ] Step status indicator update
   - [ ] Real-time metrics updates via callbacks
2. **Testing**:
   - [ ] Manual UI testing
   - [ ] Verschillende scenario's (snel convergeren, max iterations, failure)

**Deliverable**: Volledig functionele UI

### Fase 5: Edge Cases & Polish (Week 3-4)

**Doel**: Robuustheid en error handling

1. **Implementatie**:
   - [ ] Error handling voor LLM failures tijdens iteratie
   - [ ] Graceful degradation bij API rate limits
   - [ ] Recovery van partially completed iterations
   - [ ] Logging en diagnostics
2. **Testing**:
   - [ ] Error scenario tests
   - [ ] Rate limit simulation
   - [ ] Long-running test (5+ iterations)

**Deliverable**: Production-ready feature

### Fase 6: Documentation & Review (Week 4)

1. [ ] Update ARCHITECTURE.md
2. [ ] Update CHANGELOG.md
3. [ ] Update README.md met nieuwe step
4. [ ] Code review
5. [ ] Performance testing (tijd, kosten)
6. [ ] PR naar main

**Deliverable**: Gemerged feature met documentatie

---

## Testing Strategie

### Unit Tests

```python
# tests/unit/test_iterative_validation_correction.py

class TestQualityAssessment:
    """Test quality threshold checking."""

    def test_quality_sufficient_all_thresholds_met(self):
        validation = {
            'verification_summary': {
                'completeness_score': 0.95,
                'accuracy_score': 0.98,
                'schema_compliance_score': 0.97,
                'critical_issues': 0
            }
        }
        assert is_quality_sufficient(validation) is True

    def test_quality_insufficient_completeness_low(self):
        validation = {
            'verification_summary': {
                'completeness_score': 0.85,  # Below 0.90
                'accuracy_score': 0.98,
                'schema_compliance_score': 0.97,
                'critical_issues': 0
            }
        }
        assert is_quality_sufficient(validation) is False

    def test_quality_insufficient_critical_issues_present(self):
        validation = {
            'verification_summary': {
                'completeness_score': 0.95,
                'accuracy_score': 0.98,
                'schema_compliance_score': 0.97,
                'critical_issues': 1  # Not zero
            }
        }
        assert is_quality_sufficient(validation) is False


class TestBestIterationSelection:
    """Test best iteration selection logic."""

    def test_select_last_iteration_when_best(self):
        iterations = [
            {'iteration_num': 0, 'metrics': {'overall_quality': 0.80, 'critical_issues': 0}},
            {'iteration_num': 1, 'metrics': {'overall_quality': 0.90, 'critical_issues': 0}},
        ]
        best = _select_best_iteration(iterations)
        assert best['iteration_num'] == 1
        assert best['selection_reason'] == 'final_iteration_best'

    def test_select_earlier_iteration_when_regression(self):
        iterations = [
            {'iteration_num': 0, 'metrics': {'overall_quality': 0.80, 'critical_issues': 0}},
            {'iteration_num': 1, 'metrics': {'overall_quality': 0.92, 'critical_issues': 0}},
            {'iteration_num': 2, 'metrics': {'overall_quality': 0.85, 'critical_issues': 0}},
        ]
        best = _select_best_iteration(iterations)
        assert best['iteration_num'] == 1
        assert 'peaked_at_iteration_1' in best['selection_reason']

    def test_prioritize_no_critical_issues(self):
        iterations = [
            {'iteration_num': 0, 'metrics': {'overall_quality': 0.95, 'critical_issues': 1}},
            {'iteration_num': 1, 'metrics': {'overall_quality': 0.88, 'critical_issues': 0}},
        ]
        best = _select_best_iteration(iterations)
        assert best['iteration_num'] == 1  # Lower score but no critical issues


class TestIterativeLoop:
    """Test full iterative loop with mocks."""

    @patch('src.pipeline.orchestrator._run_validation_step')
    @patch('src.pipeline.orchestrator._run_correction_step')
    def test_loop_stops_when_quality_sufficient(self, mock_correction, mock_validation):
        """Test that loop stops after 1 iteration when quality is good."""

        # Mock: first validation insufficient, second sufficient
        mock_validation.side_effect = [
            {  # Iteration 0 - insufficient
                'verification_summary': {
                    'completeness_score': 0.85,
                    'accuracy_score': 0.95,
                    'schema_compliance_score': 0.95,
                    'critical_issues': 0
                }
            },
            {  # Iteration 1 - sufficient
                'verification_summary': {
                    'completeness_score': 0.92,
                    'accuracy_score': 0.97,
                    'schema_compliance_score': 0.96,
                    'critical_issues': 0
                }
            }
        ]

        mock_correction.return_value = {
            'corrected_extraction': {'some': 'data'}
        }

        result = run_validation_with_correction(
            pdf_path=Path("test.pdf"),
            extraction_result={'initial': 'data'},
            classification_result={'publication_type': 'interventional_trial'},
            llm_provider="openai",
            file_manager=mock_file_manager,
            max_iterations=3
        )

        assert result['final_status'] == 'passed'
        assert result['iteration_count'] == 2  # 0 (initial) + 1 (correction)
        assert mock_validation.call_count == 2
        assert mock_correction.call_count == 1

    @patch('src.pipeline.orchestrator._run_validation_step')
    @patch('src.pipeline.orchestrator._run_correction_step')
    def test_loop_stops_at_max_iterations(self, mock_correction, mock_validation):
        """Test that loop stops at max_iterations."""

        # Mock: always insufficient quality
        mock_validation.return_value = {
            'verification_summary': {
                'completeness_score': 0.85,
                'accuracy_score': 0.92,
                'schema_compliance_score': 0.94,
                'critical_issues': 0
            }
        }

        mock_correction.return_value = {
            'corrected_extraction': {'some': 'data'}
        }

        result = run_validation_with_correction(
            pdf_path=Path("test.pdf"),
            extraction_result={'initial': 'data'},
            classification_result={'publication_type': 'interventional_trial'},
            llm_provider="openai",
            file_manager=mock_file_manager,
            max_iterations=2
        )

        assert result['final_status'] == 'max_iterations_reached'
        assert result['iteration_count'] == 3  # 0 + 2 corrections
        assert 'warning' in result
        assert mock_validation.call_count == 3
        assert mock_correction.call_count == 2
```

### Integration Tests

```python
# tests/integration/test_iterative_workflow.py

@pytest.mark.slow
@pytest.mark.integration
def test_full_iterative_workflow_with_real_llm(test_pdf_path):
    """
    Integration test with real LLM calls.
    Uses a known problematic paper that requires correction.
    """
    # This test will be expensive - run sparingly
    pass


@pytest.mark.integration
def test_file_persistence_across_iterations():
    """Test that all iterations are correctly saved and loadable."""
    pass
```

### Manual Test Scenarios

1. **Happy Path**: Paper verbetert na 1 correctie → passed
2. **Max Iterations**: Paper blijft onvoldoende na 3 correcties → max_iterations_reached
3. **Perfect Initial**: Paper is meteen goed → passed na iteratie 0
4. **Regression**: Kwaliteit verslechtert na correctie → selecteer beste eerdere iteratie
5. **Schema Failure**: Schema validatie faalt na correctie → error + stop
6. **LLM Failure**: LLM call faalt tijdens iteratie → error handling + retry?

---

## Risico's & Mitigaties

### Risico 1: Kosten Escalatie

**Risico**: Meerdere iteraties = meer LLM calls = hogere kosten

**Impact**: Hoog - Bij 3 iteraties: ~4x validaties + 3x correcties = 7x LLM calls vs. 1x nu

**Mitigatie**:
- ✅ Configureerbare max_iterations (default: 3, kan lager)
- ✅ Schema validatie blijft gatekeeper (stopt slechte extracties vroeg)
- ✅ Cost tracking in metrics
- ✅ Waarschuwing in UI bij veel iteraties
- 📊 Monitoring: log aantal iteraties per paper, detecteer outliers

**Verwachte kosten**:
```
Scenario 1 (Goede extractie):
- Iteratie 0: validation (~$0.20) → passed
- Totaal: $0.20 (geen verschil met nu)

Scenario 2 (Matige extractie, 1 correctie):
- Iteratie 0: validation (~$0.20) → insufficient
- Correctie 1: ~$0.30
- Iteratie 1: validation (~$0.20) → passed
- Totaal: $0.70 (was: $0.50, +$0.20)

Scenario 3 (Problematische extractie, MAX=3):
- Iteratie 0: validation (~$0.20)
- Correcties 1-3: ~$0.90 ($0.30 × 3)
- Validaties 1-3: ~$0.60 ($0.20 × 3)
- Totaal: $1.70 (was: $0.50, +$1.20)

Gemiddelde verwachting (80% scenario 1, 15% scenario 2, 5% scenario 3):
- $0.20 × 0.80 + $0.70 × 0.15 + $1.70 × 0.05 = $0.35 per paper
- Huidige kosten: ~$0.30 per paper (incl. correction)
- Stijging: ~17% bij zelfde kwaliteit, maar hogere succes rate
```

### Risico 2: Execution Time

**Risico**: Meerdere iteraties = langere pipeline execution tijd

**Impact**: Medium - 3 iteraties kan 5-10 minuten duren vs. 2-3 minuten nu

**Mitigatie**:
- ✅ Parallellisatie waar mogelijk (niet in deze fase)
- ✅ Progress indicators in UI (gebruiker ziet vooruitgang)
- ✅ Configureerbare max_iterations (kan naar 1 voor snelheid)
- 📊 Time tracking per iteratie
- 💡 Future: Early stopping als 2 iteraties geen verbetering

### Risico 3: Convergence Failure

**Risico**: Loop convergeert niet, kwaliteit blijft oscilleren

**Impact**: Medium - Verspilde resources, geen goede output

**Mitigatie**:
- ✅ Max iterations hard limit (default: 3)
- ✅ Best iteration selection (kiest beste poging)
- ✅ Quality trajectory tracking (zie je oscillatie)
- 📊 Logging van niet-convergerende papers voor analyse
- 💡 Future: Detecteer oscillatie → stop vroeg

### Risico 4: Backward Compatibility

**Risico**: Bestaande CLI scripts en tests breken

**Impact**: Hoog - Gebruikers kunnen niet meer werken

**Mitigatie**:
- ✅ Oude stappen (`validation`, `correction`) blijven bestaan
- ✅ Nieuwe stap is opt-in (`validation_correction`)
- ✅ Regression tests voor oude API
- ✅ Duidelijke migratie documentatie

### Risico 5: Complexity Creep

**Risico**: Feature wordt te complex, moeilijk te onderhouden

**Impact**: Medium - Verhoogde development tijd, bugs

**Mitigatie**:
- ✅ Gefaseerde implementatie (core eerst, polish later)
- ✅ Uitgebreide tests per fase
- ✅ Code review na elke fase
- ✅ Feature flag om uit te schakelen indien problemen

---

## Open Vragen & Beslissingen

### Beslissingen Genomen

✅ **Q1**: Step naming strategie?
**A**: Hybride - nieuwe `STEP_VALIDATION_CORRECTION`, oude blijven voor CLI

✅ **Q2**: UI weergave?
**A**: Gecombineerde stap "Validation & Correction" met iteratie sub-progress

✅ **Q3**: Backward compatibility?
**A**: Ja - oude stappen blijven werken, nieuwe stap is opt-in

✅ **Q4**: Beste iteratie selectie?
**A**: Kies laatste (meestal beste), of hoogste kwaliteit bij regressie

✅ **Q5**: Quality thresholds?
**A**: Completeness ≥0.90, Accuracy ≥0.95, Schema Compliance ≥0.95, Critical Issues = 0

✅ **Q6**: File naming?
**A**: `_corrected1`, `_corrected2`, `_corrected3` suffixes

✅ **Q7**: Max iterations?
**A**: Default 3, configureerbaar in settings (1-5 range)

### Open Vragen (Te Beantwoorden Tijdens Implementatie)

❓ **Q8**: Early stopping bij geen verbetering?
- Als 2 opeenvolgende iteraties geen significante verbetering (<1%) → stop?
- Of altijd tot MAX?

❓ **Q9**: Retry bij LLM failures?
- Als LLM call faalt tijdens iteratie → retry of fail hele loop?
- Exponential backoff?

❓ **Q10**: Parallellisatie mogelijk?
- Kunnen we meerdere correctie-pogingen parallel doen? (Nee, te complex voor v1)
- Future optimization?

❓ **Q11**: Configuratie persistence?
- Slaan we threshold settings op in profile/config file?
- Of alleen in session state?

❓ **Q12**: Monitoring & Analytics?
- Willen we iteration statistics bijhouden (avg iterations, convergence rate)?
- Database of log files?

---

## Success Criteria

### Functioneel

- ✅ Loop voert automatisch validatie + correctie uit tot kwaliteit voldoende
- ✅ Stopt bij configureerbare thresholds OF max iterations
- ✅ Selecteert automatisch beste iteratie bij max iterations
- ✅ Alle iteraties worden opgeslagen met metadata
- ✅ UI toont duidelijke progress en metrics per iteratie
- ✅ Backward compatible met bestaande API

### Performance

- ✅ ≥80% van papers convergeert binnen 2 iteraties
- ✅ Gemiddelde kosten stijging <25% vs. huidige situatie
- ✅ Execution time <10 minuten voor max iterations (3)

### Kwaliteit

- ✅ Finale output kwaliteit ≥90% completeness, ≥95% accuracy (gemiddeld)
- ✅ Alle unit tests slagen (>95% coverage voor nieuwe code)
- ✅ Manual testing van alle edge cases succesvol

### Code Quality

- ✅ Code review approved
- ✅ Documentatie compleet (docstrings, ARCHITECTURE.md, README.md)
- ✅ Geen regressies in bestaande functionaliteit

---

## Referenties

- **Related Files**:
  - `src/pipeline/orchestrator.py` - Pipeline orchestration
  - `src/pipeline/validation_runner.py` - Dual validation logic
  - `src/streamlit_app/screens/execution.py` - Execution UI
  - `src/streamlit_app/screens/settings.py` - Settings UI
  - `prompts/Extraction-validation.txt` - LLM validation prompt

- **Related Documents**:
  - `VALIDATION_STRATEGY.md` - Dual validation approach
  - `ARCHITECTURE.md` - System architecture
  - `features/pipeline-execution-implementation.md` - Step-by-step execution feature

- **Related PRs/Issues**:
  - PR #17: Step-by-step pipeline execution
  - (Future: Issue for this feature)

---

## Changelog

| Datum | Versie | Wijziging |
|-------|--------|-----------|
| 2025-01-28 | 1.0 | Initial feature document |
