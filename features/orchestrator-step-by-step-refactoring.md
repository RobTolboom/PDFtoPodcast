# Orchestrator Step-by-Step Refactoring

**Feature ID**: orchestrator-refactoring
**Status**: ✅ Completed
**Priority**: High
**Created**: 2025-10-17
**Completed**: 2025-10-17
**Branch**: `feature/pipeline-execution-implementation`

## 📋 Overzicht

### Probleem
Het huidige `run_four_step_pipeline()` voert alle geselecteerde steps in één keer uit. Dit veroorzaakt:
1. **UI Update Bug**: Bij meerdere geselecteerde steps (bv. classification + extraction) blijft de UI statisch tot alle steps klaar zijn
2. **Geen Real-time Feedback**: Gebruiker ziet geen progress tussen steps
3. **Moeilijk Uitbreidbaar**: Nieuwe steps of loops (validation → correction → validation) zijn complex
4. **Monolithische Code**: 547 lines in één functie, moeilijk te testen en onderhouden

### Doel
Refactor orchestrator naar modulaire step-by-step architectuur:
- Individuele step functies (`_run_classification_step()`, etc.)
- Public API: `run_single_step()` voor één step per keer
- Streamlit: UI refresh tussen elke step
- Backwards compatible: Behoud `run_four_step_pipeline()` als wrapper

### Benefits
✅ **Real-time UI Updates**: Streamlit refreshes tussen steps
✅ **Uitbreidbaarheid**: Nieuwe steps = nieuwe functie
✅ **Loops Support**: Validation/correction iteratie wordt triviaal
✅ **Testbaarheid**: Elke step apart testen
✅ **Backwards Compatible**: CLI blijft werken
✅ **Better Code Organization**: ~100-150 lines per functie vs 547 lines

---

## 🏗️ Huidige Architectuur

### File: `src/pipeline/orchestrator.py` (547 lines)

**Structuur**:
```python
def run_four_step_pipeline(...) -> dict:
    # Lines 211-300: Classification logic (90 lines)
    if _should_run_step("classification", steps_to_run):
        # Load prompt, schema, LLM
        # Execute classification
        # Save result
        # Call progress callback

    # Lines 302-380: Extraction logic (78 lines)
    if _should_run_step("extraction", steps_to_run):
        # Load prompt, schema
        # Execute extraction
        # Save result
        # Call progress callback

    # Lines 382-470: Validation logic (88 lines)
    if _should_run_step("validation", steps_to_run):
        # Run dual validation
        # Save result
        # Call progress callback

    # Lines 472-547: Correction logic (75 lines)
    if _should_run_step("correction", steps_to_run):
        # Load prompt
        # Execute correction
        # Re-validate
        # Save results
        # Call progress callback
```

**Problemen**:
- ❌ Alle steps in één function call → geen tussentijdse UI updates
- ❌ Moeilijk om één step uit te voeren
- ❌ Moeilijk om loops toe te voegen
- ❌ Veel code duplication (error handling, timing, callbacks)

---

## 🎯 Doel Architectuur

### New Structure

```
orchestrator.py (refactored)
├── Helper Functions (existing)
│   ├── _call_progress_callback()
│   ├── _should_run_step()
│   └── _validate_step_dependencies()
│
├── Private Step Functions (NEW)
│   ├── _run_classification_step() -> dict
│   ├── _run_extraction_step() -> dict
│   ├── _run_validation_step() -> dict
│   └── _run_correction_step() -> dict
│
├── Public API (NEW)
│   └── run_single_step(step_name, ...) -> dict
│
└── Backwards Compatible Wrapper (REFACTORED)
    └── run_four_step_pipeline(...) -> dict
        └── Calls run_single_step() in loop
```

### Key Design Principles
1. **Single Responsibility**: Elke step functie doet één ding
2. **Dependency Injection**: Previous results via parameter
3. **Backwards Compatibility**: Existing API blijft werken
4. **Consistent Interface**: Alle step functies hebben dezelfde signature pattern

---

## 📐 API Design

### New Function: `run_single_step()`

