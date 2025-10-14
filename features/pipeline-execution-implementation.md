# Feature: Pipeline Execution Implementation

**Status:** Planning
**Aangemaakt:** 2025-10-14
**Eigenaar:** Rob Tolboom
**Branch:** feature/pipeline-execution-implementation

---

## 📋 Doel

Implementeer een volledig functionele **Execution Screen** voor de Streamlit web interface die de bestaande CLI pipeline (`run_four_step_pipeline()`) integreert met een gebruiksvriendelijke, real-time progress tracking UI. Dit maakt de volledige PDF → Extraction workflow beschikbaar via de web interface, zonder de gebruiker naar de command-line te verwijzen.

---

## 🎯 Scope

### In Scope

**Core Functionaliteit:**
- Nieuwe `src/streamlit_app/screens/execution.py` module
- Integration met bestaande `src.pipeline.orchestrator.run_four_step_pipeline()`
- Real-time progress tracking per pipeline stap
- Intelligent error handling met kritische vs. non-kritische fouten
- Verbose logging toggle (instelbaar via Settings screen)
- Navigatie terug naar Settings screen na completion (success of failure)

**UI Components:**
- Expandable status containers per pipeline stap (`st.status()`)
- Progress indicators met timestamps
- Error display met duidelijke foutmeldingen
- Step completion indicators (✅ / ❌)
- Optionele verbose logs (API calls, token usage, timing)

**Error Handling Strategy:**
- **Critical errors** (stop pipeline):
  - Classification failure → geen publication type → stop
  - Extraction failure → geen data voor validation → stop
  - LLM API errors (rate limits, authentication, network)
- **Non-critical errors** (log maar continue):
  - Validation warning (quality score laag maar niet fatal)
  - Schema compatibility warnings
- **Expected flow** (geen error):
  - Validation passed → skip correction
  - Correction niet nodig → normale flow

### Out of Scope

- **Results screen** - Bestaande JSON viewing in Settings screen is voldoende
- **Cancel/Stop functionaliteit** - Gebruiker hoeft niet te kunnen annuleren
- **Background/Async execution** - Pipeline is blocking (user wacht)
- **Progress percentage** - Alleen "Running" / "Completed" / "Failed" per stap
- **Cost estimation** - API kosten tracking niet in deze feature
- **Retry mechanisme** - Bij error: gebruiker moet handmatig opnieuw proberen via Settings

---

## 📊 Huidige Situatie

### ✅ Wat werkt al

**Streamlit Interface (3 van 5 screens geïmplementeerd):**
1. **Intro Screen** (`intro.py`) - Welkomstscherm met feature overview
2. **Upload Screen** (`upload.py`) - PDF upload met duplicate detection en file selection
3. **Settings Screen** (`settings.py`) - Pipeline configuratie:
   - Step selection (classification, extraction, validation, correction)
   - LLM provider selectie (OpenAI / Claude)
   - Max pages configuratie
   - Advanced settings (breakpoints, verbose logging, cleanup policy)
   - JSON result viewing/deletion voor bestaande outputs

**Pipeline Orchestration (volledig functioneel in CLI):**
- `run_pipeline.py` - CLI entry point met argumenten
- `src/pipeline/orchestrator.py` - `run_four_step_pipeline()` function:
  - Step 1: Classification (identify publication type)
  - Step 2: Extraction (schema-based data extraction)
  - Step 3: Validation (dual: schema + optional LLM semantic)
  - Step 4: Correction (conditional, only if validation fails)
- `src/pipeline/file_manager.py` - File management (filename-based outputs in `tmp/`)
- `src/pipeline/validation_runner.py` - Dual validation logic
- `src/llm/` - Multi-provider LLM abstraction (OpenAI, Claude)

**Session State Management:**
- `src/streamlit_app/session_state.py` - Initialized settings:
  ```python
  st.session_state.settings = {
      "llm_provider": "openai",
      "max_pages": None,
      "steps_to_run": ["classification", "extraction", "validation", "correction"],
      "cleanup_policy": "keep_forever",
      "breakpoint": None,
      "verbose_logging": False,
  }
  ```

### ❌ Wat ontbreekt

**Execution Screen (`execution.py`):**
- Placeholder in `app.py` lijn 78-79:
  ```python
  elif st.session_state.current_phase == "execution":
      st.info("🔄 Execution phase - coming in Phase 4")
  ```
