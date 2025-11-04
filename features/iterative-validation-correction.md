# Feature: Iterative Validation & Correction Loop

**Status**: Complete ✅ - All Phases Implemented + Bug Fixes
**Branch**: `feature/iterative-validation-correction`
**Created**: 2025-01-28
**Updated**: 2025-11-01 (v1.5 - Bug fixes: best_iteration display + navigation state reset)
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
                    │  - Completeness ≥ 0.90?      │
                    │  - Accuracy ≥ 0.95?          │
                    │  - Schema Compliance ≥ 0.95? │
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
        max_iterations: Maximum correction attempts (default: 3)
            IMPORTANT: Total iterations = initial validation + max_iterations corrections
            Example: max_iterations=3 means up to 4 total iterations (iter 0,1,2,3)
            Rationale: Naming reflects "corrections" not "total validations" for clarity
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
    validation_result: dict | None,
    thresholds: dict = DEFAULT_QUALITY_THRESHOLDS
) -> bool:
    """
    Check if validation quality meets thresholds for stopping iteration.

    Args:
        validation_result: Validation JSON with verification_summary (can be None)
        thresholds: Quality thresholds to check against

    Returns:
        bool: True if ALL thresholds are met, False otherwise

    Edge Cases:
        - validation_result is None → False
        - verification_summary missing → False
        - Any score is None → treated as 0 (fails threshold)
        - Empty dict → False (all scores default to 0)

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
        >>> is_quality_sufficient(None)  # False
        >>> is_quality_sufficient({})  # False
    """
    # Handle None validation_result
    if validation_result is None:
        return False

    summary = validation_result.get('verification_summary', {})

    # Handle missing or empty summary
    if not summary:
        return False

    # Helper to safely extract numeric scores (handle None values)
    def safe_score(key: str, default: float = 0.0) -> float:
        val = summary.get(key, default)
        return val if isinstance(val, (int, float)) else default

    # Check all thresholds
    return (
        safe_score('completeness_score') >= thresholds['completeness_score'] and
        safe_score('accuracy_score') >= thresholds['accuracy_score'] and
        safe_score('schema_compliance_score') >= thresholds['schema_compliance_score'] and
        safe_score('critical_issues', 999) <= thresholds['critical_issues']
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
    """Main iterative loop implementation with integrated error handling."""

    # Initialize
    iterations = []
    current_extraction = extraction_result
    iteration_num = 0

    # Default thresholds
    if quality_thresholds is None:
        quality_thresholds = DEFAULT_QUALITY_THRESHOLDS

    # Extract publication_type for correction step
    publication_type = classification_result.get('publication_type', 'unknown')

    while iteration_num <= max_iterations:
        try:
            # Progress callback
            _call_progress_callback(
                progress_callback,
                STEP_VALIDATION_CORRECTION,
                "starting",
                {'iteration': iteration_num, 'step': 'validation'}
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

            # Check schema validation failure (critical error)
            schema_validation = validation_result.get('schema_validation', {})
            quality_score = schema_validation.get('quality_score', 0)

            if quality_score < 0.5:  # Schema quality threshold
                # CRITICAL: Schema validation failed - STOP
                return {
                    'best_extraction': None,
                    'best_validation': validation_result,
                    'iterations': iterations,
                    'final_status': 'failed_schema_validation',
                    'iteration_count': iteration_num + 1,
                    'error': f'Schema validation failed (quality: {quality_score:.2f}). Cannot proceed with correction.',
                    'failed_at_iteration': iteration_num
                }

            # Save validation with iteration suffix
            suffix = f"corrected{iteration_num}" if iteration_num > 0 else None
            validation_file = file_manager.save_json(
                validation_result,
                "validation",
                status=suffix  # FileManager adds '-' between step and status
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

            # STEP 3A: Check for quality degradation (early stopping)
            if iteration_num >= 2:  # Need at least 3 iterations to detect trend
                if _detect_quality_degradation(iterations, window=2):
                    # EARLY STOP: Quality is degrading
                    best = _select_best_iteration(iterations)

                    _call_progress_callback(
                        progress_callback,
                        STEP_VALIDATION_CORRECTION,
                        "completed",
                        {
                            'final_status': 'early_stopped_degradation',
                            'iterations': len(iterations),
                            'best_iteration': best['iteration_num'],
                            'reason': 'quality_degradation'
                        }
                    )

                    return {
                        'best_extraction': best['extraction'],
                        'best_validation': best['validation'],
                        'iterations': iterations,
                        'final_status': 'early_stopped_degradation',
                        'iteration_count': len(iterations),
                        'improvement_trajectory': [it['metrics']['overall_quality'] for it in iterations],
                        'warning': f'Early stopping triggered: quality degraded for 2 consecutive iterations. Using best result (iteration {best["iteration_num"]}).'
                    }

            # STEP 3B: Check if we can do another correction
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
                "starting",
                {'iteration': iteration_num, 'step': 'correction'}
            )

            # Call correction step - returns tuple (corrected_extraction, final_validation)
            corrected_extraction, _ = _run_correction_step(
                extraction_result=current_extraction,
                validation_result=validation_result,
                pdf_path=pdf_path,
                max_pages=None,
                publication_type=publication_type,  # FIXED: Added missing parameter
                llm=get_llm_provider(llm_provider),
                file_manager=file_manager,
                progress_callback=progress_callback
            )

            # Save corrected extraction
            corrected_file = file_manager.save_json(
                corrected_extraction,
                "extraction",
                status=f"corrected{iteration_num}"  # FileManager adds '-' between step and status
            )

            # Update current extraction for next iteration
            current_extraction = corrected_extraction

            # Loop continues...

        except LLMProviderError as e:
            # LLM API failure - retry with exponential backoff
            max_retries = 3
            retry_successful = False

            for retry in range(max_retries):
                wait_time = 2 ** retry  # 1s, 2s, 4s
                console.print(f"[yellow]⚠️  LLM call failed, retrying in {wait_time}s... (attempt {retry+1}/{max_retries})[/yellow]")
                time.sleep(wait_time)

                try:
                    # Retry the current step based on iteration stage
                    if iteration_num == len(iterations):
                        # Failed during validation - retry validation
                        validation_result = _run_validation_step(
                            extraction_result=current_extraction,
                            pdf_path=pdf_path,
                            max_pages=None,
                            classification_result=classification_result,
                            llm=get_llm_provider(llm_provider),
                            file_manager=file_manager,
                            progress_callback=progress_callback
                        )
                        retry_successful = True
                        break
                    else:
                        # Failed during correction - retry correction
                        corrected_extraction, _ = _run_correction_step(
                            extraction_result=current_extraction,
                            validation_result=validation_result,
                            pdf_path=pdf_path,
                            max_pages=None,
                            publication_type=publication_type,
                            llm=get_llm_provider(llm_provider),
                            file_manager=file_manager,
                            progress_callback=progress_callback
                        )
                        retry_successful = True
                        break
                except LLMProviderError:
                    continue

            if not retry_successful:
                # All retries exhausted
                best = _select_best_iteration(iterations) if iterations else None
                return {
                    'best_extraction': best['extraction'] if best else current_extraction,
                    'best_validation': best['validation'] if best else None,
                    'iterations': iterations,
                    'final_status': 'failed_llm_error',
                    'iteration_count': len(iterations),
                    'error': f'LLM provider error after {max_retries} retries: {str(e)}',
                    'failed_at_iteration': iteration_num
                }

        except json.JSONDecodeError as e:
            # Invalid JSON from correction - treat as critical error
            console.print(f"[red]❌ Correction returned invalid JSON at iteration {iteration_num}[/red]")
            best = _select_best_iteration(iterations) if iterations else None
            return {
                'best_extraction': best['extraction'] if best else current_extraction,
                'best_validation': best['validation'] if best else None,
                'iterations': iterations,
                'final_status': 'failed_invalid_json',
                'iteration_count': len(iterations),
                'error': f'Correction produced invalid JSON: {str(e)}',
                'failed_at_iteration': iteration_num
            }

        except Exception as e:
            # Unexpected error - fail gracefully
            console.print(f"[red]❌ Unexpected error at iteration {iteration_num}: {str(e)}[/red]")
            best = _select_best_iteration(iterations) if len(iterations) > 0 else None
            return {
                'best_extraction': best['extraction'] if best else current_extraction,
                'best_validation': best['validation'] if best else None,
                'iterations': iterations,
                'final_status': 'failed_unexpected_error',
                'iteration_count': len(iterations),
                'error': f'Unexpected error: {str(e)}',
                'failed_at_iteration': iteration_num
            }
```

### 4. Error Status Codes

**Note**: Error handling is now integrated into the main loop (see Section 3). Below are the possible final status codes:

```python
# Error Status Codes
FINAL_STATUS_CODES = {
    'passed': 'Quality thresholds met',
    'max_iterations_reached': 'Maximum iterations reached, using best result',
    'early_stopped_degradation': 'Stopped due to quality degradation',
    'failed_schema_validation': 'Schema validation failed',
    'failed_llm_error': 'LLM API error after retries',
    'failed_invalid_json': 'Correction produced invalid JSON',
    'failed_unexpected_error': 'Unexpected error occurred'
}
```

**Error Handling Strategy** (integrated in Section 3 loop):

1. **Schema Validation Failure** → STOP FAIL
   - Cannot recover from structural errors (quality < 50%)
   - Return what we have so far

2. **LLM API Failures** → RETRY with exponential backoff (3x)
   - Transient errors (rate limits, network) often resolve
   - Wait times: 1s, 2s, 4s (2^retry)
   - After 3 retries → FAIL with best iteration so far

3. **Invalid JSON from Correction** → STOP FAIL
   - Correction corrupted the data
   - Use previous iteration (before failed correction)

4. **Unexpected Errors** → FAIL GRACEFULLY
   - Log error, return best iteration so far
   - Don't lose progress from successful iterations

### 5. Early Stopping (Quality Degradation Detection)

```python
def _detect_quality_degradation(iterations: list[dict], window: int = 2) -> bool:
    """
    Detect if quality has been degrading for the last N iterations.

    Early stopping prevents wasted LLM calls when corrections are making things worse.

    Args:
        iterations: List of all iteration data (each with 'metrics' dict)
        window: Number of consecutive degrading iterations to trigger stop (default: 2)

    Returns:
        True if quality degraded for 'window' consecutive iterations

    Logic:
        - Need at least (window + 1) iterations to detect trend
        - Compare last 'window' iterations against the OVERALL best score seen so far
        - Degradation = all iterations in window are worse than the peak quality
        - This catches systematic degradation, not transient noise

    Example:
        iterations = [
            {'metrics': {'overall_quality': 0.85}},  # iter 0
            {'metrics': {'overall_quality': 0.88}},  # iter 1 (BEST - peak quality)
            {'metrics': {'overall_quality': 0.86}},  # iter 2 (degraded from 0.88)
            {'metrics': {'overall_quality': 0.84}}   # iter 3 (degraded again)
        ]
        _detect_quality_degradation(iterations, window=2) → True
        # Last 2 iterations (0.86, 0.84) are BOTH worse than peak (0.88)
        # This indicates systematic degradation → stop and use iteration 1
    """
    if len(iterations) < window + 1:
        return False

    # Get quality scores
    scores = [it['metrics'].get('overall_quality', 0) for it in iterations]

    # Find OVERALL peak quality (not just before window)
    # This is the best score we've achieved across all iterations
    peak_quality = max(scores)

    # Check if last 'window' iterations are ALL worse than peak
    # This indicates systematic degradation, not just a single bad iteration
    window_scores = scores[-window:]
    all_degraded = all(score < peak_quality for score in window_scores)

    return all_degraded


```

**Early Stopping Rationale**:

1. **Why detect degradation?**
   - Sometimes corrections introduce new errors
   - LLM may "overthink" and corrupt good data
   - Example: Iter 1 = 0.88 quality, Iter 2 = 0.86, Iter 3 = 0.84 → STOP

2. **Why window=2?**
   - Single degradation could be transient noise
   - Two consecutive degradations indicate systematic problem
   - Balances sensitivity vs false positives

3. **Integration in loop**:
   - Check after each validation (if iteration_num >= 2)
   - If triggered: select best iteration and return immediately
   - Saves LLM costs and processing time

### 6. Beste Iteratie Selectie

```python
def _select_best_iteration(iterations: list[dict]) -> dict:
    """
    Select best iteration when max iterations reached but quality insufficient.

    Selection strategy:
        1. Priority 1: No critical issues (mandatory)
        2. Priority 2: Highest weighted quality score (40% completeness + 40% accuracy + 20% schema)
        3. Priority 3: If tied, prefer higher completeness
        4. Usually selects last iteration due to progressive improvement

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
        Create sortable quality tuple using weighted composite score.
        Returns: (critical_ok, overall_quality, completeness_tiebreaker)

        Overall quality = weighted average:
        - 40% completeness (how much PDF data extracted)
        - 40% accuracy (correctness, no hallucinations)
        - 20% schema compliance (structural correctness)
        """
        metrics = iteration['metrics']
        overall_quality = (
            metrics.get('completeness_score', 0) * 0.40 +
            metrics.get('accuracy_score', 0) * 0.40 +
            metrics.get('schema_compliance_score', 0) * 0.20
        )
        return (
            metrics.get('critical_issues', 999) == 0,  # Priority 1: No critical issues
            overall_quality,                            # Priority 2: Composite quality
            metrics.get('completeness_score', 0)        # Priority 3: Completeness as tiebreaker
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
    """
    Extract key metrics from validation result for comparison.

    Used for:
    - Best iteration selection (_select_best_iteration)
    - Quality degradation detection (_detect_quality_degradation)
    - Progress tracking and UI display

    Returns dict with individual scores + computed 'overall_quality':
        - 40% completeness (coverage of PDF data)
        - 40% accuracy (correctness, no hallucinations)
        - 20% schema compliance (structural correctness)
    """
    summary = validation_result.get('verification_summary', {})

    return {
        'completeness_score': summary.get('completeness_score', 0),
        'accuracy_score': summary.get('accuracy_score', 0),
        'schema_compliance_score': summary.get('schema_compliance_score', 0),
        'critical_issues': summary.get('critical_issues', 0),
        'total_issues': summary.get('total_issues', 0),
        'overall_status': summary.get('overall_status', 'unknown'),
        # Derived composite score (used by ranking and degradation detection)
        'overall_quality': (
            summary.get('completeness_score', 0) * 0.4 +
            summary.get('accuracy_score', 0) * 0.4 +
            summary.get('schema_compliance_score', 0) * 0.2
        )
    }
```

### 7. File Naming Structuur

```
tmp/
├── paper-123-extraction.json                  # Originele extractie (iteratie 0)
├── paper-123-validation.json                  # Eerste validatie (iteratie 0)
│
├── paper-123-extraction-corrected1.json       # Correctie iteratie 1
├── paper-123-validation-corrected1.json       # Validatie van correctie 1
│
├── paper-123-extraction-corrected2.json       # Correctie iteratie 2
├── paper-123-validation-corrected2.json       # Validatie van correctie 2
│
├── paper-123-extraction-corrected3.json       # Correctie iteratie 3 (MAX)
└── paper-123-validation-corrected3.json       # Finale validatie (iteratie 3)
```

**Expliciete Mapping**:

| Iteration | Extraction File | Validatie File | Notes |
|-----------|----------------|----------------|-------|
| **0** (initial) | `extraction.json` | `validation.json` | Originele extractie + eerste validatie |
| **1** (after 1st correction) | `extraction-corrected1.json` | `validation-corrected1.json` | Na 1e correctiepoging |
| **2** (after 2nd correction) | `extraction-corrected2.json` | `validation-corrected2.json` | Na 2e correctiepoging |
| **3** (after 3rd correction) | `extraction-corrected3.json` | `validation-corrected3.json` | Na 3e correctiepoging (MAX) |

**Belangrijk**: `validation-correctedN.json` valideert altijd `extraction-correctedN.json`

**File Manager Updates**:

```python
# src/pipeline/file_manager.py

# Geen wijzigingen nodig - huidige API ondersteunt al status suffix:
file_manager.save_json(data, "extraction", status="corrected1")
# → tmp/paper-123-extraction-corrected1.json (FileManager adds '-' separator)

# In loop code:
suffix = f"corrected{iteration_num}" if iteration_num > 0 else None
validation_file = file_manager.save_json(
    validation_result,
    "validation",
    status=suffix or None  # None = no suffix, "" would create "_"
)
```

### 8. Progress Callbacks

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
    max_value=0.99,  # Cap at 99% - requiring 100% is unrealistic
    value=0.90,
    step=0.05,
    help="Minimum required completeness score (0.90 = 90%). Max 99% - requiring perfect scores would prevent loop termination."
)

accuracy_threshold = st.slider(
    "Accuracy threshold",
    min_value=0.5,
    max_value=0.99,  # Cap at 99% - requiring 100% is unrealistic
    value=0.95,
    step=0.05,
    help="Minimum required accuracy score (0.95 = 95%). Max 99% - requiring perfect scores would prevent loop termination."
)

schema_compliance_threshold = st.slider(
    "Schema compliance threshold",
    min_value=0.5,
    max_value=0.99,  # Cap at 99% - requiring 100% is unrealistic
    value=0.95,
    step=0.05,
    help="Minimum required schema compliance score. Max 99% - requiring perfect scores would prevent loop termination."
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

### 4. Real-Time Updates met st.empty() (Streamlit Best Practice)

**Probleem**: De iterative loop draait binnen één pipeline step. Tussen iteraties willen we de UI updaten zonder st.rerun() (wat kostbaar is en de hele app herlaadt).

**Oplossing**: Gebruik `st.empty()` containers voor in-place updates binnen de loop.

**Waarom st.empty() voor deze feature?**
- ✅ **Efficiency**: Geen full app rerun tussen iteraties (saves ~100-200ms per iteration)
- ✅ **Real-time feedback**: User ziet metrics/history accumulate zonder page refresh
- ✅ **Smooth UX**: Progress bar/table updates live, geen flikkering
- ✅ **Streamlit 2024 best practice**: Recommended pattern voor within-step updates
- ✅ **Consistent**: Hele validation-correction loop is één atomic step

**Implementatie Strategie** (REVISED - No Loop Duplication):

```python
# src/streamlit_app/screens/execution.py

def display_validation_correction_step(
    pdf_path: Path,
    extraction_result: dict,
    classification_result: dict,
    llm_provider: str,
    file_manager: PipelineFileManager
) -> dict:
    """
    Display and execute iterative validation-correction with real-time UI updates.

    Uses st.empty() containers for in-place updates WITHOUT st.rerun() between iterations.
    This provides smooth, efficient real-time feedback during the iterative loop.

    Architecture:
        - Create placeholder containers upfront (st.empty())
        - Call orchestrator's run_validation_with_correction() with progress callback
        - Progress callback updates containers in-place via `with container:`
        - NO reruns until loop completes
        - NO loop duplication - orchestrator owns the loop logic

    Returns:
        dict: Final result from run_validation_with_correction()
    """

    # Get settings
    max_iterations = st.session_state.settings.get('max_correction_iterations', 3)
    quality_thresholds = st.session_state.settings.get('quality_thresholds')

    # ========================================================================
    # STEP 1: Create st.empty() placeholder containers
    # ========================================================================
    # These containers are created ONCE and will be updated in-place during the loop

    st.markdown("### Step 3: Validation & Correction (Iterative)")

    # Container 1: Current iteration status
    iteration_status_container = st.empty()

    # Container 2: Progress bar
    progress_bar_container = st.empty()

    # Container 3: Current metrics (latest iteration)
    current_metrics_container = st.empty()

    # Container 4: Iteration history table
    history_table_container = st.empty()

    # Container 5: Quality trend chart
    quality_chart_container = st.empty()

    # ========================================================================
    # STEP 2: Create Progress Callback Function
    # ========================================================================
    # This callback receives events from the orchestrator and updates UI containers

    # Shared state for callback (accessible across callback invocations)
    iterations_history = []  # Track all iterations for history table/chart

    def progress_callback(step_name: str, status: str, data: dict):
        """
        Callback invoked by orchestrator to update UI.

        Events:
            - status="starting", data={'iteration': N, 'step': 'validation'|'correction'}
            - status="completed", data={'final_status': 'passed'|'max_iterations_reached'|...}
            - (Can be extended with more granular events)
        """
        nonlocal iterations_history

        iteration_num = data.get('iteration', 0)
        step_type = data.get('step', 'unknown')

        # ----------------------------------------------------------------
        # Update UI: Status message
        # ----------------------------------------------------------------
        if status == "starting":
            with iteration_status_container:
                if step_type == "validation":
                    if iteration_num == 0:
                        st.info(f"⏳ Running initial validation (iteration {iteration_num}/{max_iterations})")
                    else:
                        st.info(f"⏳ Validating corrected extraction (iteration {iteration_num}/{max_iterations})")
                elif step_type == "correction":
                    st.info(f"⏳ Running correction {iteration_num}/{max_iterations}...")

            # Update progress bar
            with progress_bar_container:
                # Rough progress: each iteration has 2 steps (validation + correction)
                # Total steps = (max_iterations + 1) validations + max_iterations corrections
                progress = iteration_num / (max_iterations + 1)
                st.progress(min(progress, 1.0))
                st.caption(f"Iteration {iteration_num + 1} of {max_iterations + 1}")

        elif status == "completed":
            final_status = data.get('final_status', 'unknown')

            with iteration_status_container:
                if final_status == "passed":
                    st.success(f"✅ Quality thresholds met at iteration {data.get('iterations', 0)}!")
                elif final_status == "max_iterations_reached":
                    best_iter = data.get('best_iteration', 0)
                    st.warning(f"⚠️ Max iterations reached. Using best result (iteration {best_iter}).")
                elif final_status == "early_stopped_degradation":
                    best_iter = data.get('best_iteration', 0)
                    st.warning(f"⚠️ Early stopping: quality degraded. Using best (iteration {best_iter}).")
                elif "failed" in final_status:
                    st.error(f"❌ Execution failed: {final_status}")

            # Final progress
            with progress_bar_container:
                st.progress(1.0)

        # ----------------------------------------------------------------
        # Update UI: Metrics (if iteration data provided)
        # ----------------------------------------------------------------
        iteration_data = data.get('iteration_data')  # From orchestrator
        if iteration_data:
            iterations_history.append(iteration_data)
            metrics = iteration_data['metrics']

            # Current metrics
            with current_metrics_container:
                st.markdown("#### 📊 Current Iteration Metrics")
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    comp = metrics.get('completeness_score', 0)
                    comp_threshold = quality_thresholds['completeness_score']
                    comp_status = "✅" if comp >= comp_threshold else "⚠️"
                    st.metric(
                        f"{comp_status} Completeness",
                        f"{comp:.1%}",
                        delta=f"Target: {comp_threshold:.0%}"
                    )

                with col2:
                    acc = metrics.get('accuracy_score', 0)
                    acc_threshold = quality_thresholds['accuracy_score']
                    acc_status = "✅" if acc >= acc_threshold else "⚠️"
                    st.metric(
                        f"{acc_status} Accuracy",
                        f"{acc:.1%}",
                        delta=f"Target: {acc_threshold:.0%}"
                    )

                with col3:
                    schema = metrics.get('schema_compliance_score', 0)
                    schema_threshold = quality_thresholds['schema_compliance_score']
                    schema_status = "✅" if schema >= schema_threshold else "⚠️"
                    st.metric(
                        f"{schema_status} Schema",
                        f"{schema:.1%}",
                        delta=f"Target: {schema_threshold:.0%}"
                    )

                with col4:
                    critical = metrics.get('critical_issues', 0)
                    critical_status = "✅" if critical == 0 else "❌"
                    st.metric(
                        f"{critical_status} Critical Issues",
                        f"{critical}",
                        delta="Must be 0"
                    )

            # History table
            with history_table_container:
                st.markdown("#### 📋 Iteration History")

                import pandas as pd
                history_data = []
                for it in iterations_history:
                    m = it['metrics']
                    history_data.append({
                        'Iteration': it['iteration_num'],
                        'Completeness': f"{m.get('completeness_score', 0):.1%}",
                        'Accuracy': f"{m.get('accuracy_score', 0):.1%}",
                        'Schema': f"{m.get('schema_compliance_score', 0):.1%}",
                        'Critical': m.get('critical_issues', 0),
                        'Overall': f"{m.get('overall_quality', 0):.1%}"
                    })

                df = pd.DataFrame(history_data)
                st.dataframe(df, use_container_width=True)

            # Quality chart
            with quality_chart_container:
                st.markdown("#### 📈 Quality Improvement Trajectory")

                chart_data = pd.DataFrame({
                    'Iteration': [it['iteration_num'] for it in iterations_history],
                    'Completeness': [it['metrics']['completeness_score'] for it in iterations_history],
                    'Accuracy': [it['metrics']['accuracy_score'] for it in iterations_history],
                    'Schema': [it['metrics']['schema_compliance_score'] for it in iterations_history],
                }).set_index('Iteration')

                st.line_chart(chart_data)

    # ========================================================================
    # STEP 3: Call Orchestrator with Callback
    # ========================================================================
    # The orchestrator owns the loop logic - we just provide UI updates

    result = run_validation_with_correction(
        pdf_path=pdf_path,
        extraction_result=extraction_result,
        classification_result=classification_result,
        llm_provider=llm_provider,
        file_manager=file_manager,
        max_iterations=max_iterations,
        quality_thresholds=quality_thresholds,
        progress_callback=progress_callback
    )

    return result
```

**Key Benefits van deze Approach**:

1. **Zero Reruns binnen Loop**:
   - Huidige: 2 reruns per iteratie (mark running + after step)
   - Nieuwe: 0 reruns binnen loop, alleen 1 rerun na completion
   - Bij 3 iteraties: bespaart 6 reruns = ~600ms

2. **Smooth Visual Updates**:
   - History table groeit incrementeel (geen flikkering)
   - Chart updates live (smooth animation)
   - Metrics update instantly na elke validation

3. **Better UX**:
   - User ziet continue progress
   - No page reloads tussen iteraties
   - Feels more "real-time" and responsive

4. **Maintains Responsiveness**:
   - Hele loop is binnen één step execution
   - User kan niet "Back" clicken tijdens loop (correct behavior)
   - Na completion: normal UI flow resumes met rerun

5. **Streamlit 2024 Best Practice**:
   - st.empty() is recommended voor this exact use case
   - Fragments not applicable (blocking operations)
   - Aligns with Streamlit dashboard patterns

**When NOT to use st.empty()**:
- ❌ Between different pipeline steps (use st.rerun() - want user navigation)
- ❌ Voor button clicks (use st.rerun() naturally)
- ❌ Voor interactive widgets (use fragments or natural rerun)

**When TO use st.empty()**:
- ✅ Within-step iterations (zoals hier)
- ✅ Real-time data streaming
- ✅ Progressive result accumulation
- ✅ Live dashboards with polling

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

### Pre-Implementation Checklist

**Voordat je begint met Fase 1, verify de volgende**:

#### Bestaande Code Verification

1. **Orchestrator File**:
   - [ ] Open `src/pipeline/orchestrator.py`
   - [ ] Locate `run_single_step()` functie (noteer regelnummer: ______)
   - [ ] Locate `_run_validation_step()` functie (bestaat deze? Ja/Nee: ______)
   - [ ] Locate `_run_correction_step()` functie (bestaat deze? Ja/Nee: ______)

2. **Return Types Verification**:
   - [ ] Check `_run_validation_step()` signature:
     ```python
     def _run_validation_step(...) -> dict:
         # Returns validation result dict
     ```
   - [ ] Check `_run_correction_step()` signature:
     ```python
     def _run_correction_step(...) -> tuple[dict, dict]:
         # Returns (corrected_extraction, final_validation)
         # IMPORTANT: Sectie 3 regel 470 unpackt tuple:
         # corrected_extraction, _ = _run_correction_step(...)
     ```

#### Dependencies Verification

3. **Required Imports** (check if already in `orchestrator.py`):
   - [ ] `from pathlib import Path`
   - [ ] `from datetime import datetime`
   - [ ] `import time`
   - [ ] `from typing import Callable`
   - [ ] `from rich.console import Console` (voor `console.print()` in error handling)
   - [ ] `from src.llm import get_llm_provider` (of equivalent)
   - [ ] `from src.pipeline.file_manager import PipelineFileManager`

#### Test Setup

4. **Testing Infrastructure**:
   - [ ] Check `tests/unit/` directory exists
   - [ ] Verify `pytest` installed: `pytest --version` (should show >= 7.0)
   - [ ] Run existing tests: `pytest tests/unit/ -v` (should pass)
   - [ ] Check coverage tool: `pytest --cov=src.pipeline tests/unit/ --cov-report=term`

#### File Manager API Verification

5. **File Naming Support**:
   - [ ] Open `src/pipeline/file_manager.py`
   - [ ] Verify `save_json()` method supports `status` parameter:
     ```python
     def save_json(self, data: dict, file_type: str, status: str | None = None) -> Path:
         """
         status="corrected1" should produce: "paper-123-extraction-corrected1.json"
         (FileManager adds '-' separator automatically)
         """
     ```
   - [ ] Test in Python REPL:
     ```python
     from src.pipeline.file_manager import PipelineFileManager
     # Create test instance and verify status suffix works
     ```

**✅ All checks passed? Proceed to Fase 1**
**❌ Any check failed? Resolve dependency issues first**

---

### Fase 1: Core Loop Logic (Week 1)

**Doel**: Implementeer basis iterative loop zonder UI

**File**: `src/pipeline/orchestrator.py`
**Locatie**: Na `run_single_step()` functie (ca. regel 300-400, depends on codebase)

#### Imports to Add (top of file, if not present)

```python
from datetime import datetime
import time
from typing import Callable
from rich.console import Console

console = Console()  # For error logging
```

#### Implementation Order (dependencies)

1. ✅ Feature branch aanmaken
2. ✅ Feature document (dit document)

3. **Constants** (bij bestaande STEP_* constants):
   - [ ] `STEP_VALIDATION_CORRECTION = "validation_correction"` (zie regel 242)
   - [ ] `DEFAULT_QUALITY_THRESHOLDS` dict (zie sectie 2, regel 257-262)
   - [ ] Update `ALL_PIPELINE_STEPS` lijst (voeg nieuwe step toe)

4. **Helper Functions** (in deze volgorde - dependency order):
   - [ ] `is_quality_sufficient(validation_result, thresholds)` (sectie 2, regel 264-318)
     - **Dependencies**: None (standalone)
     - **Location**: Na constants, vóór main loop functie

   - [ ] `_extract_metrics(validation_result)` (sectie 6, regel 741-770)
     - **Dependencies**: None (standalone)
     - **Returns**: dict met all scores + computed 'overall_quality'

   - [ ] `_detect_quality_degradation(iterations, window=2)` (sectie 5, regel 616-659)
     - **Dependencies**: Calls `_extract_metrics()` indirectly (via iterations[]['metrics'])
     - **Fixed algorithm**: Uses `max(scores)` not `max(scores[:-window])`

   - [ ] `_select_best_iteration(iterations)` (sectie 6, regel 662-738)
     - **Dependencies**: Uses iteration['metrics'] (populated by `_extract_metrics()`)
     - **Returns**: Best iteration dict with 'selection_reason'

   - [ ] `_call_progress_callback(callback, step_name, status, data)` (NIEUW - small helper)
     - **Purpose**: Safe callback invocation with None check
     - **Implementation**:
       ```python
       def _call_progress_callback(
           callback: Callable | None,
           step_name: str,
           status: str,
           data: dict
       ):
           """Invoke progress callback if provided."""
           if callback is not None:
               callback(step_name, status, data)
       ```

5. **Main Loop Function**:
   - [ ] `run_validation_with_correction()` (sectie 3, regel 311-574)
     - **Dependencies**: ALL helper functions above
     - **Location**: After all helpers
     - **Integrated error handling**: try/except blocks binnen loop (niet apart)
     - **Important**: Extract `publication_type` from `classification_result` (regel 324)
     - **Important**: Tuple unpacking for correction (regel 470): `corrected_extraction, _ = ...`

#### Testing

**Create Test File**: `tests/unit/test_iterative_validation_correction.py`

- [ ] Copy test template from sectie "Testing Strategie" (regel 1539-1818)
- [ ] Implement `TestQualityAssessment` class (7 tests including edge cases)
- [ ] Implement `TestBestIterationSelection` class (4 tests)
- [ ] Implement `TestEarlyStoppingAlgorithm` class (3 tests)
- [ ] Implement `TestIterativeLoop` class (3 tests with mocks)
- [ ] Implement `TestEdgeCases` class (8 tests - NEW in v1.3)

**Run Tests**:
```bash
# Run all tests
pytest tests/unit/test_iterative_validation_correction.py -v

# Run with coverage
pytest tests/unit/test_iterative_validation_correction.py --cov=src.pipeline.orchestrator --cov-report=term-missing

# Target: >95% coverage for new functions
```

**Deliverable**:
- ✅ Werkende loop logica in `orchestrator.py`
- ✅ ~350 lines of new code (7 functions)
- ✅ ~400 lines of tests (4 test classes, 25+ tests)
- ✅ >95% code coverage
- ✅ All tests passing

### Fase 2: File Management & Persistence (Week 1-2)

**Doel**: Alle iteraties correct opslaan met juiste naming

**IMPORTANT NOTE**: Er is GEEN "lazy loading" - alle iteraties blijven in memory tijdens loop execution (zie sectie 3, regel 316: `iterations = []`). Deze fase verifieert alleen dat file saving correct werkt.

#### File Naming Strategy (zie sectie 7, regel 790-817)

**Pattern**:
```
tmp/paper-123-extraction.json                  # Iteration 0 (initial)
tmp/paper-123-validation.json                  # Iteration 0 validation

tmp/paper-123-extraction-corrected1.json       # Iteration 1 (after 1st correction)
tmp/paper-123-validation-corrected1.json       # Iteration 1 validation

tmp/paper-123-extraction-corrected2.json       # Iteration 2
tmp/paper-123-validation-corrected2.json       # Iteration 2 validation

tmp/paper-123-extraction-corrected3.json       # Iteration 3 (MAX)
tmp/paper-123-validation-corrected3.json       # Iteration 3 validation
```

#### Implementatie

**File**: `src/pipeline/orchestrator.py` (binnen `run_validation_with_correction()`)

1. **Verification** (Pre-Implementation Checklist already covers this):
   - [ ] Verify `file_manager.save_json(data, type, status="corrected1")` werkt
   - [ ] Check bestaande code in sectie 7 (regel 806-817) - geen wijzigingen nodig aan FileManager zelf

2. **Implementeer File Saving in Loop** (sectie 3):
   - [ ] **Validation save** (regel 364-369):
     ```python
     suffix = f"corrected{iteration_num}" if iteration_num > 0 else None
     validation_file = file_manager.save_json(
         validation_result,
         "validation",
         status=suffix  # FileManager adds '-' between step and status
     )
     ```
   - [ ] **Extraction save** (regel 481-486):
     ```python
     corrected_file = file_manager.save_json(
         corrected_extraction,
         "extraction",
         status=f"corrected{iteration_num}"  # FileManager adds '-'
     )
     ```
   - [ ] **Add logging** after each save:
     ```python
     console.print(f"[dim]Saved: {validation_file}[/dim]")
     ```

3. **Iteratie Metadata** (al in code):
   - [ ] Verify `iteration_data` dict contains (regel 372-378):
     - `iteration_num`
     - `extraction` (full dict - kept in memory)
     - `validation` (full dict - kept in memory)
     - `metrics` (computed scores)
     - `timestamp`
   - [ ] Deze data blijft in `iterations = []` list (geen disk persistence nodig)

#### Testing

**File**: `tests/unit/test_file_management.py` (nieuwe file)

```python
from src.pipeline.file_manager import PipelineFileManager
from pathlib import Path
import json

class TestIterationFileNaming:
    """Test dat iteration files correct benaamd worden."""

    def test_iteration_0_no_suffix(self, tmp_path):
        """Iteration 0 krijgt geen suffix."""
        fm = PipelineFileManager(output_dir=tmp_path, paper_id="test-123")

        path = fm.save_json({"test": "data"}, "validation", status=None)
        assert path.name == "test-123-validation.json"

    def test_iteration_1_corrected_suffix(self, tmp_path):
        """Iteration 1 krijgt corrected1 suffix (met -)."""
        fm = PipelineFileManager(output_dir=tmp_path, paper_id="test-123")

        path = fm.save_json({"test": "data"}, "extraction", status="corrected1")
        assert path.name == "test-123-extraction-corrected1.json"

    def test_all_iterations_saved(self, tmp_path):
        """Simuleer volledige loop - alle files moeten er zijn."""
        fm = PipelineFileManager(output_dir=tmp_path, paper_id="test-123")
        max_iterations = 3

        # Save iteration 0
        fm.save_json({"iter": 0}, "validation", status=None)
        fm.save_json({"iter": 0}, "extraction", status=None)

        # Save iterations 1-3
        for i in range(1, max_iterations + 1):
            fm.save_json({"iter": i}, "validation", status=f"-corrected{i}")
            fm.save_json({"iter": i}, "extraction", status=f"-corrected{i}")

        # Verify all files exist
        expected_files = [
            "test-123-validation.json",
            "test-123-extraction.json",
            "test-123-validation-corrected1.json",
            "test-123-extraction-corrected1.json",
            "test-123-validation-corrected2.json",
            "test-123-extraction-corrected2.json",
            "test-123-validation-corrected3.json",
            "test-123-extraction-corrected3.json",
        ]

        for filename in expected_files:
            filepath = tmp_path / filename
            assert filepath.exists(), f"Missing file: {filename}"

            # Verify JSON is valid
            with open(filepath) as f:
                data = json.load(f)
                assert "iter" in data
```

**Run Tests**:
```bash
pytest tests/unit/test_file_management.py -v
```

**Deliverable**:
- ✅ File saving correct geïmplementeerd in loop
- ✅ Alle iteraties opgeslagen met correcte naming (-correctedN suffix)
- ✅ Logging toegevoegd voor traceability
- ✅ Tests verifiëren file naming correctheid
- ✅ **NO lazy loading** (verwarrende term verwijderd)

### Fase 3: Backward Compatibility (Week 2)

**Doel**: Bestaande code blijft werken, nieuwe step is beschikbaar

**File**: `src/pipeline/orchestrator.py`

#### 1. Add New Constant (bij bestaande STEP_* constants)

```python
# Existing constants (verify these exist):
STEP_CLASSIFICATION = "classification"
STEP_EXTRACTION = "extraction"
STEP_VALIDATION = "validation"
STEP_CORRECTION = "correction"

# NEW: Add combined step
STEP_VALIDATION_CORRECTION = "validation_correction"  # <-- ADD THIS
```

#### 2. Update Pipeline Steps List

```python
# Find ALL_PIPELINE_STEPS (waarschijnlijk ca. regel 50-100)
ALL_PIPELINE_STEPS = [
    STEP_CLASSIFICATION,
    STEP_EXTRACTION,
    STEP_VALIDATION_CORRECTION,  # <-- ADD THIS (nieuwe gecombineerde stap)
    # NOTE: STEP_VALIDATION en STEP_CORRECTION blijven beschikbaar voor CLI backward compat
]
```

#### 3. Update `run_single_step()` Function

**Locate**: `run_single_step()` functie in orchestrator.py

**Add elif-branch** (zie sectie 1, regel 220-237):

```python
def run_single_step(step_name: str, ...) -> dict:
    """
    Original function - blijft werken voor CLI en directe stap-aanroepen.

    Supported step_name values:
        - STEP_VALIDATION: Single validation run (no correction)
        - STEP_CORRECTION: Single correction run (no re-validation)
        - STEP_VALIDATION_CORRECTION: New iterative workflow  # <-- DOCUMENT THIS
    """
    if step_name == STEP_CLASSIFICATION:
        return _run_classification_step(...)  # Unchanged

    elif step_name == STEP_EXTRACTION:
        return _run_extraction_step(...)  # Unchanged

    elif step_name == STEP_VALIDATION:
        return _run_validation_step(...)  # Unchanged - backward compat

    elif step_name == STEP_CORRECTION:
        return _run_correction_step(...)  # Unchanged - backward compat

    # NEW: Add this elif branch
    elif step_name == STEP_VALIDATION_CORRECTION:
        return run_validation_with_correction(
            pdf_path=pdf_path,
            extraction_result=extraction_result,
            classification_result=classification_result,
            llm_provider=llm_provider,
            file_manager=file_manager,
            max_iterations=max_iterations,  # From settings or default
            quality_thresholds=quality_thresholds,  # From settings or default
            progress_callback=progress_callback
        )

    else:
        raise ValueError(f"Unknown step: {step_name}")
```

**Parameters to add** (if not already in `run_single_step()` signature):
- [ ] `max_iterations: int = 3`
- [ ] `quality_thresholds: dict | None = None`
- [ ] `progress_callback: Callable | None = None`

#### 4. Verify Backward Compatibility

**CRITICAL**: Oude stappen blijven ONGEWIJZIGD werken:

- [ ] `STEP_VALIDATION` - blijft single validation run (geen correctie)
- [ ] `STEP_CORRECTION` - blijft single correction run (geen re-validatie)
- [ ] Bestaande code die deze stappen aanroept moet NIET breken

#### Testing

**File**: `tests/unit/test_backward_compatibility.py` (nieuwe file)

```python
import pytest
from src.pipeline.orchestrator import (
    run_single_step,
    STEP_VALIDATION,
    STEP_CORRECTION,
    STEP_VALIDATION_CORRECTION
)

class TestBackwardCompatibility:
    """Verify oude API blijft werken."""

    def test_old_validation_step_still_works(self, mock_dependencies):
        """STEP_VALIDATION moet nog steeds single validation run doen."""
        result = run_single_step(
            step_name=STEP_VALIDATION,
            **mock_dependencies
        )

        # Should return validation result, NOT loop result
        assert 'verification_summary' in result
        assert 'iterations' not in result  # Old API doesn't have iterations

    def test_old_correction_step_still_works(self, mock_dependencies):
        """STEP_CORRECTION moet nog steeds single correction run doen."""
        result = run_single_step(
            step_name=STEP_CORRECTION,
            **mock_dependencies
        )

        # Should return tuple (corrected_extraction, final_validation)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_new_combined_step_returns_loop_result(self, mock_dependencies):
        """STEP_VALIDATION_CORRECTION moet iterative loop result returnen."""
        result = run_single_step(
            step_name=STEP_VALIDATION_CORRECTION,
            max_iterations=2,
            **mock_dependencies
        )

        # Should return loop result with iterations
        assert 'iterations' in result
        assert 'final_status' in result
        assert 'best_extraction' in result
        assert 'best_validation' in result

    def test_all_pipeline_steps_includes_new_step(self):
        """ALL_PIPELINE_STEPS moet nieuwe step bevatten."""
        from src.pipeline.orchestrator import ALL_PIPELINE_STEPS

        assert STEP_VALIDATION_CORRECTION in ALL_PIPELINE_STEPS

    def test_old_steps_not_in_default_pipeline(self):
        """STEP_VALIDATION en STEP_CORRECTION zijn alleen voor CLI backward compat."""
        from src.pipeline.orchestrator import ALL_PIPELINE_STEPS

        # These are NOT in the default pipeline (alleen voor CLI)
        assert STEP_VALIDATION not in ALL_PIPELINE_STEPS
        assert STEP_CORRECTION not in ALL_PIPELINE_STEPS
```

**Run Tests**:
```bash
# Run backward compat tests
pytest tests/unit/test_backward_compatibility.py -v

# Run ALL existing tests - moeten ALLEMAAL slagen
pytest tests/unit/ -v

# If any test fails -> backward compatibility is broken -> FIX IT
```

**Regression Testing**:
```bash
# Run full test suite (unit + integration)
make test  # or: pytest tests/ -v

# Target: 100% van bestaande tests moet SLAGEN
```

**Deliverable**:
- ✅ `STEP_VALIDATION_CORRECTION` constant toegevoegd
- ✅ `ALL_PIPELINE_STEPS` updated met nieuwe step
- ✅ `run_single_step()` elif-branch toegevoegd
- ✅ Oude stappen (`STEP_VALIDATION`, `STEP_CORRECTION`) blijven werken
- ✅ Backward compatibility tests (5 tests)
- ✅ Alle bestaande tests slagen nog steeds

---

### Fase 3.5: CLI Support (Week 2)

**Doel**: Nieuwe step is aanroepbaar via command-line interface

**Assumption**: Project heeft een `src/cli.py` of equivalent voor command-line interface

#### 1. Verify CLI Structure

**Check existing CLI**:
- [ ] Locate CLI entry point (waarschijnlijk `src/cli.py` of `src/__main__.py`)
- [ ] Check if `--step` argument already exists
- [ ] Check how current steps are invoked (e.g., `--step extraction`)

#### 2. Add CLI Arguments for New Step

**If using `argparse`** (common pattern):

```python
# src/cli.py (or wherever CLI args are defined)

parser = argparse.ArgumentParser(description="PDF to Podcast Pipeline")

# Existing step argument
parser.add_argument(
    "--step",
    choices=[
        "classification",
        "extraction",
        "validation",  # Old - backward compat
        "correction",  # Old - backward compat
        "validation_correction",  # NEW: Add this
    ],
    help="Pipeline step to run"
)

# NEW: Arguments for validation_correction step
parser.add_argument(
    "--max-iterations",
    type=int,
    default=3,
    help="Maximum number of correction attempts (default: 3)"
)

parser.add_argument(
    "--completeness-threshold",
    type=float,
    default=0.90,
    help="Minimum completeness score (default: 0.90)"
)

parser.add_argument(
    "--accuracy-threshold",
    type=float,
    default=0.95,
    help="Minimum accuracy score (default: 0.95)"
)

parser.add_argument(
    "--schema-threshold",
    type=float,
    default=0.95,
    help="Minimum schema compliance score (default: 0.95)"
)
```

**If using `click`** (alternative pattern):

```python
# src/cli.py

import click

@click.command()
@click.option(
    "--step",
    type=click.Choice([
        "classification",
        "extraction",
        "validation",
        "correction",
        "validation_correction"  # NEW
    ])
)
@click.option("--max-iterations", default=3, help="Max correction attempts")
@click.option("--completeness-threshold", default=0.90)
@click.option("--accuracy-threshold", default=0.95)
@click.option("--schema-threshold", default=0.95)
def run(step, max_iterations, completeness_threshold, accuracy_threshold, schema_threshold):
    """Run pipeline step."""
    # ... CLI logic ...
```

#### 3. Wire Arguments to Orchestrator

**In CLI handler function**:

```python
# src/cli.py (in main/run function)

if args.step == "validation_correction":
    # Build quality thresholds from CLI args
    quality_thresholds = {
        'completeness_score': args.completeness_threshold,
        'accuracy_score': args.accuracy_threshold,
        'schema_compliance_score': args.schema_threshold,
        'critical_issues': 0  # Fixed - always 0
    }

    # Call orchestrator
    result = run_single_step(
        step_name=STEP_VALIDATION_CORRECTION,
        pdf_path=Path(args.pdf_path),
        extraction_result=load_extraction_result(),  # From previous step
        classification_result=load_classification_result(),  # From previous step
        llm_provider=args.llm_provider,
        file_manager=file_manager,
        max_iterations=args.max_iterations,
        quality_thresholds=quality_thresholds,
        progress_callback=None  # CLI heeft geen UI callback
    )

    # Print result summary
    print(f"Final status: {result['final_status']}")
    print(f"Iterations: {result['iteration_count']}")
    print(f"Best extraction: {result['best_extraction']}")
```

#### 4. Update CLI Help Text

- [ ] Add documentation for new step in `--help` output
- [ ] Example usage in help text:
  ```
  Examples:
    # Run with defaults
    python -m src.cli run --pdf-path paper.pdf --step validation_correction

    # Run with custom parameters
    python -m src.cli run \
      --pdf-path paper.pdf \
      --step validation_correction \
      --max-iterations 2 \
      --completeness-threshold 0.85
  ```

#### Testing

**Manual CLI Tests**:

```bash
# Test 1: Help text shows new step
python -m src.cli run --help
# Verify: validation_correction appears in --step choices

# Test 2: Run with defaults
python -m src.cli run \
  --pdf-path tests/data/sample.pdf \
  --step validation_correction \
  --llm-provider openai

# Expected output:
# - Progress messages during iterations
# - Final status (passed / max_iterations_reached)
# - Iteration count
# - Files created in tmp/ directory

# Test 3: Run with custom thresholds
python -m src.cli run \
  --pdf-path tests/data/sample.pdf \
  --step validation_correction \
  --max-iterations 2 \
  --completeness-threshold 0.85 \
  --accuracy-threshold 0.90 \
  --llm-provider openai

# Expected: Loop stops at max 2 iterations (or earlier if quality sufficient)

# Test 4: Verify output files
ls tmp/
# Expected files (voor max_iterations=2):
#   sample-extraction.json
#   sample-validation.json
#   sample-extraction-corrected1.json
#   sample-validation-corrected1.json
#   sample-extraction-corrected2.json
#   sample-validation-corrected2.json

# Test 5: Backward compat - old steps still work
python -m src.cli run --pdf-path tests/data/sample.pdf --step validation
python -m src.cli run --pdf-path tests/data/sample.pdf --step correction
# Expected: Both commands succeed (backward compat maintained)
```

**Automated CLI Tests** (optional):

```python
# tests/integration/test_cli.py

import subprocess
from pathlib import Path

class TestCLI:
    """Test CLI interface for new step."""

    def test_cli_help_shows_new_step(self):
        """--help moet nieuwe step tonen."""
        result = subprocess.run(
            ["python", "-m", "src.cli", "run", "--help"],
            capture_output=True,
            text=True
        )

        assert "validation_correction" in result.stdout
        assert "--max-iterations" in result.stdout

    def test_cli_runs_new_step_successfully(self, test_pdf_path):
        """CLI moet nieuwe step kunnen uitvoeren."""
        result = subprocess.run([
            "python", "-m", "src.cli", "run",
            "--pdf-path", str(test_pdf_path),
            "--step", "validation_correction",
            "--max-iterations", "1",
            "--llm-provider", "openai"
        ], capture_output=True, text=True)

        assert result.returncode == 0
        assert "Final status:" in result.stdout
```

**Run Tests**:
```bash
# Manual tests (zie hierboven)

# Automated tests
pytest tests/integration/test_cli.py -v
```

**Deliverable**:
- ✅ CLI `--step validation_correction` werkt
- ✅ CLI arguments voor thresholds en max_iterations
- ✅ Help text updated met examples
- ✅ Output files correct aangemaakt (-correctedN suffixes)
- ✅ Backward compatibility verified (oude steps werken nog)
- ✅ CLI tests (manual + optioneel automated)

---

### Fase 4: Streamlit UI Integration met st.empty() (Week 2-3)

**Doel**: UI voor iterative loop met real-time updates

#### File 1: Settings Screen - Add Configuration UI

**File**: `src/streamlit_app/screens/settings.py`

**Locate**: Settings form (ca. regel 50-150, waar andere pipeline settings staan)

**Add nieuwe sectie** (zie sectie "UI/UX Ontwerp", regel 907-958):

```python
# src/streamlit_app/screens/settings.py

import streamlit as st

# ... existing settings code ...

# NEW: Add Validation & Correction Settings sectie
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

# Threshold sliders (cap at 0.99 to prevent infinite loops!)
completeness_threshold = st.slider(
    "Completeness threshold",
    min_value=0.5,
    max_value=0.99,  # <-- CAP at 99%, not 1.0!
    value=0.90,
    step=0.05,
    help="Minimum required completeness score (0.90 = 90%). Max 99% - requiring perfect scores would prevent loop termination."
)

accuracy_threshold = st.slider(
    "Accuracy threshold",
    min_value=0.5,
    max_value=0.99,  # <-- CAP at 99%, not 1.0!
    value=0.95,
    step=0.05,
    help="Minimum required accuracy score (0.95 = 95%). Max 99% - requiring perfect scores would prevent loop termination."
)

schema_compliance_threshold = st.slider(
    "Schema compliance threshold",
    min_value=0.5,
    max_value=0.99,  # <-- CAP at 99%, not 1.0!
    value=0.95,
    step=0.05,
    help="Minimum required schema compliance score. Max 99% - requiring perfect scores would prevent loop termination."
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

#### File 2: Session State - Initialize Defaults

**File**: `src/streamlit_app/__init__.py`

**Locate**: `init_session_state()` functie

**Add default values** (zie sectie "Configuratie", regel 1394-1411):

```python
# src/streamlit_app/__init__.py

def init_session_state():
    """Initialize all session state variables."""

    # ... existing initialization code ...

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

#### File 3: Execution Screen - Add Step Display Function

**File**: `src/streamlit_app/screens/execution.py`

**Locate**: After bestaande `display_*_step()` functies (e.g., `display_extraction_step()`)

**Add imports** (top of file):

```python
import pandas as pd  # For history table
from src.pipeline.orchestrator import run_validation_with_correction, STEP_VALIDATION_CORRECTION
```

**Add nieuwe functie** (zie sectie 4, regel 1133-1346):

```python
def display_validation_correction_step(
    pdf_path: Path,
    extraction_result: dict,
    classification_result: dict,
    llm_provider: str,
    file_manager: PipelineFileManager
) -> dict:
    """
    Display and execute iterative validation-correction with real-time UI updates.

    Architecture:
        - Create st.empty() containers upfront
        - Call orchestrator with progress callback
        - Progress callback updates containers in-place
        - NO reruns until loop completes
        - NO loop duplication - orchestrator owns logic
    """

    # Get settings
    max_iterations = st.session_state.settings.get('max_correction_iterations', 3)
    quality_thresholds = st.session_state.settings.get('quality_thresholds')

    # ========================================================================
    # STEP 1: Create st.empty() placeholder containers
    # ========================================================================
    st.markdown("### Step 3: Validation & Correction (Iterative)")

    # 5 containers for in-place updates
    iteration_status_container = st.empty()
    progress_bar_container = st.empty()
    current_metrics_container = st.empty()
    history_table_container = st.empty()
    quality_chart_container = st.empty()

    # ========================================================================
    # STEP 2: Create Progress Callback Function
    # ========================================================================
    iterations_history = []  # Shared state for callback

    def progress_callback(step_name: str, status: str, data: dict):
        """Callback invoked by orchestrator to update UI."""
        nonlocal iterations_history

        iteration_num = data.get('iteration', 0)
        step_type = data.get('step', 'unknown')

        # Update status message
        if status == "starting":
            with iteration_status_container:
                if step_type == "validation":
                    if iteration_num == 0:
                        st.info(f"⏳ Running initial validation (iteration {iteration_num}/{max_iterations})")
                    else:
                        st.info(f"⏳ Validating corrected extraction (iteration {iteration_num}/{max_iterations})")
                elif step_type == "correction":
                    st.info(f"⏳ Running correction {iteration_num}/{max_iterations}...")

            # Update progress bar
            with progress_bar_container:
                progress = iteration_num / (max_iterations + 1)
                st.progress(min(progress, 1.0))
                st.caption(f"Iteration {iteration_num + 1} of {max_iterations + 1}")

        elif status == "completed":
            final_status = data.get('final_status', 'unknown')

            with iteration_status_container:
                if final_status == "passed":
                    st.success(f"✅ Quality thresholds met at iteration {data.get('iterations', 0)}!")
                elif final_status == "max_iterations_reached":
                    best_iter = data.get('best_iteration', 0)
                    st.warning(f"⚠️ Max iterations reached. Using best result (iteration {best_iter}).")
                elif final_status == "early_stopped_degradation":
                    best_iter = data.get('best_iteration', 0)
                    st.warning(f"⚠️ Early stopping: quality degraded. Using best (iteration {best_iter}).")
                elif "failed" in final_status:
                    st.error(f"❌ Execution failed: {final_status}")

            with progress_bar_container:
                st.progress(1.0)

        # Update metrics/history if iteration data provided
        iteration_data = data.get('iteration_data')
        if iteration_data:
            iterations_history.append(iteration_data)
            metrics = iteration_data['metrics']

            # Current metrics (4 columns)
            with current_metrics_container:
                st.markdown("#### 📊 Current Iteration Metrics")
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    comp = metrics.get('completeness_score', 0)
                    comp_threshold = quality_thresholds['completeness_score']
                    comp_status = "✅" if comp >= comp_threshold else "⚠️"
                    st.metric(f"{comp_status} Completeness", f"{comp:.1%}", delta=f"Target: {comp_threshold:.0%}")

                with col2:
                    acc = metrics.get('accuracy_score', 0)
                    acc_threshold = quality_thresholds['accuracy_score']
                    acc_status = "✅" if acc >= acc_threshold else "⚠️"
                    st.metric(f"{acc_status} Accuracy", f"{acc:.1%}", delta=f"Target: {acc_threshold:.0%}")

                with col3:
                    schema = metrics.get('schema_compliance_score', 0)
                    schema_threshold = quality_thresholds['schema_compliance_score']
                    schema_status = "✅" if schema >= schema_threshold else "⚠️"
                    st.metric(f"{schema_status} Schema", f"{schema:.1%}", delta=f"Target: {schema_threshold:.0%}")

                with col4:
                    critical = metrics.get('critical_issues', 0)
                    critical_status = "✅" if critical == 0 else "❌"
                    st.metric(f"{critical_status} Critical Issues", f"{critical}", delta="Must be 0")

            # History table
            with history_table_container:
                st.markdown("#### 📋 Iteration History")
                history_data = []
                for it in iterations_history:
                    m = it['metrics']
                    history_data.append({
                        'Iteration': it['iteration_num'],
                        'Completeness': f"{m.get('completeness_score', 0):.1%}",
                        'Accuracy': f"{m.get('accuracy_score', 0):.1%}",
                        'Schema': f"{m.get('schema_compliance_score', 0):.1%}",
                        'Critical': m.get('critical_issues', 0),
                        'Overall': f"{m.get('overall_quality', 0):.1%}"
                    })

                df = pd.DataFrame(history_data)
                st.dataframe(df, use_container_width=True)

            # Quality chart
            with quality_chart_container:
                st.markdown("#### 📈 Quality Improvement Trajectory")
                chart_data = pd.DataFrame({
                    'Iteration': [it['iteration_num'] for it in iterations_history],
                    'Completeness': [it['metrics']['completeness_score'] for it in iterations_history],
                    'Accuracy': [it['metrics']['accuracy_score'] for it in iterations_history],
                    'Schema': [it['metrics']['schema_compliance_score'] for it in iterations_history],
                }).set_index('Iteration')

                st.line_chart(chart_data)

    # ========================================================================
    # STEP 3: Call Orchestrator with Callback
    # ========================================================================
    result = run_validation_with_correction(
        pdf_path=pdf_path,
        extraction_result=extraction_result,
        classification_result=classification_result,
        llm_provider=llm_provider,
        file_manager=file_manager,
        max_iterations=max_iterations,
        quality_thresholds=quality_thresholds,
        progress_callback=progress_callback
    )

    return result
```

**Integrate in execution flow** (main execution logic):

```python
# src/streamlit_app/screens/execution.py (in main execution function)

# ... existing step handling code ...

elif current_step == STEP_VALIDATION_CORRECTION:
    result = display_validation_correction_step(
        pdf_path=st.session_state.pdf_path,
        extraction_result=st.session_state.step_status[STEP_EXTRACTION]['result'],
        classification_result=st.session_state.step_status[STEP_CLASSIFICATION]['result'],
        llm_provider=st.session_state.settings['llm_provider'],
        file_manager=st.session_state.file_manager
    )
    st.session_state.step_status[STEP_VALIDATION_CORRECTION]['result'] = result
    st.session_state.step_status[STEP_VALIDATION_CORRECTION]['status'] = 'completed'
```

#### Testing

**Manual UI Tests** (run Streamlit app):

```bash
# Start Streamlit app
streamlit run src/streamlit_app/main.py

# Test 1: Settings screen
# - Navigate to Settings
# - Verify "Validation & Correction Settings" sectie exists
# - Adjust max_iterations slider (1-5)
# - Adjust threshold sliders (verify capped at 0.99)
# - Save settings

# Test 2: Execute nieuwe step
# - Upload PDF
# - Run classification + extraction
# - Run "Validation & Correction" step
# - Verify:
#   - Iteration status updates in real-time
#   - Progress bar fills incrementeel
#   - Current metrics update na elke validation
#   - History table grows with each iteration
#   - Quality chart updates live
#   - NO page flickering (zero reruns binnen loop)

# Test 3: Different scenarios
# Scenario A: Snel convergeren (quality sufficient after 1 iteration)
# - Expected: Loop stops at iteration 1, shows success message

# Scenario B: Max iterations (quality never sufficient)
# - Set low thresholds (e.g., 0.99 for all)
# - Expected: Loop runs all 3 iterations, shows "max iterations" warning

# Scenario C: Early stopping (quality degradation)
# - (Difficult to test manually - requires specific paper)

# Scenario D: Failure (schema validation fails)
# - (Requires corrupted extraction)
```

**Performance Measurement**:

```python
# Add temporary logging to measure rerun overhead
# In display_validation_correction_step():

import time

start_time = time.time()
rerun_count = 0  # Should remain 0 during loop

# ... (after loop completes) ...

elapsed = time.time() - start_time
console.print(f"[cyan]Performance: {elapsed:.2f}s, {rerun_count} reruns during loop[/cyan]")
# Expected: rerun_count = 0 (no reruns between iterations)
```

**Deliverable**:
- ✅ Settings UI met sliders voor max_iterations en thresholds
- ✅ Session state initialized met defaults
- ✅ `display_validation_correction_step()` functie (170 lines)
- ✅ 5 st.empty() containers met in-place updates
- ✅ Progress callback implementation
- ✅ Integration in execution flow
- ✅ 0 reruns binnen loop (verified via manual testing)
- ✅ Smooth real-time updates zonder flikkering

### Fase 5: Edge Cases & Polish (Week 3-4)

**Doel**: Verify en test error handling (already implemented in Sectie 3)

**IMPORTANT NOTE**: Error handling code is ALREADY defined in **Sectie 3: Loop Logica** (regels 516-587). Deze fase gaat NIET over nieuwe implementatie, maar over **testen en verifiëren** van die bestaande logic.

#### Error Handling - Already Implemented in Sectie 3

**Reference**: See Sectie 3, regels 516-587 voor volledige implementatie.

**1. LLM Provider Failures** (regel 516-560):
```python
except LLMProviderError as e:
    # Exponential backoff retry: 1s, 2s, 4s
    max_retries = 3
    # Retry validation or correction based on stage
    # If all retries fail → return best iteration so far
```

**2. JSON Decode Errors** (regel 571-583):
```python
except json.JSONDecodeError as e:
    # Correction returned invalid JSON → critical error
    # Return best iteration so far
```

**3. Unexpected Errors** (regel 585-598):
```python
except Exception as e:
    # Catch-all for unexpected errors
    # Return best iteration with status="failed_unexpected"
```

**4. Schema Validation Failures** (regel 367-389):
```python
# Check quality_score < 0.5 → STOP immediately
# This is NOT an exception, but early exit logic
```

#### Verification Tasks

**Task 1: Verify LLM Retry Logic** (already implemented in Sectie 3, regel 516-560)

**File**: `src/pipeline/orchestrator.py` → `run_validation_with_correction()`

**Verify**:
- [ ] Locate `except LLMProviderError` block (should be ca. regel 350-400)
- [ ] Verify retry loop: `for retry in range(max_retries):`
- [ ] Verify exponential backoff: `wait_time = 2 ** retry`
- [ ] Verify retry distinguishes validation vs correction stage
- [ ] Verify fallback: `if not retry_successful: return best iteration`

**Test**:
```bash
# Unit test - mock LLM failure
pytest tests/unit/test_iterative_validation_correction.py::test_llm_retry_logic -v

# Expected behavior:
# - LLM call fails → waits 1s → retry
# - Retry fails → waits 2s → retry
# - Retry fails → waits 4s → retry
# - All retries fail → returns best iteration with status="failed_llm"
```

**Task 2: Verify JSON Decode Error Handling** (already implemented in Sectie 3, regel 571-583)

**File**: Same file, same function

**Verify**:
- [ ] Locate `except json.JSONDecodeError` block
- [ ] Verify logs error with iteration number
- [ ] Verify returns best iteration with status="failed_json_decode"

**Test**:
```bash
# Unit test - mock invalid JSON from correction
pytest tests/unit/test_iterative_validation_correction.py::test_json_decode_error -v

# Expected behavior:
# - Correction returns malformed JSON → caught
# - Loop stops immediately (no retry for JSON errors)
# - Returns best iteration so far
```

**Task 3: Verify Unexpected Error Handling** (already implemented in Sectie 3, regel 585-598)

**File**: Same file, same function

**Verify**:
- [ ] Locate `except Exception as e` catch-all block
- [ ] Verify logs error type and message
- [ ] Verify returns best iteration with status="failed_unexpected"

**Test**:
```bash
# Unit test - mock unexpected error (e.g., file system error)
pytest tests/unit/test_iterative_validation_correction.py::test_unexpected_error -v
```

**Task 4: Verify Schema Validation Early Exit** (already in Sectie 3, regel 367-389)

**File**: Same file, same function

**Verify**:
- [ ] Locate quality_score check: `if quality_score < 0.5:`
- [ ] Verify immediate return with status="failed_schema_validation"
- [ ] Verify DOES NOT increment iteration counter

**Test**:
```bash
# Integration test - provide extraction with severe schema violations
pytest tests/integration/test_schema_validation_failure.py -v

# Expected behavior:
# - Initial validation detects quality_score < 0.5
# - Loop exits immediately (no correction attempted)
# - Returns status="failed_schema_validation"
```

**Task 5: Integration Testing - Full Pipeline with Errors**

**Scenario A: Rate Limit Simulation** (tests LLM retry logic)

```bash
# Mock LLM provider to return 429 (rate limit) on first 2 calls
pytest tests/integration/test_rate_limit_recovery.py -v

# Expected:
# - First call fails (429) → retry after 1s
# - Second call fails (429) → retry after 2s
# - Third call succeeds → loop continues normally
```

**Scenario B: Long-Running Test** (5+ iterations)

```bash
# Force low quality thresholds (0.99 for all) to trigger max iterations
pytest tests/integration/test_long_running_loop.py -v --timeout=180

# Expected:
# - Loop runs all 5 iterations
# - No memory leaks (check memory usage)
# - Returns best iteration with status="max_iterations_reached"
```

**Scenario C: Partial Failure Recovery**

```bash
# Simulate failure at iteration 2 (after 1 successful iteration)
pytest tests/integration/test_partial_failure.py -v

# Expected:
# - Iteration 0: validation succeeds
# - Iteration 1: correction succeeds
# - Iteration 2: LLM fails (all retries exhausted)
# - Returns iteration 1 result (best so far)
```

#### Logging & Diagnostics - Already Implemented

**Reference**: Sectie 3 already includes `console.print()` statements for all critical events.

**Verify**:
- [ ] Line ~523: LLM retry warning
- [ ] Line ~573: JSON decode error
- [ ] Line ~587: Unexpected error
- [ ] Line ~368: Schema validation failure

**Enhancement (optional)**:
```python
# Add structured logging voor production
import logging

logger = logging.getLogger(__name__)

# Replace console.print with logger calls:
logger.warning(f"LLM retry {retry+1}/{max_retries}")
logger.error(f"JSON decode failed: {str(e)}")
```

**Test Logging Output**:
```bash
# Run with verbose logging
pytest tests/unit/test_iterative_validation_correction.py -v --log-cli-level=DEBUG

# Verify all error events are logged with proper severity
```

#### Deliverable

**Code Verification**:
- ✅ Verify all 4 error handling blocks exist in orchestrator.py
- ✅ Verify retry logic with exponential backoff
- ✅ Verify fallback to best iteration in all failure modes

**Test Coverage**:
- ✅ Unit tests for each error type (LLM, JSON, unexpected, schema)
- ✅ Integration tests for rate limit recovery
- ✅ Long-running test (5+ iterations) zonder memory leaks
- ✅ Partial failure recovery test

**Production Readiness**:
- ✅ All error scenarios gracefully handled
- ✅ Structured logging in place (optional enhancement)
- ✅ Test coverage >95% for error handling paths
- ✅ Performance verified (no excessive retries, no memory leaks)

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


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_quality_assessment_with_none_validation_result(self):
        """Test that None validation_result returns False."""
        assert is_quality_sufficient(None) is False

    def test_quality_assessment_with_empty_dict(self):
        """Test that empty dict returns False."""
        assert is_quality_sufficient({}) is False

    def test_quality_assessment_with_missing_verification_summary(self):
        """Test that missing verification_summary returns False."""
        validation = {'some_other_key': 'value'}
        assert is_quality_sufficient(validation) is False

    def test_quality_assessment_with_none_score_values(self):
        """Test that None score values are treated as 0 (fail)."""
        validation = {
            'verification_summary': {
                'completeness_score': None,  # None treated as 0
                'accuracy_score': 0.98,
                'schema_compliance_score': 0.97,
                'critical_issues': 0
            }
        }
        assert is_quality_sufficient(validation) is False  # 0 < 0.90

    def test_best_iteration_with_equal_scores(self):
        """Test tie-breaking behavior when scores are equal."""
        iterations = [
            {'iteration_num': 0, 'metrics': {'overall_quality': 0.85, 'completeness_score': 0.80, 'critical_issues': 0}},
            {'iteration_num': 1, 'metrics': {'overall_quality': 0.85, 'completeness_score': 0.85, 'critical_issues': 0}},  # Equal overall but higher completeness
        ]
        best = _select_best_iteration(iterations)
        # Should select iteration 1 due to higher completeness tiebreaker
        assert best['iteration_num'] == 1

    def test_early_stopping_with_minimal_iterations(self):
        """Test early stopping doesn't trigger with < 3 iterations."""
        iterations = [
            {'iteration_num': 0, 'metrics': {'overall_quality': 0.90}},
            {'iteration_num': 1, 'metrics': {'overall_quality': 0.85}},  # Only 2 iterations
        ]
        # Need at least 3 iterations to detect degradation (window=2)
        assert _detect_quality_degradation(iterations, window=2) is False

    def test_early_stopping_with_peak_at_start(self):
        """Test early stopping when best score is iteration 0."""
        iterations = [
            {'iteration_num': 0, 'metrics': {'overall_quality': 0.95}},  # PEAK
            {'iteration_num': 1, 'metrics': {'overall_quality': 0.90}},
            {'iteration_num': 2, 'metrics': {'overall_quality': 0.88}},
        ]
        # Last 2 iterations (0.90, 0.88) are both < peak (0.95)
        assert _detect_quality_degradation(iterations, window=2) is True

    @patch('src.pipeline.orchestrator._run_validation_step')
    @patch('src.pipeline.orchestrator._run_correction_step')
    def test_loop_handles_schema_validation_failure(self, mock_correction, mock_validation):
        """Test that schema validation failure stops the loop."""
        mock_validation.return_value = {
            'schema_validation': {
                'quality_score': 0.3  # Below 0.5 threshold
            },
            'verification_summary': {
                'completeness_score': 0.85,
                'accuracy_score': 0.95,
                'schema_compliance_score': 0.95,
                'critical_issues': 0
            }
        }

        result = run_validation_with_correction(
            pdf_path=Path("test.pdf"),
            extraction_result={'initial': 'data'},
            classification_result={'publication_type': 'interventional_trial'},
            llm_provider="openai",
            file_manager=mock_file_manager,
            max_iterations=3
        )

        assert result['final_status'] == 'failed_schema_validation'
        assert 'error' in result
        assert mock_validation.call_count == 1  # Stopped after first validation
        assert mock_correction.call_count == 0  # Never ran correction

    @patch('src.pipeline.orchestrator._run_validation_step')
    @patch('src.pipeline.orchestrator._run_correction_step')
    def test_loop_handles_correction_tuple_return(self, mock_correction, mock_validation):
        """Test that correction step tuple unpacking works correctly."""
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

        # Correction returns TUPLE, not dict
        mock_correction.return_value = (
            {'corrected': 'extraction'},  # corrected_extraction
            {'final': 'validation'}  # final_validation (ignored)
        )

        result = run_validation_with_correction(
            pdf_path=Path("test.pdf"),
            extraction_result={'initial': 'data'},
            classification_result={'publication_type': 'interventional_trial'},
            llm_provider="openai",
            file_manager=mock_file_manager,
            max_iterations=3
        )

        assert result['final_status'] == 'passed'
        assert result['best_extraction'] == {'corrected': 'extraction'}
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
**A**: `-corrected1`, `-corrected2`, `-corrected3` suffixes

✅ **Q7**: Max iterations?
**A**: Default 3, configureerbaar in settings (1-5 range)

✅ **Q8**: Early stopping bij kwaliteitsdegradatie?
**A**: Ja - stop automatisch als quality degradeert voor 2 opeenvolgende iteraties (zie sectie 5: Early Stopping)

✅ **Q9**: Retry bij LLM failures?
**A**: Ja - retry 3x met exponential backoff (1s, 2s, 4s), daarna fail with best iteration (zie sectie 4: Error Handling)

✅ **Q10**: Best iteration selection algorithm?
**A**: Weighted composite score (40% completeness + 40% accuracy + 20% schema compliance) na prioriteit voor 0 critical issues (zie sectie 6)

✅ **Q11**: Configuratie persistence?
**A**: v1 = session state only (herstart = reset naar defaults), v2 = optional config file voor batch processing

### Open Vragen (Te Beantwoorden Tijdens Implementatie)

❓ **Q12**: Parallellisatie mogelijk?
- Kunnen we meerdere correctie-pogingen parallel doen? (Nee, te complex voor v1)
- Future optimization?

❓ **Q13**: Monitoring & Analytics?
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
| 2025-01-28 | 1.1 | Critical fixes na review: loop logica clarification, error handling sectie, best iteration algorithm fix (weighted scoring), file naming mapping table, early stopping logica, sectie hernummering, open vragen opgelost |
| 2025-01-28 | 1.2 | Added st.empty() real-time UI update strategy: nieuwe sectie 4 onder UI/UX Ontwerp met complete implementatie van in-place updates binnen iterative loop (zero reruns tussen iteraties), updated Fase 4 implementatie strategie |
| 2025-10-29 | 1.3 | **Implementation-Ready Revision**: Resolved critical architecture conflicts and code issues. **CRITICAL FIXES**: (1) Integrated error handling directly into loop (Sectie 3) with try/except and retry logic, (2) Fixed `_run_correction_step()` return type (tuple unpacking instead of dict access), (3) Added missing `publication_type` parameter, (4) Resolved duplicate loop execution - UI now calls orchestrator with callbacks instead of reimplementing loop logic. **ALGORITHM FIXES**: (5) Fixed early stopping to check against overall peak (not peak before window), (6) Updated docstrings and examples for clarity. **ROBUSTNESS**: (7) Added None-checks and edge case handling in `is_quality_sufficient()`, (8) Capped quality threshold sliders at 0.99 (not 1.0) to prevent infinite loops, (9) Strengthened max_iterations semantics documentation. **TESTING**: (10) Expanded test strategy with comprehensive edge case tests (None handling, tie-breaking, schema failures, tuple unpacking). Document now implementation-ready zonder blocking issues. |
| 2025-10-30 | 1.4 | **Implementation Completed - Phases 1-3**: ✅ Fase 1 (Core Loop Logic) - Implemented all 5 helper functions + main loop with 25 passing tests. ✅ Fase 2 (File Management) - Fixed file naming pattern (corrected{N}), added logging, 3 tests passing. ✅ Fase 3 (Backward Compatibility) - Added STEP_VALIDATION_CORRECTION to pipeline, updated ALL_PIPELINE_STEPS, 6 backward compat tests, all 152 unit tests passing. Feature fully integrated into pipeline with complete backward compatibility. Ready for Fase 4 (UI Integration). |
| 2025-11-01 | 1.5 | **Bug Fixes - UI Display & Navigation**: ✅ Fixed Streamlit execution screen showing wrong "BEST" iteration - Added `best_iteration` key to 6 return locations in `run_iterative_extraction_validation_correction()` (lines 1030, 1090, 1145, 1302, 1346, 1388). Backend was selecting correct best iteration, but UI defaulted to iteration 0 when key was missing. ✅ Fixed "process already done" error when clicking "Back to Start" - Added `reset_execution_state()` call to sidebar "Back to Start" button in `app.py`. Execution state (status, results, step_status, current_step_index) was persisting after navigation, causing state machine to skip pipeline execution on subsequent runs. Both bugs resolved, users can now run multiple pipelines in same session and see correct best iteration highlighted. |