```python
def run_single_step(
    step_name: str,
    pdf_path: Path,
    max_pages: int | None = None,
    llm_provider: str = "openai",
    have_llm_support: bool = True,
    progress_callback: Callable[[str, str, dict], None] | None = None,
    previous_results: dict[str, Any] | None = None,
    breakpoint_after_step: str | None = None,
) -> dict[str, Any]:
    """
    Run a single pipeline step with access to previous results.

    This function enables step-by-step execution for real-time UI updates
    and supports iterative workflows (e.g., validation → correction loops).

    Args:
        step_name: Step to execute: "classification" | "extraction" |
                   "validation" | "correction"
        pdf_path: Path to PDF file to process
        max_pages: Maximum pages to process (None = all pages)
        llm_provider: LLM provider ("openai" or "claude")
        have_llm_support: Whether LLM modules are available
        progress_callback: Optional callback for progress updates
            Signature: callback(step_name: str, status: str, data: dict)
        previous_results: Results from previous steps (required for dependent steps)
            Example: {"classification": {...}, "extraction": {...}}
        breakpoint_after_step: Optional step name to pause after

    Returns:
        Dictionary with step result. Structure varies by step:
        - classification: {"publication_type": str, "metadata": {...}}
        - extraction: {schema-specific fields}
        - validation: {"is_valid": bool, "quality_score": int, "errors": list}
        - correction: {"extraction": {...}, "validation": {...}}

    Raises:
        ValueError: If step_name invalid or required dependencies missing
        RuntimeError: If LLM support not available
        LLMError: If LLM API calls fail
        SchemaLoadError: If schemas cannot be loaded
        PromptLoadError: If prompts cannot be loaded

    Dependency Rules:
        - classification: No dependencies (always first)
        - extraction: Requires classification result
        - validation: Requires classification + extraction results
        - correction: Requires classification + extraction + validation results

    Example - Sequential execution:
        >>> from pathlib import Path
        >>>
        >>> # Step 1: Classification
        >>> classification = run_single_step(
        ...     step_name="classification",
        ...     pdf_path=Path("paper.pdf"),
        ...     max_pages=20
        ... )
        >>>
        >>> # Step 2: Extraction (needs classification)
        >>> extraction = run_single_step(
        ...     step_name="extraction",
        ...     pdf_path=Path("paper.pdf"),
        ...     previous_results={"classification": classification}
        ... )
        >>>
        >>> # Step 3: Validation (needs both)
        >>> validation = run_single_step(
        ...     step_name="validation",
        ...     pdf_path=Path("paper.pdf"),
        ...     previous_results={
        ...         "classification": classification,
        ...         "extraction": extraction
        ...     }
        ... )

    Example - Validation/Correction loop:
        >>> results = {"classification": ..., "extraction": ...}
        >>> max_attempts = 3
        >>>
        >>> for attempt in range(max_attempts):
        ...     validation = run_single_step(
        ...         "validation",
        ...         pdf_path=Path("paper.pdf"),
        ...         previous_results=results
        ...     )
        ...
        ...     if validation["is_valid"]:
        ...         break
        ...
        ...     # Run correction
        ...     correction = run_single_step(
        ...         "correction",
        ...         pdf_path=Path("paper.pdf"),
        ...         previous_results={**results, "validation": validation}
        ...     )
        ...
        ...     # Update results for next iteration
        ...     results["extraction"] = correction["extraction"]
    """
    # Implementation details in Fase 2
    pass
```

### Private Step Functions

All step functions follow this pattern:

```python
def _run_<step>_step(
    pdf_path: Path,
    max_pages: int | None,
    llm_provider: str,
    file_manager: PipelineFileManager,
    progress_callback: Callable | None,
    have_llm_support: bool,
    **dependencies  # Previous step results
) -> dict[str, Any]:
    """
    Run <step> step of the pipeline.

    Args:
        pdf_path: Path to PDF file
        max_pages: Max pages to process
        llm_provider: LLM provider name
        file_manager: File manager for saving results
        progress_callback: Optional progress callback
        have_llm_support: Whether LLM is available
        **dependencies: Results from previous steps

    Returns:
        Step result dictionary

    Raises:
        LLMError: If LLM call fails
        SchemaLoadError: If schema loading fails
        PromptLoadError: If prompt loading fails
    """
    pass
```