- Geen import in `src/streamlit_app/screens/__init__.py`
- Geen routing naar daadwerkelijke pipeline execution

**Results Screen (`results.py`):**
- Out of scope - bestaande JSON viewing functionaliteit in Settings screen is voldoende

---

## 🏗️ Implementatie Strategie

### Architectuur Beslissing: Enhanced Implementation (Optie B)

**Gekozen aanpak:**
- **Real-time progress** met Streamlit native components
- **Blocking execution** (geen async/threading complexity)
- **Wrapper functions** rond bestaande orchestrator logica
- **Intelligent error handling** met kritische vs. non-kritische fouten

**Waarom niet Minimaal (Optie A)?**
- Te basic: geen feedback tijdens 2-5 minuten wachttijd
- Slechte UX: gebruiker weet niet wat er gebeurt

**Waarom niet Async (Optie C)?**
- Te complex: threading in Streamlit is tricky
- Niet nodig: gebruiker wil niet annuleren
- Overkill voor MVP

### Pipeline Wrapper Strategie

**Originele orchestrator** (`src/pipeline/orchestrator.py`):
```python
def run_four_step_pipeline(
    pdf_path: Path,
    max_pages: int | None,
    llm_provider: str,
    breakpoint_after_step: str | None,
    have_llm_support: bool
) -> dict[str, Any]:
    # Returns: {"classification": {...}, "extraction": {...}, ...}
```

**Streamlit wrapper** (nieuwe functie in `execution.py`):
```python
def run_pipeline_with_progress(
    pdf_path: Path,
    settings: dict,
    verbose: bool
) -> dict[str, Any]:
    """
    Wraps run_four_step_pipeline() met Streamlit progress UI.

    Voor elke stap:
    1. Open st.status() expandable container
    2. Roep pipeline step functie aan
    3. Update status (success/failure)
    4. Log verbose details (indien enabled)
    5. Handle errors (stop of continue)
    """
```

**Alternative: Refactor orchestrator**
- ❌ **Niet gekozen**: te invasive, breekt CLI interface
- ✅ **Gekozen**: wrapper approach, hergebruik bestaande code

---

## 📝 UI Design Specificatie

### Layout Structure

```
╔════════════════════════════════════════════════════════════╗
║  ## 🚀 Pipeline Execution                                  ║
║  Processing: sample_paper.pdf                              ║
║  Settings: OpenAI, All pages, Steps: 1,2,3,4               ║
║  ──────────────────────────────────────────────────────    ║
║                                                             ║
║  ✅ Step 1: Classification                [Completed]      ║
║     └─ Publication Type: interventional_trial              ║
║     └─ DOI: 10.1186/s12871-025-02345-6                     ║
║     └─ Completed in 8.3s                                   ║
║     [View Details ▼]                                        ║
║        • Uploaded PDF to OpenAI GPT-5                      ║
║        • Input tokens: 24,583 | Output: 1,247              ║
║        • Saved: tmp/sample_paper-classification.json       ║
║                                                             ║
║  🔄 Step 2: Extraction                   [Running...]      ║
║     └─ Using schema: interventional_trial (~8,500 tokens)  ║
║     └─ Elapsed: 12.4s                                      ║
║                                                             ║
║  ⏳ Step 3: Validation                   [Pending]         ║
║                                                             ║
║  ⏳ Step 4: Correction                   [Pending]         ║
║                                                             ║
║  ──────────────────────────────────────────────────────    ║
║  [⬅️ Back to Settings]                                     ║
╚════════════════════════════════════════════════════════════╝
```

### Step States

| State | Icon | Description | Expandable | Actions |
|-------|------|-------------|-----------|---------|
| **Pending** | ⏳ | Not yet started | No | None |
| **Running** | 🔄 | Currently executing | Yes, auto-expanded | Show elapsed time |
| **Success** | ✅ | Completed successfully | Yes, collapsed by default | View details, View JSON |
| **Warning** | ⚠️ | Completed with warnings | Yes, auto-expanded | View warnings, Continue |
| **Failed** | ❌ | Critical error, pipeline stopped | Yes, auto-expanded | View error, Retry |

### Verbose Logging Content

**When `settings["verbose_logging"] = True`:**