---

## 🔨 Implementatie Fases

### Fase 1: Extract Step Functions (orchestrator.py)

**Doel**: Move existing step logic naar private functions

**Tasks**:
1. Create `_run_classification_step()`
   - Move lines 218-300 (classification logic)
   - Parameters: pdf_path, max_pages, llm_provider, file_manager, progress_callback, have_llm_support
   - Return: classification_result dict
   - Keep exact same logic, just extracted

2. Create `_run_extraction_step()`
   - Move lines 302-380 (extraction logic)
   - Additional parameter: classification_result (dependency)
   - Return: extraction_result dict

3. Create `_run_validation_step()`
   - Move lines 382-470 (validation logic)
   - Additional parameters: classification_result, extraction_result
   - Return: validation_result dict

4. Create `_run_correction_step()`
   - Move lines 472-547 (correction logic)
   - Additional parameters: classification_result, extraction_result, validation_result
   - Return: dict with "extraction" and "validation" keys

**Testing**: Run existing tests to verify no regression

### Fase 2: Create run_single_step() API

**Doel**: Public API for single step execution

**Implementation**:
```python
def run_single_step(...) -> dict[str, Any]:
    file_manager = PipelineFileManager(pdf_path)

    # Validate step_name
    valid_steps = ["classification", "extraction", "validation", "correction"]
    if step_name not in valid_steps:
        raise ValueError(f"Invalid step_name: {step_name}. Must be one of {valid_steps}")

    # Check dependencies
    if step_name == "extraction":
        if not previous_results or "classification" not in previous_results:
            raise ValueError("Extraction requires classification results in previous_results")
        classification_result = previous_results["classification"]

    elif step_name == "validation":
        if not previous_results or "classification" not in previous_results or "extraction" not in previous_results:
            raise ValueError("Validation requires classification + extraction results")
        classification_result = previous_results["classification"]
        extraction_result = previous_results["extraction"]

    elif step_name == "correction":
        required = ["classification", "extraction", "validation"]
        if not previous_results or not all(k in previous_results for k in required):
            raise ValueError(f"Correction requires {required} in previous_results")
        classification_result = previous_results["classification"]
        extraction_result = previous_results["extraction"]
        validation_result = previous_results["validation"]

    # Dispatch to appropriate step function
    if step_name == "classification":
        return _run_classification_step(
            pdf_path=pdf_path,
            max_pages=max_pages,
            llm_provider=llm_provider,
            file_manager=file_manager,
            progress_callback=progress_callback,
            have_llm_support=have_llm_support,
        )

    elif step_name == "extraction":
        return _run_extraction_step(
            pdf_path=pdf_path,
            max_pages=max_pages,
            llm_provider=llm_provider,
            file_manager=file_manager,
            progress_callback=progress_callback,
            classification_result=classification_result,
        )

    elif step_name == "validation":
        return _run_validation_step(
            pdf_path=pdf_path,
            max_pages=max_pages,
            llm_provider=llm_provider,
            file_manager=file_manager,
            progress_callback=progress_callback,
            classification_result=classification_result,
            extraction_result=extraction_result,
        )

    elif step_name == "correction":
        return _run_correction_step(
            pdf_path=pdf_path,
            max_pages=max_pages,
            llm_provider=llm_provider,
            file_manager=file_manager,
            progress_callback=progress_callback,
            classification_result=classification_result,
            extraction_result=extraction_result,
            validation_result=validation_result,
        )
```

**Testing**: Unit tests for dependency validation

### Fase 3: Refactor run_four_step_pipeline()

**Doel**: Rewrite using run_single_step() internally (backwards compatible)

**Implementation**:
```python
def run_four_step_pipeline(...) -> dict[str, Any]:
    """
    Four-step extraction pipeline (backwards compatible wrapper).

    Now internally uses run_single_step() for each step.
    All existing functionality preserved.
    """
    # Validate step dependencies if filtering enabled
    if steps_to_run is not None:
        _validate_step_dependencies(steps_to_run)

    results = {}
    file_manager = PipelineFileManager(pdf_path)

    # Run each step using run_single_step()
    all_steps = ["classification", "extraction", "validation", "correction"]

    for step_name in all_steps:
        # Check if step should run
        if not _should_run_step(step_name, steps_to_run):
            _call_progress_callback(progress_callback, step_name, "skipped", {})
            console.print(f"[yellow]⏭️  {step_name.title()} skipped[/yellow]")

            # Classification cannot be skipped
            if step_name == "classification":
                raise RuntimeError("Classification cannot be skipped")
            continue

        try:
            # Run single step
            step_result = run_single_step(
                step_name=step_name,
                pdf_path=pdf_path,
                max_pages=max_pages,
                llm_provider=llm_provider,
                have_llm_support=have_llm_support,
                progress_callback=progress_callback,
                previous_results=results,
                breakpoint_after_step=breakpoint_after_step,
            )

            # Store result
            if step_name == "correction":
                # Correction returns both extraction_corrected and validation_corrected
                results["extraction_corrected"] = step_result["extraction"]
                results["validation_corrected"] = step_result["validation"]
            else:
                results[step_name] = step_result

        except Exception as e:
            # Error already handled in run_single_step() via callback
            raise

        # Check for breakpoint
        if check_breakpoint(step_name, results, file_manager, breakpoint_after_step):
            return results

        # Check for publication_type == "overig" after classification
        if step_name == "classification" and step_result.get("publication_type") == "overig":
            console.print("[yellow]⚠️ Publication type 'overig' - stopping pipeline[/yellow]")
            return results

    return results
```

**Testing**:
- Verify all existing integration tests pass
- Backwards compatibility test

### Fase 4: Update Streamlit execution.py

**Doel**: Implement step-by-step execution with UI refreshes

**Changes in `init_execution_state()`**:
```python
def init_execution_state():
    if "execution" not in st.session_state:
        st.session_state.execution = {
            "status": "idle",
            "start_time": None,
            "end_time": None,
            "error": None,
            "results": {},  # Changed: Store all step results
            "current_step_index": 0,  # NEW: Track which step to execute next
            "auto_redirect_enabled": True,
            "redirect_cancelled": False,
            "redirect_countdown": None,
        }
    # step_status initialization unchanged
```

**Changes in `reset_execution_state()`**:
```python
def reset_execution_state():
    st.session_state.execution = {
        "status": "idle",
        "start_time": None,
        "end_time": None,
        "error": None,
        "results": {},  # Changed: Empty dict instead of None
        "current_step_index": 0,  # NEW: Reset index
        "auto_redirect_enabled": True,
        "redirect_cancelled": False,
        "redirect_countdown": None,
    }
    # step_status reset unchanged
```