Show inside expandable step details:
- LLM provider and model used
- API call timing (start → end)
- Token usage (input + output)
- File paths (saved JSON locations)
- Schema information (name, estimated tokens)
- Validation scores (if applicable)

**When `settings["verbose_logging"] = False`:**

Show only:
- Step name and status
- High-level result (e.g., "Publication Type: interventional_trial")
- Elapsed time
- Error messages (if any)

---

## ✅ Acceptatiecriteria

### Functioneel

1. **Pipeline Execution:**
   - ✅ Execution screen wordt geladen wanneer `current_phase = "execution"`
   - ✅ Pipeline gebruikt settings uit `st.session_state.settings`
   - ✅ Alleen geselecteerde steps worden uitgevoerd (`steps_to_run`)
   - ✅ Pipeline roept `run_four_step_pipeline()` aan met correcte parameters
   - ✅ Results worden opgeslagen in `tmp/` directory met filename-based naming

2. **Progress Tracking:**
   - ✅ Elke step heeft een duidelijke status (Pending/Running/Success/Warning/Failed)
   - ✅ Running step toont elapsed time
   - ✅ Completed steps tonen completion time
   - ✅ Status updates in real-time (geen page refresh nodig)

3. **Error Handling:**
   - ✅ Classification failure → stop pipeline, toon error, enable "Back to Settings"
   - ✅ Extraction failure → stop pipeline, toon error, enable "Back to Settings"
   - ✅ LLM API errors → stop pipeline, toon actionable error message
   - ✅ Validation warnings → log maar continue naar correction (indien selected)
   - ✅ Correction failure → toon error maar mark pipeline als "completed with errors"

4. **Verbose Logging:**
   - ✅ Verbose mode shows: LLM calls, token usage, file paths, timing
   - ✅ Non-verbose mode shows: high-level status, errors, results only
   - ✅ Toggle is configurable via Settings screen (`verbose_logging`)

5. **Navigation:**
   - ✅ "Back to Settings" button altijd beschikbaar (bovenaan of onderaan)
   - ✅ Bij completion: automatic redirect naar Settings screen na 3 seconden (met cancel optie)
   - ✅ Bij critical error: blijf op Execution screen met "Back to Settings" button

### Technisch

6. **Code Kwaliteit:**
   - ✅ Volledige docstrings volgens project standaard (zie `code-documentation-improvement.md`)
   - ✅ Type hints voor alle functie signatures
   - ✅ Error handling met try/except en duidelijke error messages
   - ✅ Logging met `console.print()` voor debugging (in verbose mode)

7. **Integratie:**
   - ✅ Export `show_execution_screen` in `src/streamlit_app/screens/__init__.py`
   - ✅ Import en route in `app.py`
   - ✅ Hergebruik van bestaande `run_four_step_pipeline()` zonder modificaties
   - ✅ Hergebruik van bestaande `PipelineFileManager` voor output files

8. **Testing:**
   - ✅ Handmatige test: upload PDF → configure settings → execute pipeline → verify outputs
   - ✅ Error scenario test: invalid API key → verify error handling
   - ✅ Verbose logging test: enable/disable toggle → verify output detail level
   - ✅ Step selection test: only run classification+extraction → verify validation skipped

### UX

9. **Gebruiksvriendelijkheid:**
   - ✅ Duidelijke feedback tijdens wachttijd (geen "hanging" gevoel)
   - ✅ Expand/collapse voor verbose details (keep UI clean)
   - ✅ Error messages zijn actionable ("Check API key in .env" ipv "Error 401")
   - ✅ Success state toont key results (publication type, DOI, validation status)

10. **Performance:**
    - ✅ UI updates blijven responsive tijdens pipeline execution
    - ✅ Geen significant overhead t.o.v. CLI pipeline (< 1 seconde extra)
    - ✅ File I/O gebeurt via bestaande `PipelineFileManager` (geen duplicaat saves)

---

## 📋 Takenlijst

### Fase 1: Setup & Planning ✅
- [x] Analyseer huidige Streamlit interface structuur
- [x] Analyseer bestaande pipeline orchestrator implementatie
- [x] Definieer implementatie strategie (Enhanced vs Async)
- [x] Schrijf feature document met volledige specificatie
- [x] Maak feature branch: `feature/pipeline-execution-implementation`