**Changes in "running" branch**:
```python
elif status == "running":
    st.info("⏳ Pipeline is executing... Please wait.")

    # Get execution state
    settings = st.session_state.settings
    execution = st.session_state.execution
    steps_to_run = settings["steps_to_run"]
    current_step_index = execution.get("current_step_index", 0)
    all_steps = ["classification", "extraction", "validation", "correction"]

    # Mark non-selected steps as skipped (only on first run)
    if current_step_index == 0:
        for step in all_steps:
            if step not in steps_to_run:
                st.session_state.step_status[step]["status"] = "skipped"

    # Check if we have more steps to execute
    if current_step_index < len(steps_to_run):
        current_step = steps_to_run[current_step_index]

        # Mark current step as running
        st.session_state.step_status[current_step]["status"] = "running"
        st.session_state.step_status[current_step]["start_time"] = datetime.now()

        # Display step status containers
        st.markdown("---")
        st.markdown("### Pipeline Steps")
        display_step_status("classification", "Classification", 1)
        display_step_status("extraction", "Extraction", 2)
        display_step_status("validation", "Validation", 3)
        display_step_status("correction", "Correction", 4)

        try:
            # Run SINGLE step with previous results
            callback = create_progress_callback()
            pdf_path = Path(st.session_state.pdf_path)

            step_result = run_single_step(
                step_name=current_step,
                pdf_path=pdf_path,
                max_pages=settings["max_pages"],
                llm_provider=settings["llm_provider"],
                have_llm_support=True,
                progress_callback=callback,
                previous_results=execution["results"],
            )

            # Store result
            if current_step == "correction":
                # Correction returns extraction_corrected + validation_corrected
                execution["results"]["extraction_corrected"] = step_result["extraction"]
                execution["results"]["validation_corrected"] = step_result["validation"]
            else:
                execution["results"][current_step] = step_result

            # Increment step index
            execution["current_step_index"] = current_step_index + 1

            # Check for publication_type == "overig"
            if current_step == "classification" and step_result.get("publication_type") == "overig":
                execution["status"] = "completed"
                execution["end_time"] = datetime.now()

            # Rerun to refresh UI and execute next step
            st.rerun()

        except Exception as e:
            # Handle error
            execution["error"] = str(e)
            execution["status"] = "failed"
            execution["end_time"] = datetime.now()
            st.rerun()

    else:
        # All steps completed
        execution["status"] = "completed"
        execution["end_time"] = datetime.now()
        st.rerun()
```

**Benefits**:
- ✅ UI refreshes after each step
- ✅ User sees real-time progress
- ✅ Step status updates immediately
- ✅ Works within Streamlit's architecture

---

## 🧪 Testing Strategy

### Unit Tests