### Fase 2: Core Execution Screen Implementation
- [ ] **Create `src/streamlit_app/screens/execution.py`** met:
  - [ ] Module-level docstring met Purpose, Components, Usage Example
  - [ ] `show_execution_screen()` main function
  - [ ] `run_pipeline_with_progress()` wrapper function
  - [ ] Step status tracking helper functions
  - [ ] Error handling logic (critical vs non-critical)
  - [ ] Verbose logging toggle implementation
- [ ] **Update exports in `src/streamlit_app/screens/__init__.py`:**
  - [ ] Add `from .execution import show_execution_screen`
  - [ ] Add `"show_execution_screen"` to `__all__`
- [ ] **Update routing in `app.py`:**
  - [ ] Replace placeholder `st.info()` with `show_execution_screen()` call
  - [ ] Import `show_execution_screen` from screens
- [ ] **Test basic routing:**
  - [ ] Verify execution screen loads when `current_phase = "execution"`
  - [ ] Verify settings are correctly passed from session state

### Fase 3: Pipeline Integration
- [ ] **Implement pipeline wrapper logic:**
  - [ ] Extract settings from `st.session_state.settings`
  - [ ] Map settings to `run_four_step_pipeline()` parameters
  - [ ] Call orchestrator with correct arguments
  - [ ] Capture return value (results dict)
- [ ] **Implement step-by-step execution:**
  - [ ] Wrap Classification step with `st.status()` container
  - [ ] Wrap Extraction step with `st.status()` container
  - [ ] Wrap Validation step with `st.status()` container
  - [ ] Wrap Correction step with `st.status()` container (conditional)
- [ ] **Test step filtering:**
  - [ ] Verify only selected steps run (`steps_to_run`)
  - [ ] Verify unselected steps are skipped
  - [ ] Verify breakpoint handling (if set)

### Fase 4: Progress Tracking & UI
- [ ] **Implement status indicators:**
  - [ ] Pending state (⏳) - before execution
  - [ ] Running state (🔄) - during execution
  - [ ] Success state (✅) - after successful completion
  - [ ] Warning state (⚠️) - completed with warnings
  - [ ] Failed state (❌) - critical error
- [ ] **Implement timing display:**
  - [ ] Elapsed time counter for running step
  - [ ] Completion time for finished steps
  - [ ] Total pipeline duration
- [ ] **Implement result summary:**
  - [ ] Classification: show publication type, DOI
  - [ ] Extraction: show "Completed" + file path
  - [ ] Validation: show overall status, scores
  - [ ] Correction: show "Applied" or "Skipped"

### Fase 5: Verbose Logging Implementation
- [ ] **Create verbose logging helper:**
  - [ ] Function to log API call details (provider, model, tokens)
  - [ ] Function to log file save details (path, size)
  - [ ] Function to log timing details (start, end, duration)
- [ ] **Integrate verbose logging:**
  - [ ] Check `st.session_state.settings["verbose_logging"]`
  - [ ] Show verbose details in expandable sections (when enabled)
  - [ ] Hide verbose details when disabled (clean UI)
- [ ] **Test verbose toggle:**
  - [ ] Enable in Settings → Execute → Verify detailed logs shown
  - [ ] Disable in Settings → Execute → Verify only high-level progress shown

### Fase 6: Error Handling
- [ ] **Implement critical error handling:**
  - [ ] Classification failure → stop, show error, enable "Back"
  - [ ] Extraction failure → stop, show error, enable "Back"
  - [ ] LLM API errors → stop, show actionable message
- [ ] **Implement non-critical error handling:**
  - [ ] Validation warnings → log, continue
  - [ ] Schema compatibility warnings → log, continue
- [ ] **Implement error display:**
  - [ ] Red alert box for critical errors
  - [ ] Yellow warning box for non-critical warnings
  - [ ] Error details in expandable section
  - [ ] Actionable guidance (e.g., "Check .env file")
- [ ] **Test error scenarios:**
  - [ ] Invalid API key → verify error caught and displayed
  - [ ] Network timeout → verify graceful failure
  - [ ] Publication type "overig" → verify pipeline stops correctly

### Fase 7: Navigation & Flow Control
- [ ] **Implement navigation buttons:**
  - [ ] "Back to Settings" button (altijd beschikbaar)
  - [ ] Position button logically (bovenaan of onderaan)
- [ ] **Implement post-completion flow:**
  - [ ] Success: show summary, auto-redirect naar Settings na 3s
  - [ ] Failure: show error, stay on Execution screen with "Back" button
  - [ ] Add countdown timer for auto-redirect ("Redirecting in 3... 2... 1...")
  - [ ] Add "Cancel auto-redirect" option
- [ ] **Test navigation:**
  - [ ] Back button resets to settings phase
  - [ ] Auto-redirect works correctly
  - [ ] Cancel redirect keeps user on Execution screen

### Fase 8: Testing & Validation
- [ ] **Functional testing:**
  - [ ] Test: All 4 steps selected → verify all run
  - [ ] Test: Only classification+extraction → verify validation skipped
  - [ ] Test: Classification fails → verify pipeline stops
  - [ ] Test: Validation passes → verify correction skipped
  - [ ] Test: Validation fails → verify correction runs
- [ ] **Settings integration testing:**
  - [ ] Test: LLM provider = OpenAI → verify OpenAI used
  - [ ] Test: max_pages = 10 → verify only 10 pages processed
  - [ ] Test: verbose_logging = True → verify detailed logs shown
  - [ ] Test: verbose_logging = False → verify clean UI
  - [ ] Test: breakpoint = "classification" → verify pipeline stops after classification
- [ ] **Error handling testing:**
  - [ ] Test: Invalid API key → verify error caught
  - [ ] Test: Network timeout → verify graceful failure
  - [ ] Test: PDF too large → verify error message
  - [ ] Test: Corrupt PDF → verify error handling
- [ ] **UI/UX testing:**
  - [ ] Test: Long running pipeline (> 2 min) → verify UI stays responsive
  - [ ] Test: Expand/collapse details → verify functionality
  - [ ] Test: Auto-redirect countdown → verify cancel works
  - [ ] Test: Back button during execution → verify safe (no corruption)

### Fase 9: Documentation & Finalization
- [ ] **Code documentation:**
  - [ ] Complete docstrings for all functions (Args, Returns, Raises, Example)
  - [ ] Module-level docstring met Purpose, Components, Usage
  - [ ] Inline comments for complex logic
  - [ ] Type hints for all function signatures
- [ ] **Update project documentation:**
  - [ ] Update `CHANGELOG.md` onder "Unreleased"
  - [ ] Update `README.md` indien nodig (execution screen beschrijving)
  - [ ] Update `ARCHITECTURE.md` indien nodig (execution flow diagram)
- [ ] **Code quality checks:**
  - [ ] Run `make format` - Format code with Black
  - [ ] Run `make lint` - Run Ruff linter
  - [ ] Run `make typecheck` - Run mypy type checking
  - [ ] Run `make test-fast` - Run fast unit tests
  - [ ] Fix any warnings or errors
- [ ] **Commit changes:**
  - [ ] Commit: "feat(streamlit): implement execution screen with progress tracking"
  - [ ] Run `make commit` - Pre-commit checks
  - [ ] Verify commit message follows convention

### Fase 10: Integration & Deployment
- [ ] **Integration testing:**
  - [ ] Test complete flow: Intro → Upload → Settings → Execution → Settings
  - [ ] Test with real PDF documents (small, medium, large)
  - [ ] Test with different publication types
  - [ ] Test error recovery (fix API key → retry)
- [ ] **Performance validation:**
  - [ ] Measure execution time vs CLI (should be < 1s overhead)
  - [ ] Verify memory usage (no leaks during long pipelines)
  - [ ] Verify file cleanup (tmp/ directory not growing unnecessarily)
- [ ] **Final checks:**
  - [ ] Run `make ci` - Full CI checks (format, lint, typecheck, tests)
  - [ ] Review code changes (self-review)
  - [ ] Verify no breaking changes to existing screens
  - [ ] Verify no changes to CLI pipeline behavior
- [ ] **Prepare for merge:**
  - [ ] Update feature document with "Completed" status
  - [ ] Push branch naar remote: `git push -u origin feature/pipeline-execution-implementation`
  - [ ] Create Pull Request met template
  - [ ] Request code review

---

## ⚠️ Risico's