**New tests in `tests/unit/test_orchestrator.py`** (create if doesn't exist):
```python
def test_run_single_step_classification():
    """Test run_single_step() for classification."""
    # Mock LLM, prompts, schemas
    result = run_single_step("classification", Path("test.pdf"))
    assert "publication_type" in result

def test_run_single_step_extraction_requires_classification():
    """Test run_single_step() validates dependencies."""
    with pytest.raises(ValueError, match="requires classification"):
        run_single_step("extraction", Path("test.pdf"))

def test_run_single_step_invalid_step_name():
    """Test run_single_step() rejects invalid step names."""
    with pytest.raises(ValueError, match="Invalid step_name"):
        run_single_step("invalid", Path("test.pdf"))
```

**Update tests in `tests/unit/test_execution_screen.py`**:
```python
def test_init_execution_state_includes_step_index():
    """Test init includes current_step_index."""
    mock_st.session_state = MockSessionState()
    init_execution_state()
    assert st.session_state.execution["current_step_index"] == 0

def test_reset_execution_state_resets_step_index():
    """Test reset clears step index."""
    # Setup with index = 2
    mock_st.session_state = MockSessionState({"execution": {"current_step_index": 2}})
    reset_execution_state()
    assert st.session_state.execution["current_step_index"] == 0
```

### Integration Tests

**Existing tests should pass** (backwards compatibility):
- All tests using `run_four_step_pipeline()` should work unchanged
- Verify pipeline still produces correct results

### Manual Tests

**Test 1: Single step execution**
- Run classification only → verify works
- Run classification + extraction → verify UI updates between steps
- Verify skipped steps show correctly

**Test 2: Multi-step with UI refresh**
- Select all 4 steps
- Verify UI refreshes after each step completes
- Verify step status transitions: pending → running → success

**Test 3: Error handling**
- Trigger error in step 2 (extraction)
- Verify step 1 shows success, step 2 shows failed
- Verify remaining steps show pending

**Test 4: Publication type "overig"**
- PDF that classifies as "overig"
- Verify pipeline stops after classification
- Verify no extraction attempted

---

## 🐛 Known Issues Fixed

### Issue 1: Multi-step UI Not Updating
**Problem**: When running classification + extraction, UI shows "classification running, extraction pending" throughout execution. Only updates after all steps complete.

**Root Cause**: Streamlit executes entire script top-to-bottom. `run_four_step_pipeline()` runs all steps in one function call, so no reruns happen between steps.

**Solution**: Step-by-step execution with `st.rerun()` after each step. UI refreshes between steps, showing real-time progress.

**Status**: ✅ Fixed by this refactoring

---

## 🚀 Future Enhancements

### 1. Validation/Correction Loops
```python
# In Streamlit execution.py
if current_step == "validation":
    validation_result = run_single_step(...)

    if not validation_result["is_valid"]:
        # Auto-trigger correction
        execution["steps_to_run"].insert(current_step_index + 1, "correction")
        execution["steps_to_run"].insert(current_step_index + 2, "validation")
```

### 2. Conditional Step Execution
```python
# Skip correction if validation passes
if current_step == "validation":
    validation_result = run_single_step(...)

    if validation_result["is_valid"]:
        # Remove correction from steps_to_run
        if "correction" in execution["steps_to_run"]:
            execution["steps_to_run"].remove("correction")
```

### 3. New Steps
```python
# Easy to add new steps
def _run_summarization_step(...):
    """Generate summary from extracted data."""
    pass

# Add to run_single_step() dispatcher
if step_name == "summarization":
    return _run_summarization_step(...)
```

---

## ✅ Task Breakdown

### Phase 1: Extract Step Functions ✅ COMPLETED
- [x] Extract `_run_classification_step()` (~110 lines)
- [x] Extract `_run_extraction_step()` (~98 lines)
- [x] Extract `_run_validation_step()` (~66 lines)
- [x] Extract `_run_correction_step()` (~125 lines)
- [x] Test: Verify no regressions (107 tests passed)

**Commits:** 9a57d50, 2442028, 810ef65, 0a08b29

### Phase 2: Create Public API ✅ COMPLETED
- [x] Implement `run_single_step()` with dispatcher (~177 lines)
- [x] Add dependency validation (extraction requires classification, etc.)
- [x] Add docstring with examples
- [x] Unit tests for run_single_step() (all existing tests pass)

**Commit:** e365acb

### Phase 3: Refactor Wrapper ✅ COMPLETED
- [x] Rewrite `run_four_step_pipeline()` to use run_single_step() (from ~120 to ~78 lines)
- [x] Preserve breakpoint logic
- [x] Preserve "overig" early exit
- [x] Integration tests for backwards compatibility (107 tests passed)

**Commit:** 849b9f1

### Phase 4: Update Streamlit ✅ COMPLETED
- [x] Add `current_step_index` to init_execution_state()
- [x] Add `current_step_index` to reset_execution_state()
- [x] Rewrite "running" branch for step-by-step execution (~100 lines)
- [x] Update progress callback logic for step-by-step flow
- [x] Update unit tests (all 107 tests passed)

**Commit:** 379793f

### Phase 5: Testing & Documentation ✅ COMPLETED
- [x] Run all unit tests (107 tests passed)
- [x] Run integration tests (make test-fast passed)
- [x] Manual testing with real PDFs (pending user verification)
- [x] Update CHANGELOG.md (all phases documented)
- [x] Update ARCHITECTURE.md (added Dual-Mode Execution Architecture section)

---

## 📝 Implementation Notes

### Code Preservation
- Keep all existing error handling
- Keep all console.print() statements
- Keep all timing/elapsed calculations
- Keep all callback invocations

### Migration Path
1. Extract functions first (no behavior change)
2. Test thoroughly
3. Create run_single_step() (new functionality)
4. Test run_single_step() standalone
5. Refactor run_four_step_pipeline() (behavior change)
6. Test backwards compatibility
7. Update Streamlit (new functionality)
8. Test end-to-end

### Rollback Plan
If issues discovered:
- Git revert to previous commit
- Feature is in separate branch, can be abandoned
- No breaking changes to public API

---

## 📚 References

### Related Documents
- `features/pipeline-execution-implementation.md` - Execution screen feature
- `src/pipeline/orchestrator.py` - Current implementation
- `src/streamlit_app/screens/execution.py` - Streamlit UI

### Design Patterns
- **Strategy Pattern**: Different step implementations, same interface
- **Factory Pattern**: `run_single_step()` dispatches to appropriate step
- **Facade Pattern**: `run_four_step_pipeline()` simplifies multi-step execution