| Risico | Impact | Waarschijnlijkheid | Mitigatie |
|--------|--------|-------------------|-----------|
| **Pipeline blocking hangt Streamlit UI** | Hoog | Medium | Use `st.status()` met updates in try/finally blocks, keep UI responsive |
| **Error tijdens pipeline corrupteert state** | Medium | Medium | Wrap in try/except, reset state on critical errors, safe file I/O |
| **Verbose logging te veel output** | Laag | Hoog | Make expandable by default (collapsed), only expand on error |
| **LLM API timeout tijdens execution** | Medium | Medium | Handle timeout explicitly, show actionable error, don't corrupt tmp/ files |
| **User navigeert weg tijdens execution** | Medium | Laag | Not preventing (no warning), but ensure clean state on return |
| **File permissions error bij write** | Medium | Laag | Check `tmp/` directory writeable on startup, show clear error |
| **Memory leak bij lange pipelines** | Laag | Laag | Reuse existing orchestrator (no new memory patterns), verify with profiling |
| **Inconsistent state tussen Settings en Execution** | Medium | Medium | Always read from `st.session_state.settings`, don't cache locally |

---

## 🔄 Dependencies

### Code Dependencies
- `src.pipeline.orchestrator.run_four_step_pipeline()` - Main pipeline function
- `src.pipeline.file_manager.PipelineFileManager` - File management
- `src.llm.get_llm_provider()` - LLM provider factory
- `st.status()` - Streamlit status containers (requires Streamlit >= 1.28.0)
- `st.session_state.settings` - Pipeline configuration dict

### Environment Dependencies
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - LLM authentication
- Writable `tmp/` directory - For pipeline outputs
- Valid PDF in `uploads/` directory - For processing

### Feature Dependencies
- ✅ Upload screen (already implemented)
- ✅ Settings screen (already implemented)
- ✅ Session state management (already implemented)
- ✅ Pipeline orchestrator (already implemented)
- ❌ Results screen (out of scope - not needed)

---

## 📈 Succes Metrics

### Kwantitatief
- ✅ 100% van geselecteerde steps worden uitgevoerd
- ✅ 0 pipeline state corruption errors
- ✅ < 1 seconde overhead t.o.v. CLI pipeline
- ✅ 100% error scenarios gracefully handled (no crashes)
- ✅ 0 linting/typing errors in new code

### Kwalitatief
- ✅ Gebruiker ziet duidelijke feedback tijdens wachttijd
- ✅ Error messages zijn actionable en begrijpelijk
- ✅ Verbose logging toggle werkt intuïtief
- ✅ UI blijft responsive tijdens lange pipelines
- ✅ Code is goed gedocumenteerd en begrijpelijk

### User Acceptance
- ✅ Pipeline executie werkt zonder crashes
- ✅ Gebruiker kan succesvol PDF → JSON extraction voltooien via web UI
- ✅ Gebruiker kan errors debuggen via verbose logging
- ✅ Gebruiker kan terug navigeren naar Settings bij problemen

---

## 🔄 Update Log

| Datum | Wijziging | Door |
|-------|-----------|------|
| 2025-10-14 | Feature document aangemaakt met volledige specificatie | Claude Code |
| 2025-10-14 | Implementatie strategie gedefinieerd: Enhanced (Optie B) | Claude Code & Rob Tolboom |
| 2025-10-14 | Error handling strategie uitgewerkt (critical vs non-critical) | Claude Code & Rob Tolboom |
| 2025-10-14 | Verbose logging specificatie toegevoegd (toggle via settings) | Claude Code & Rob Tolboom |
| 2025-10-14 | Results screen verwijderd uit scope (bestaande functionaliteit voldoende) | Claude Code & Rob Tolboom |

---

## 📚 Referenties

### Interne Referenties
- `features/code-documentation-improvement.md` - Documentatie standaard
- `src/pipeline/orchestrator.py` - Bestaande pipeline logica
- `src/streamlit_app/screens/settings.py` - Settings screen implementatie
- `CONTRIBUTING.md` - Development guidelines
- `CLAUDE.md` - Development workflows

### Streamlit Documentation
- [st.status() API](https://docs.streamlit.io/library/api-reference/status/st.status)
- [Session State](https://docs.streamlit.io/library/api-reference/session-state)
- [Progress & Status](https://docs.streamlit.io/library/api-reference/status)

### Design Patterns
- Wrapper Pattern - Wrapping `run_four_step_pipeline()` met UI logic
- Factory Pattern - `get_llm_provider()` voor provider instantiation
- State Machine - Pipeline phases (Pending → Running → Success/Failed)
