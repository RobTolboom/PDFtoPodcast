# Changelog

All notable changes to PDFtoPodcast will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Report Generation Feature - Phase 8: CLI Support** (#report-generation-phase8) - Complete CLI integration for report generation
  - **CLI Flags:** `--report-language {nl,en}`, `--report-renderer {latex,weasyprint}`, `--report-compile-pdf/--no-report-compile-pdf`, `--enable-figures/--disable-figures`
  - **Single Step Output:** Report generation single-step (`--step report_generation`) shows final status, iterations, quality score, and rendered artifact paths
  - **Full Pipeline Summary:** Report generation row added to CLI summary table with status, iterations, quality score, and rendered paths
  - **Documentation:** Updated help text from "four-step" to "five-step pipeline", added report example to CLI description
  - **Error Handling:** Comprehensive error handling for LaTeX/WeasyPrint renderer failures with graceful degradation

- **Report Generation Feature - Phase 7: Streamlit UI Integration** (#report-generation-phase7) - Report step integrated into Streamlit execution flow
  - **New Execution Step:** Report Generation added as Step 5 (after Appraisal)
  - **Report Settings Panel:** Language selection (nl/en), PDF compile toggle, figure generation toggle, renderer selection (latex/weasyprint)
  - **Result Display:** Quality score summary, best iteration indicator, validation status
  - **Iteration History Table:** 8-column table showing completeness, accuracy, cross-reference consistency, data consistency, schema compliance, critical issues, quality score, and status per iteration
  - **Artifact Downloads:** Download buttons for PDF, LaTeX source (.tex), and Markdown fallback (.md)
  - **Manual Re-run:** "Re-run report generation" button for regenerating reports without full pipeline restart
  - **Progress Tracking:** Basic progress callback integration (Streamlit limitations prevent true real-time streaming)

- **Report Generation Feature - Phase 5: Figure Generators** (#report-generation-phase5) - Matplotlib-based figure generation for reports
  - **Figure Generator Module:** `src/rendering/figure_generator.py` with:
    - `generate_figure()` main entry point
    - `rob_traffic_light` figure type (basic Risk of Bias visualization)
    - `forest` figure type (basic forest plot with error bars)
    - `prisma` figure type (PRISMA 2020 flow diagram for systematic reviews)
    - `consort` figure type (CONSORT flow diagram for clinical trials, supports multi-arm)
    - `FigureGenerationError` exception for error handling
    - 300 dpi PNG output with Agg backend
    - Shared utilities: `_draw_flow_box()` and `_draw_flow_arrow()` for flow diagrams
  - **LaTeX Integration:** Figure blocks now render with `\includegraphics`, `\caption`, and `\label`
  - **Unit Tests:** 16 tests for figure generation (skip when matplotlib not installed)

### Fixed

- **CLI Syntax Error in run_pipeline.py:** Fixed critical syntax errors (indentation issues and orphaned code after `if __name__ == "__main__"`) that caused `make lint` to fail with 12 invalid-syntax errors

- **Appraisal File Loading Bug:** Report generation now correctly loads `appraisal-best.json` instead of looking for non-existent `appraisal.json`

- **Report Generation Feature - Phase 4: LaTeX Renderer Improvements** (#report-generation-phase4) - Enhanced LaTeX renderer with expanded test coverage and new features
  - **Test Coverage Expansion:** Added 24 new unit tests (from 3 to 27 total) covering:
    - All text block styles (paragraph, bullets, numbered)
    - All 4 callout variants (warning, note, implication, clinical_pearl)
    - Table alignments (l, c, r, S) and render_hints
    - Figure block error handling (Phase 5 scope)
    - Subsection rendering and nesting
    - LaTeX special character escaping
  - **Metadata Injection:** Report title, authors, and publication date now injected from `report.metadata` into LaTeX output
  - **Label Generation:** Tables now generate `\label{tbl_xxx}` commands for cross-referencing (when label field present)
  - **Template Updates:**
    - Added metadata placeholders (`{{TITLE}}`, `{{AUTHORS}}`, `{{DATE}}`) to `main.tex`
    - Created `figures.tex` placeholder for Phase 5 figure macros
  - **Quality Assurance:** All 27 LaTeX renderer tests pass

### Changed

- **LLM Timeout Increased**: Extended default timeout from 10 to 30 minutes (600s → 1800s)
  - Accommodates longer report generation and complex extraction tasks
  - Configurable via `LLM_TIMEOUT` environment variable
  - With 3 automatic retries: max total time 90 minutes (was 30 minutes)

### Fixed

- **Report Generation Feature - Phase 3: Critical Integration & Test Coverage Fixes** (#report-generation-phase3-fixes) - Fixed 3 critical issues that made Phase 3 implementation non-functional
  - **Issue #1 - Dead Code (Pipeline Dispatch)**: Modified pipeline dispatch (orchestrator.py:4455) to conditionally call `run_report_with_correction()` when `enable_iterative_correction=True`, making Phase 3 loop actually execute. Previously, dispatch always called Phase 2 single-pass `run_report_generation()`, making all Phase 3 code dead code.
  - **Issue #2 - Missing Dependency Gating**: Added ~70 lines of upstream quality validation to `run_report_with_correction()` start:
    - Block if extraction quality < 0.70
    - Warn if extraction quality < 0.90
    - Block if appraisal missing Risk of Bias data
    - Warn if appraisal quality < 0.70
    - Matches feature spec requirements (lines 1625-1636)
  - **Issue #3 - Zero Test Coverage**: Created comprehensive test suite for Phase 3:
    - `tests/unit/test_report_quality.py`: 17 tests (~270 lines) for `_extract_report_metrics()`, `is_report_quality_sufficient()`, and `_select_best_report_iteration()`
    - `tests/integration/test_report_full_loop.py`: 8 integration tests (~700 lines) covering full iterative loop, early stopping, max iterations, degradation detection, dependency gating, and file persistence
    - All 25 new tests pass, bringing total test count to 152 passed
  - **Quality Assurance:** Code formatted with black, linted with ruff, all existing + new tests pass
  - **Status:** Phase 3 now fully functional with proper pipeline integration, safety checks, and automated test coverage

- **Report Generation Feature - Phase 2: Critical Bugfixes** (#report-generation-phase2-bugfix) - Fixed 4 blocking issues that prevented Phase 2 from running
  - **Issue #1 - LLM Method Call**: Changed `llm.generate_structured_output()` (non-existent) to `llm.generate_json_with_schema()` (correct method)
  - **Issue #2 - Schema Validation**: Replaced `validate_schema_compatibility()` (wrong signature) with `validate_with_schema()` from validation module
  - **Issue #3 - Missing Prompt Inputs**: Added required LANGUAGE, GENERATION_TIMESTAMP, and PIPELINE_VERSION to prompt context (prompt contract compliance)
  - **Issue #4 - Missing Test Coverage**: Added 3 integration tests with mocked LLM to verify run_report_generation() actually works
  - All tests pass (130 passed), code formatted and linted

- **Report Generation Feature - Phase 2: Prompt Context & Language Routing** (#report-generation-phase2) - Ensured report orchestration supplies complete inputs and configurable language
  - Added dynamic pipeline version detection (using package metadata or `pyproject.toml`)
  - Included serialized `report.schema.json` in LLM prompt context to match template requirements
  - Propagated `report_language` option through CLI, Streamlit settings, and orchestrator so users can select Dutch or English output
  - Updated UI/CLI defaults, file-management utilities, and unit tests to cover the new behaviour

### Added

- **Report Generation Feature - Phase 3: Validation & Correction Loop** (#report-generation-phase3) - Iterative quality improvement for report generation
  - **Quality Metrics & Thresholds:**
    - `REPORT_QUALITY_THRESHOLDS`: Quality thresholds constant (completeness ≥85%, accuracy ≥95%, cross_reference_consistency ≥90%, data_consistency ≥90%, schema_compliance ≥95%, critical_issues = 0)
    - `_extract_report_metrics()`: Extract quality scores from validation result with weighted quality_score (35% accuracy + 30% completeness + 10% cross-ref + 10% data + 15% schema)
    - `is_report_quality_sufficient()`: Check if all thresholds met for stopping iteration
    - `_select_best_report_iteration()`: Select best iteration by quality_score with accuracy as tiebreaker (data correctness paramount)
  - **Validation & Correction Steps:**
    - `_run_report_validation_step()`: LLM-based validation against Report-validation.txt prompt, checking completeness, accuracy, cross-reference consistency, data consistency, and schema compliance
    - `_run_report_correction_step()`: LLM-based correction using Report-correction.txt prompt to fix data mismatches, missing sections, broken references, and schema violations
  - **Main Iterative Loop:**
    - `run_report_with_correction()`: Complete workflow with automatic iterative correction (similar to appraisal pattern)
      - Iteration 0: Generate initial report + validate
      - Iterations 1-N: Correct + re-validate until quality sufficient or max iterations reached
      - Early stopping on quality degradation (window=2)
      - Best iteration selection on max iterations or degradation
      - Error recovery with partial results on LLM/schema errors
  - **Return Structure:**
    - `best_report`: Best report JSON selected by quality metrics
    - `best_validation`: Validation of best report
    - `best_iteration`: Iteration number of best result
    - `iterations`: Full iteration history with metrics per iteration
    - `final_status`: "passed" | "max_iterations_reached" | "early_stopped_degradation" | "failed"
    - `iteration_count`: Total iterations performed
    - `improvement_trajectory`: Quality scores per iteration for analysis
  - **File Management:** All file manager methods from Phase 2 used for saving iterations and best results
  - **Import Updates:** Added `load_report_validation_prompt` and `load_report_correction_prompt` to orchestrator imports
  - **Quality Assurance:** All existing tests pass (127 passed), code formatted and linted
  - **Status:** Phase 3 complete (validation & correction loop), ready for Phase 4 (LaTeX renderer)

- **Report Generation Feature - Phase 2: Orchestrator Integration** (#report-generation-phase2) - Pipeline integration for single-pass report generation
  - **Orchestrator:**
    - `run_report_generation()`: Single-pass report generator with LLM call, schema validation, and file saving
    - `STEP_REPORT_GENERATION` constant and integration in `ALL_PIPELINE_STEPS`
    - Full integration in `run_single_step()` with dependency validation (classification + extraction + appraisal)
    - Automatic use of best iterations from validation_correction and appraisal steps
    - Progress callbacks and rich console output for UI integration
  - **File Manager:**
    - `save_report_iteration()`: Save report and optional validation JSON for iteration
    - `load_report_iteration()`: Load report iteration with validation
    - `save_best_report()`: Save best report iteration (for Phase 3 correction loop)
    - `get_report_iterations()`: Get all report iterations with metadata
  - **Testing:**
    - `tests/unit/test_report_generation.py`: 7 tests validating file manager methods, constants, and pipeline integration
  - **Status:** Phase 2 complete (single-pass generation), ready for Phase 3 (validation & correction loop)

- **Report Generation Feature - Phase 1: Schemas & Prompts** (#report-generation-phase1) - Foundation for structured report generation from extraction and appraisal data
  - **Schemas:**
    - `schemas/report.schema.json`: Block-based report structure (textBlock, tableBlock, figureBlock, calloutBlock) with metadata, layout, sections, and source_map (~300 lines)
    - `schemas/report_validation.schema.json`: Validation report structure with quality scores (completeness, accuracy, consistency, schema compliance) and issues taxonomy (~150 lines)
    - Both schemas registered in `src/schemas_loader.py` SCHEMA_MAPPING
  - **Prompts:**
    - `prompts/Report-generation.txt`: Single template with branching for all 5 study types (interventional, observational, systematic_review, prediction, editorials), covering 12 core sections + type-specific appendices (~600 lines)
    - `prompts/Report-validation.txt`: Quality validation with 4 scored dimensions + logical alignment checks (~300 lines)
    - `prompts/Report-correction.txt`: Issue-driven correction workflow with evidence-locked fixes (~250 lines)
    - All prompts registered in `src/prompts.py` with dedicated loader functions and included in `validate_prompt_directory()`
  - **Code Integration:**
    - Added `load_report_generation_prompt()`, `load_report_validation_prompt()`, `load_report_correction_prompt()` to `src/prompts.py`
    - Updated `get_all_available_prompts()` to include report prompts
    - Updated module docstring to reflect 6-step pipeline (Classification → Extraction → Validation → Correction → Appraisal → Report)
  - **Testing:**
    - `tests/unit/test_report_schema.py`: 18 tests validating schema structure, block types, enums, label patterns (100% pass)
    - `tests/unit/test_report_prompts.py`: 18 tests validating prompt content, coverage, language support, traceability (100% pass)
  - **Quality Assurance:** All files pass `make format`, `make lint`, `make test-fast`
  - **Status:** Phase 1 complete, ready for Phase 2 (Orchestrator integration)

- **Report Generation Feature Documentation** (#report-generation-feature) - Comprehensive feature specification for structured report generation (v0.4)
  - **Complete technical design:** Block-based JSON architecture (text, table, figure, callout blocks), LaTeX rendering pipeline, iterative validation/correction
  - **17-section report structure:** Core sections (clinical bottom-line, study snapshot, quality assessment, results, limitations) plus type-specific appendices (CONSORT, PRISMA, PROBAST)
  - **Schema design:** Self-contained `report.schema.json` (no bundling required) with strict typing, render hints, and source map traceability
  - **Prompt architecture:** 3 prompts (generation, validation, correction) with study-type routing and quality thresholds
  - **Critical review improvements:** File naming patterns, appraisal dependency validation, logical_consistency_score naming, prompt token limits mitigation, best practices examples, CLI flag consistency
  - **8 implementation phases:** Schema/prompts → orchestrator → validation loop → LaTeX renderer → figures → UI/CLI → testing/docs
  - **File:** `features/report-generation.md` (2100+ lines, ready for Phase 1 implementation)

- **Critical Appraisal Pipeline Step** (#appraisal-feature) - New 4th pipeline step for structured quality assessment
  - **Study-type routing:** Automatically routes to appropriate appraisal tool based on publication type:
    - RoB 2 for randomized controlled trials (5 domains + overall risk of bias)
    - ROBINS-I for observational studies (7 domains covering confounding, selection bias, measurement)
    - PROBAST for prediction/prognosis models (4 domains × 2 perspectives)
    - AMSTAR 2 + ROBIS for meta-analyses/systematic reviews (16 items + 4 domains)
    - Argument quality assessment for editorials/opinion pieces
  - **GRADE certainty ratings:** Per-outcome certainty of evidence (High/Moderate/Low/Very Low) with downgrading factors
  - **Iterative correction loop:** Similar to extraction, with quality thresholds (logical_consistency ≥90%, completeness ≥85%, evidence_support ≥90%, schema_compliance ≥95%)
  - **Orchestrator functions:**
    - `run_appraisal_with_correction()`: Full iterative loop with quality checks
    - `is_appraisal_quality_sufficient()`: Quality threshold validation
    - `_select_best_appraisal_iteration()`: Weighted quality scoring for best result selection
    - `_get_appraisal_prompt_name()`: Publication type to tool mapping
  - **File management:** Iteration files (`{id}-appraisal{N}.json`, `{id}-appraisal-validation{N}.json`) and best file selection (`{id}-appraisal-best.json`)
  - **CLI support:** `--step appraisal` with 5 quality threshold arguments (logical/completeness/evidence/schema/max-iter)
  - **Streamlit UI:** Configuration section with quality sliders, iteration settings, and result display with RoB summary, GRADE ratings, and iteration history
  - **Comprehensive testing:** 11 integration tests (test_appraisal_full_loop.py) and 42 unit tests (test_appraisal_quality.py, test_appraisal_functions.py)
  - **Files added:** 7 prompts (Appraisal-*.txt), 2 schemas (appraisal.schema.json, appraisal_validation.schema.json), orchestrator extensions (1253 lines), file manager methods, prompt loaders
  - **Documentation:** Complete feature specification (features/appraisal.md), updated README architecture diagram, CLI help text with examples
  - **Backward compatibility:** Step is optional; existing 3-step pipelines continue to work unchanged

- **Appraisal Validation Schema** - Introduced dedicated `appraisal_validation.schema.json` to enforce the new appraisal-validation contract (scores, issue taxonomy, metadata) and wired orchestrator to load it via `load_schema("appraisal_validation")`, ensuring structured outputs remain aligned with OpenAI structured-output requirements.

- **Appraisal prompt/schema alignment**
  - Restricted `tool.judgement_scale` to a controlled enum (`rob2`, `robins`, `probast`, `amstar2`, `robis`) and made `tools.{amstar2|robis|grade}` strict booleans.
  - Added `applicability.exposure`, causal-strategy enums, and AMSTAR2 critical-item enumeraties zodat output exact schema-conform blijft.
  - Clarified diagnostic routing in `Appraisal-prediction.txt` (incl. `tool.variant="diagnostic"`) zodat diagnostic studies emit `study_type="diagnostic"`.
  - Schema blokkeert nu `risk_of_bias` voor `study_type="editorial_opinion"` en de interventional prompt verduidelijkt wanneer `analysis_issues.notes` mag worden gezet.
  - Synced bias-direction terminologie tussen `Appraisal-validation.txt` en het schema.

- **Appraisal backward compatibility**
  - Added single-pass appraisal mode via `run_appraisal_single_pass()` plus CLI flag `--appraisal-single-pass` and Streamlit toggle.
  - `run_single_step` accepts `enable_iterative_correction` and appraisal dependencies now load automatically when running the step in isolatie.
  - Backward-compatible filenames (`paper-appraisal.json`, `paper-appraisal_validation.json`) are written alongside the `*-best.json` artefacts.

- **Appraisal UI enhancements**
  - Streamlit execution screen toont nu een aparte "Appraisal"-statuskaart, uitgebreide result summary (RoB, GRADE, applicability) en quality-score charts.
  - Iteration history tabel/visualisatie + 🔁 "Re-run appraisal" knop maken iteratieve correctie inzichtelijk en beheersbaar vanuit de UI.

- **Best Extraction & Validation Selection** - Automatic quality-based selection with persistent "best" files
  - Save best extraction + validation as `{id}-extraction-best.json` and `{id}-validation-best.json` after ALL exit paths
  - Save selection metadata as `{id}-extraction-best-metadata.json` with iteration number, quality scores, and selection reason
  - **6 Exit Paths covered:**
    1. Direct success (quality sufficient at iteration 0) - saves iteration 0 as best
    2. Early stop degradation - uses `_select_best_iteration()` weighted quality scoring
    3. Max iterations reached - selects highest quality iteration
    4. LLM error (retry exhausted) - best of completed iterations
    5. JSON decode error - best of completed iterations
    6. Unexpected error - best of completed iterations
  - **Settings Screen Integration:** "View" buttons now show BEST extraction/validation (not iteration 0)
    - Extraction step: Shows best extraction if exists, falls back to extraction0
    - Validation step: Shows best validation if exists, falls back to validation0
    - Validation & Correction step: Shows best validation (highest quality, not most recent)
  - **Pipeline Loading Integration:** Future steps (appraisal) automatically load BEST extraction
    - Updated `_get_or_load_result()` to prefer best files over iteration 0
    - Console messages show which iteration is being used with quality score
    - Full backward compatibility: falls back to iteration 0 if no best file exists
  - **Metadata tracking:**
    - `best_iteration_num`: Which iteration was selected (0, 1, 2, ...)
    - `overall_quality`: Weighted quality score (0.0-1.0)
    - `completeness_score`, `accuracy_score`, `schema_compliance_score`: Individual metrics
    - `selection_reason`: "passed" | "early_stopped_degradation" | "max_iterations_reached" | "failed_llm_error" | "failed_invalid_json" | "failed_unexpected_error"
    - `total_iterations`: Total number of iterations performed
    - `timestamp`: Selection timestamp (ISO-8601)

- **Iterative Validation-Correction Loop (Fase 1)** - Core loop logic with automatic quality improvement
  - Added `run_validation_with_correction()` main loop function (~260 lines)
  - Automatic iterative correction until quality thresholds met or max iterations reached
  - Quality assessment: `is_quality_sufficient()` checks completeness (≥90%), accuracy (≥95%), schema compliance (≥95%), critical issues (0)
  - Best iteration selection: `_select_best_iteration()` using weighted quality score (40% completeness + 40% accuracy + 20% schema)
  - Early stopping: `_detect_quality_degradation()` stops loop when quality degrades for 2 consecutive iterations
  - Metrics extraction: `_extract_metrics()` computes overall quality scores for comparison
  - Error handling: Integrated retry logic with exponential backoff for LLM failures, graceful degradation for schema/JSON errors
  - Constants: `STEP_VALIDATION_CORRECTION`, `DEFAULT_QUALITY_THRESHOLDS`, `FINAL_STATUS_CODES` (7 status codes)
  - File naming: Iterations saved as `extraction0.json`, `extraction1.json`, `validation0.json`, `validation1.json`, etc.
  - Comprehensive test suite: 25 tests across 5 test classes with full edge case coverage

- **Iterative Validation-Correction Loop (Fase 2)** - File management and persistence
  - Added logging after file saves for traceability (`console.print` statements)
  - Fixed file naming pattern: `extraction-corrected{N}.json` (using `-` not `_` between step and status)
  - Verified file persistence across all iterations (iteration 0 has no suffix, iterations 1+ have `-corrected{N}`)
  - Test suite: 3 tests in `tests/unit/test_file_management_iterations.py` verifying correct file naming
  - All iteration data kept in memory during loop execution (no lazy loading)

- **Iterative Validation-Correction Loop (Fase 3)** - Backward compatibility and pipeline integration
  - Added `STEP_VALIDATION_CORRECTION` constant to pipeline step constants
  - Updated `ALL_PIPELINE_STEPS` to use new combined step (replaces separate validation+correction in default pipeline)
  - Legacy steps (`STEP_VALIDATION`, `STEP_CORRECTION`) remain available for CLI backward compatibility
  - Added elif-branch in `run_single_step()` to dispatch to `run_validation_with_correction()`
  - Updated docstring with comprehensive step documentation including legacy step notes
  - Test suite: 6 backward compatibility tests in `tests/unit/test_backward_compatibility.py`
  - All 152 unit tests pass (including 6 new backward compat tests)
  - Fixed 2 execution screen tests to expect 3 pipeline steps instead of 4

- **Iterative Validation-Correction Loop (Fase 4)** - Streamlit UI integration with real-time updates
  - Added pandas dependency (>=2.0.0) for iteration history tables
  - Updated session state defaults: `max_correction_iterations=3`, quality thresholds (completeness=0.90, accuracy=0.95, schema=0.95)
  - Settings screen: New "Validation & Correction" section with max iterations input and 3 threshold sliders (capped at 0.99 to prevent infinite loops)
  - Execution screen: New `_display_validation_correction_result()` function (~75 lines) displays final status, iteration count, best iteration selection, history table (pandas DataFrame), and metrics
  - Updated pipeline step display from 4 to 3 steps: Classification, Extraction, Validation & Correction
  - Updated breakpoint options to include `validation_correction` step
  - All step definitions updated to use new 3-step model throughout Streamlit app
  - Feature 100% complete: Backend (Phases 1-3) + UI (Phase 4) fully integrated
  - All 152 unit tests passing, backward compatible with CLI

- **Iterative Validation-Correction Loop (Fase 3.5)** - CLI support for single-step execution
  - Added `--step` CLI argument with 5 choices: classification, extraction, validation, correction, validation_correction
  - Added `--max-iterations` argument (default: 3) for configuring correction attempts
  - Added threshold arguments: `--completeness-threshold`, `--accuracy-threshold`, `--schema-threshold` (defaults: 0.90, 0.95, 0.95)
  - Implemented step selection logic: single step execution vs full pipeline
  - Added step-specific result display for CLI output (classification, validation_correction, validation)
  - Updated CLI help text with usage examples
  - Exported `run_single_step` from `src.pipeline` module (was missing from public API)
  - Backward compatible: Full pipeline runs when no `--step` specified
  - Examples: `python run_pipeline.py paper.pdf --step validation_correction --max-iterations 2 --completeness-threshold 0.85`

- **Iterative Validation-Correction Loop (Fase 5)** - Comprehensive error handling tests
  - Added `TestErrorHandling` class with 5 new unit tests (193 lines)
  - Test coverage: LLM failures, retry mechanism, schema failures, unexpected errors, JSON decode errors
  - Verified error handling: LLM API failures retried 3 times with exponential backoff (1s, 2s, 4s)
  - Verified graceful degradation: All error types preserve iterations and return meaningful status codes
  - Test results: All 30 tests in `test_iterative_validation_correction.py` pass (25 existing + 5 new)
  - Error scenarios covered: failed_llm_error, failed_schema_validation, failed_invalid_json, failed_unexpected_error

- **Orchestrator Modular Architecture** - Refactored monolithic pipeline into modular, testable functions
  - Extracted `_run_classification_step()` private function (110 lines)
  - Extracted `_run_extraction_step()` private function (98 lines)
  - Extracted `_run_validation_step()` private function (66 lines)
  - Extracted `_run_correction_step()` private function (125 lines)
  - Added `run_single_step()` public API for step-by-step execution with dependency validation
  - Refactored `run_four_step_pipeline()` to use `run_single_step()` internally (DRY principle)
  - Reduced code duplication: wrapper now calls same API used by Streamlit
  - Updated module docstring with API documentation and usage examples
  - Reduced `run_four_step_pipeline()` from 547 to ~78 lines
  - Enables step-by-step UI updates in Streamlit with reruns between steps
  - Maintains 100% backwards compatibility with existing CLI and API usage

- **Streamlit Execution Screen** - Real-time pipeline execution UI with progress tracking
  - Live progress updates per step via callbacks (Classification → Extraction → Validation → Correction)
  - Session state management with rerun prevention (prevents pipeline restart on UI interactions)
  - Verbose logging toggle (configurable via Settings screen)
  - Intelligent error handling with critical vs. non-critical error distinction
  - Step selection support (run subset of pipeline steps via Settings)
  - Auto-redirect to Settings after completion with 30-second countdown timer (cancellable)
  - Error recovery with state cleanup and retry capability
  - Top navigation "Back" button with confirmation dialog during running state
  - Comprehensive manual testing checklist (90+ tests across 7 categories)

- **Unit Tests for Execution Screen** - `tests/unit/test_execution_screen.py`
  - 9 comprehensive unit tests covering state management, callbacks, and helper functions
  - MockSessionState class for Streamlit session_state simulation
  - 100% test coverage for public functions (init, reset, create_callback, helpers)
  - All tests use mocking to avoid Streamlit dependency and real API calls

- **Dual-Mode Execution Documentation** - Added comprehensive architecture documentation
  - New section in ARCHITECTURE.md explaining Streamlit (step-by-step) vs CLI (batch) execution modes
  - Documents state management patterns and rerun behavior
  - Includes comparison table and code examples for both modes
  - Explains DRY principle: single `run_single_step()` API used by both modes
  - Architecture benefits: testability, maintainability, flexibility for future modes

- **Professional development documentation structure**
  - ARCHITECTURE.md - Complete system architecture documentation
  - CONTRIBUTING.md - Developer contribution guide
  - DEVELOPMENT.md - Local development workflow guide
  - API.md - Module and function reference
  - TESTING.md - Testing strategy and guidelines

- **Comprehensive unit test coverage for core modules** - Significantly improved test coverage (0% → 22%)
  - **tests/unit/test_schemas_loader.py** - 16 tests for schema loading, caching, error handling
  - **tests/unit/test_prompts.py** - 24 tests for prompt loading utilities
  - **tests/unit/test_validation.py** - 12 tests for validation logic and quality checks
  - **tests/unit/test_llm_base.py** - 9 tests for LLM base classes and exceptions
  - **tests/unit/test_file_manager.py** - 9 tests for PipelineFileManager
  - **tests/unit/test_pipeline_utils.py** - 12 tests for pipeline utility functions
  - All 82 new unit tests passing (99 total with existing integration tests)
  - Module coverage highlights:
    - `src/config.py`: 100% coverage
    - `src/pipeline/file_manager.py`: 100% coverage
    - `src/pipeline/__init__.py`: 100% coverage
    - `src/llm/base.py`: 85% coverage
    - `src/pipeline/utils.py`: 76% coverage
  - Comprehensive mocking and error handling tests
  - Follows CONTRIBUTING.md testing guidelines with proper markers

- **Enhanced code documentation across core and UI modules** - Comprehensive documentation improvements (Fases 1-3)
  - **Fase 1: Setup & Planning**
    - Inventariseerd 36 Python bestanden en beoordeeld documentatie kwaliteit
    - Gedefinieerd documentatie standaard gebaseerd op validation.py en json-bundler.py
    - Feature planning document aangemaakt met 6-fase roadmap
  - **Fase 2: Core Modules (4 bestanden)**
    - `src/llm/openai_provider.py` - 5 functies upgraded met complete Args/Returns/Example sections
    - `src/pipeline/validation_runner.py`, `src/llm/__init__.py`, `src/pipeline/__init__.py` already at ⭐⭐⭐ level
    - Added +176 lines of documentation
  - **Fase 3: Streamlit Modules (9 bestanden)**
    - Batch 1: 5 utility modules upgraded (json_viewer.py, result_checker.py, session_state.py, screens/__init__.py, intro.py)
    - Batch 2: 2 complex screen modules (settings.py, upload.py)
    - Added +284 lines of documentation across 7 upgraded modules
  - **Fase 4: Test Modules (11 bestanden)**
    - Batch 1: Test utility upgraded (validate_schemas.py)
    - Batch 2: Test infrastructure upgraded (conftest.py)
    - Added +190 lines of documentation
  - **Overall Impact:**
    - 15 modules upgraded to ⭐⭐⭐ documentation
    - +650 lines of documentation added total
    - All docstrings follow project standards with Args/Returns/Raises/Example sections

- **Enhanced testing infrastructure with pytest markers and coverage**
  - **pyproject.toml** - Added pytest marker registration: `@unit`, `@integration`, `@slow`, `@llm`
  - **pyproject.toml** - Configured coverage settings (80% threshold, HTML/terminal reports)
  - **tests/unit/test_json_bundler.py** - Added `@pytest.mark.unit` module marker
  - **tests/integration/test_schema_bundling.py** - Added `@pytest.mark.integration` module marker
  - **Makefile** - Updated test commands to use pytest markers
  - Enables selective test execution and better test organization

- **Documentation & tests**
  - README kreeg een "Running the appraisal step" sectie, nieuwe `docs/appraisal.md` beschrijft tools/CLI/Streamlit workflow.
  - Added unit tests verifying `run_single_step` honours the iterative vs single-pass toggle.

### Changed

- **Appraisal Feature Specification (v1.1)** - Refined feature document with technical corrections and clarifications
  - Fixed critical study type terminology alignment (interventional_trial vs interventional mismatch between classification and appraisal schemas)
  - Added explicit routing function `_get_appraisal_prompt_name()` with error handling for unsupported publication types
  - Clarified quality_score logic with critical_issues handling (schema_compliance_score → 0.0, not just quality_score cap)
  - Added comprehensive diagnostic study routing section explaining QUADAS-2/C → prediction_prognosis prompt mapping
  - Sharpened validation criteria (50 char rationale minimum, boilerplate detection, domain-specific keywords)
  - Aligned best iteration selection algorithm documentation with implementation (quality_score weighted composite)
  - Clarified max_iterations semantics (iter 0 = initial appraisal, 1-N = corrections)
  - Added error handling documentation (SchemaLoadError for schema loading failures)
  - Documented scoring architecture (thresholds = minimum requirements, weights = ranking importance)
  - Added GRADE validation future enhancement note for complex validation rules
  - Enhanced user stories with concrete, measurable acceptance criteria
  - Made test case expected output more explicit with full field specifications
  - Improved risk mitigation strategy (extraction quality warning instead of hard block)
  - Fixed workflow diagram syntax (pipe → "OR" for clarity)
  - Location: features/appraisal.md (v1.0 → v1.1, +15 improvements)

- **CLI summary now surfaces validation-correction quality metrics and appraisal outcomes** - Full-pipeline runs expose Step 3/4 status directly (`run_pipeline.py`).

- **Public pipeline docstrings** - Orchestrator, package `__init__`, Streamlit entry now describe the four-step flow as Classification → Extraction → Validation & Correction → Appraisal.

- **Marked `COMMERCIAL_LICENSE.md` as a draft** - Pending legal review to prevent accidental publication of unapproved contract language.

- **Execution Screen Auto-Redirect** - Disabled automatic redirect to Settings screen after pipeline completion
  - Changed `auto_redirect_enabled` from `True` to `False` in execution state initialization
  - Users now stay on Execution screen after completion with full control
  - No 30-second countdown timer
  - Info message displayed: "Pipeline execution completed. View results in Settings screen or run again."

- **Interventional Extraction Prompt & Schema Alignment** - Strengthened validation instructions and aligned prompt with schema requirements
  - Enhanced CLOSED WORLD ASSUMPTION: Explicit messaging that "additionalProperties":false applies at ALL nesting levels
  - Added ALL-OR-NOTHING RULE: Omit entire parent object rather than emitting partial data when confidence is low
  - Type correctness enforcement: Booleans must be JSON booleans (true/false), never strings ("true"/"false")
  - Numeric correctness: All numbers must be JSON numbers, never strings (no "1.5" or "95%")
  - Primary outcome fallback logic: When no primary outcome is explicitly stated, mark first outcome as is_primary:true
  - P-value handling guidance: Exact numbers as JSON numbers (0.042), thresholds as strings ("<0.001"), no conversion
  - Enhanced PRE-FLIGHT CHECKLIST: 13 checks (was 10) including type validation, metadata exclusion, and nested key validation
  - Explicit disallowed keys: correction_notes, _metadata, _pipeline_metadata, vendor metadata

- **File Naming Schema** - Changed iteration file naming to use consistent numbering across all iterations
  - **BREAKING CHANGE**: Old iteration files will not be recognized by new code
  - Old schema: `extraction.json`, `extraction-corrected1.json`, `validation.json`, `validation-corrected1.json`
  - New schema: `extraction0.json`, `extraction1.json`, `validation0.json`, `validation1.json`
  - All iterations now have explicit numbers (0, 1, 2, ...) for better clarity and consistency
  - Updated file_manager.py: Changed `status` parameter to `iteration_number` in get_filename(), save_json(), and load_json()
  - Updated orchestrator.py: All save_json() calls now use iteration_number parameter (8 locations)
  - Updated result_checker.py: Glob patterns changed to match numbered files (`validation[0-9]*.json`)
  - Migration note: Users should clear tmp/ directory or delete old iteration files before using new version
  - Legacy 4-step pipeline now saves as extraction1.json/validation1.json

- **Streamlit UI** - Updated deprecated `use_container_width` parameter to new `width` parameter
  - Replaced `use_container_width=True` with `width="stretch"` (13 occurrences)
  - Replaced `use_container_width=False` with `width="content"` (1 occurrence)
  - Updated 4 screen files: intro.py, settings.py, upload.py, execution.py
  - Follows Streamlit deprecation notice (parameter will be removed after 2025-12-31)

- **Documentation** - Updated architecture and design documentation
  - Updated ARCHITECTURE.md: Pipeline Orchestrator section reflects 3-step model with 10 key functions listed
  - Added new subsection "Iterative Validation-Correction Loop" with workflow, quality assessment formula, status codes, file naming, error handling
  - Design decisions updated: Why 3 steps, why iterative correction, why keep 4-step option, why quality thresholds, why early stopping, why best iteration selection
  - All documentation reflects new combined validation_correction step while maintaining backward compatibility notes

- **Pipeline Execution Metadata** - Comprehensive metadata embedded in step JSON files
  - Added `_pipeline_metadata` field to all step outputs (classification, extraction, validation, correction)
  - Metadata includes: timestamp (ISO-8601 UTC), duration_seconds, LLM provider/model, max_pages, PDF filename, execution_mode (streamlit/cli), status (success/failed)
  - Error handling: Failed steps save `{step}-failed.json` with metadata including error_message and error_type
  - Automatic metadata stripping before schema validation and LLM prompts via `_strip_metadata_for_pipeline()`
  - Enables cost analytics, debugging, and audit trail without external database
  - Added 7 unit tests for metadata stripping helper function (118 total unit tests)
  - Non-breaking: metadata is optional and doesn't affect existing code or schemas

- **Enhanced Verbose Logging Metadata** - Comprehensive API response metadata for debugging and cost optimization
  - Response IDs for debugging and support tickets (both OpenAI and Claude)
  - Model tracking: exact model version used (e.g., "gpt-5-2025-04-14", "claude-3-5-sonnet-20241022")
  - Cached tokens display with cache hit percentage for cost optimization (OpenAI only)
  - Reasoning tokens and summary for GPT-5/o-series models with effort level
  - Response status and stop_reason tracking
  - Metadata stored in `_metadata` field in result dict (non-breaking addition)
  - Streamlit verbose display enhanced with cache efficiency, reasoning tokens, response metadata sections

- **Pipeline Execution Architecture** - Switched to step-by-step execution with real-time UI updates
  - Execute one step at a time with `st.rerun()` between steps instead of running all steps at once
  - Added `current_step_index` to execution state for progress tracking (0-3)
  - Users see immediate UI updates as each step completes (Classification → Extraction → Validation → Correction)
  - Fixes bug where multi-step selection showed static status during execution
  - Maintains all error handling, callbacks, and status tracking functionality

- **Pipeline Orchestrator** - `src/pipeline/orchestrator.py` refactored for Streamlit callback support
  - Added `steps_to_run: list[str] | None` parameter for step filtering
  - Added `progress_callback: Callable | None` parameter for real-time UI updates
  - Maintained backwards compatibility with CLI interface (all existing parameters work)
  - Step filtering validates dependencies (validation needs extraction, correction needs validation)
  - Callback signature: `callback(step_name: str, status: str, data: dict)`
  - Callbacks invoked on state changes: starting, completed, failed, skipped

- **Refactored monolithic files into modular package structure**
  - `src/llm.py` (1,152 lines) → `src/llm/` package (base.py, openai_provider.py, claude_provider.py)
  - `run_pipeline.py` (679 → 195 lines) → `src/pipeline/` package (orchestrator.py, file_manager.py, validation_runner.py, utils.py)
  - `app.py` (897 → 86 lines) → `src/streamlit_app/` package (file_management.py, result_checker.py, json_viewer.py, session_state.py, screens/)
  - Improved code organization and maintainability
  - Easier to add new LLM providers in the future
  - All existing imports remain functional (backward compatible)

- **Updated and reorganized README documentation**
  - **src/README.md** - Updated for new modular package structure
  - **README.md** - Improved organization and navigation with Quick Links table
  - **tests/README.md** - Enhanced test documentation with Quick Start section
  - **prompts/README.md** - Reorganized for better navigation (reduced from 581 to 337 lines)
  - **schemas/readme.md** - Major reorganization for clarity (reduced from 1257 to 440 lines)
  - **ARCHITECTURE.md** - Added comprehensive Medical Standards & Compliance section (increased from 575 to 1018 lines)

- **Fixed remaining references to old monolithic structure**
  - **CONTRIBUTING.md** - Updated llm.py reference to llm/__init__.py
  - **DEVELOPMENT.md** - Updated project structure diagram with all modular packages

- **Improved project organization by relocating test utilities**
  - **validate_schemas.py** - Moved from project root to `tests/` directory
  - Updated references in DEVELOPMENT.md and Makefile
  - `make validate-schemas` target updated to use new location

### Fixed

- **Error Handling** - Replaced bare exception handlers in `orchestrator.py` with logged warnings when metadata saving fails
  - Extraction error handler (`orchestrator.py:870`) now logs failure to save error metadata
  - Correction error handler (`orchestrator.py:1201`) now logs failure to save error metadata
  - Prevents silent exception swallowing while maintaining "best effort" error handling approach

- **Evidence Synthesis Schema Validation** - Fixed 6 schema validation errors for meta-analysis/systematic review extractions
  - **Fix 1:** Added `is_primary` boolean field to `SynthesisOutcome` schema
  - **Fix 2:** Added `source` field to `risk_of_bias_summary`
  - **Fix 3:** Added `source` field to `Synthesis` top-level object
  - **Fix 4:** Removed redundant `outcome_id` requirement from nested `PairwiseMetaAnalysis`
  - **Fix 5:** Added `synthesis_id` string field to `Synthesis` schema
  - **Fix 6:** Clarified `authors` extraction in prompt - added explicit instruction that `last_name` is REQUIRED
  - Root cause: Schema-prompt misalignment where prompt instructions requested fields that schema `additionalProperties: false` rejected
  - Impact: Meta-analysis extractions now validate successfully, quality scores improved from 37.5-38.9% (failed) to passing
  - Files modified: `schemas/evidence_synthesis.schema.json` (source), `prompts/Extraction-prompt-evidence-synthesis.txt`, regenerated `evidence_synthesis_bundled.json`

- **Appraisal iteration persistence** - `run_appraisal_with_correction()` now uses `PipelineFileManager.save_appraisal_iteration()` to persist appraisal/validation pairs consistently.

- **Iterative Validation-Correction Loop** - Fixed validation file overwrite bug where post-correction validations were lost
  - **Bug**: After correction, validation{N}.json was saved with post-correction validation, then immediately overwritten when loop revalidated the same extraction
  - **Root cause**: Loop re-validated current_extraction at start of each iteration, even though correction step already validated it
  - **Fix**: Reuse post-correction validation for next iteration quality check instead of re-validating
  - **Result**: Each iteration now preserves both extraction and validation files (extraction0 + validation0, extraction1 + validation1, etc.)

- **Result Checker** - Fixed KeyError when accessing validation_correction step in Streamlit settings screen
  - Added `validation_correction` key to `check_existing_results()` return dictionary
  - Added `validation_correction` mapping to `get_result_file_info()` file_map
  - Checks for validation files including iterations (`{id}-validation*.json`)
  - Aligns result checker with new 3-step pipeline architecture
  - Fixes KeyError: 'validation_correction' crash in `src/streamlit_app/screens/settings.py:155`

- **Pipeline Orchestrator** - Fixed "Unsupported provider" error when running validation_correction step
  - Fixed `run_single_step()` passing OpenAIProvider object instead of string to `run_validation_with_correction()`
  - Removed unnecessary `llm = get_llm_provider(llm_provider)` call
  - Changed `llm_provider=llm` to `llm_provider=llm_provider` to pass string parameter
  - Fixes "Unsupported provider: <src.llm.openai_provider.OpenAIProvider object at 0x...>" error

- **Metadata Stripping** - Fixed validation failure due to unexpected `correction_notes` field
  - Added `correction_notes` to `_strip_metadata_for_pipeline()` stripping logic
  - The correction step adds `correction_notes` for debugging (not part of extraction schema)
  - Now stripped before validation along with `usage`, `_metadata`, `_pipeline_metadata`
  - Fixes schema validation error: "Additional properties are not allowed ('correction_notes' was unexpected)"
  - Added unit test `test_strip_metadata_removes_correction_notes`

- **File Naming Inconsistency** - Fixed validation files missing correct iteration suffix in validation-correction loop
  - Removed duplicate file saves from `_run_correction_step()`
  - Loop now saves both extraction and validation files with iteration suffix `corrected{N}`
  - Fixed issue where `validation-corrected.json` was overwritten each iteration instead of creating numbered versions
  - Post-correction validation now properly saved with iteration number for each loop iteration

- **Metadata Leakage in Final Results** - Fixed correction_notes leaking into final results returned from validation-correction loop
  - Added `_strip_metadata_for_pipeline()` calls at 3 critical points to prevent correction_notes from appearing in final results
  - Ensures `iterations[]` array only contains clean extraction data without correction_notes metadata
  - Ensures `best_extraction` selected from iterations is clean (no correction_notes field)
  - Ensures legacy 4-step pipeline returns clean corrected extraction
  - Added comprehensive integration test suite: `tests/integration/test_validation_correction_metadata_stripping.py`

- **Schema bundler self-referencing definitions** - Fixed schema bundler creating self-referencing definitions causing validation recursion errors
  - `schemas/json-bundler.py` - Replace local alias definitions with actual definitions from common schema
  - Prevents `ContrastEffect` and similar aliases from becoming `{"$ref": "#/$defs/ContrastEffect"}` self-references
  - Resolves "maximum recursion depth exceeded" error during validation step
  - Affects `observational_analytic_bundled.json` and `interventional_trial_bundled.json`

- **Execution Screen Real-time Feedback** - Fixed step status visibility and updates during pipeline execution
  - Fixed step containers not showing during execution (only "⏳ Pipeline is executing..." was visible)
  - Fixed non-selected steps showing "pending" instead of "⏭️ Skipped"
  - Fixed first step showing "pending" instead of "🔄 Running" when pipeline starts

- **Streamlit Execution Screen** - Fixed Settings screen showing wrong "BEST" iteration after pipeline completion
  - Root cause: orchestrator.py return dictionaries missing `best_iteration` key
  - UI tried to read `result.get("best_iteration", 0)` but key was undefined, always defaulting to iteration 0
  - Fix: Added `best_iteration` key to 6 return locations in `run_iterative_extraction_validation_correction()`
  - Impact: Settings screen now correctly highlights which iteration was selected as "BEST" in iteration history table

- **Streamlit Navigation** - Fixed "process already done" error when clicking "Back to Start" after pipeline completion
  - Root cause: Execution state persisted in session state after "Back to Start" navigation
  - Fix: Added `reset_execution_state()` call to "Back to Start" button handler in sidebar
  - Impact: Users can now run multiple pipelines in same session without app restart
  - Fixed all steps now show "🔄 Running" status immediately before execution begins (added `st.rerun()` after status update)
  - Removed static "0.0s" elapsed time from running status (shown only for completed/failed)

- **Partial Pipeline Runs** - Fixed "dependency not found" error when running individual steps
  - Added `PipelineFileManager.load_json()` to load cached results from `tmp/` folder
  - Enables running validation after classification+extraction (separate runs)
  - Enables re-running correction without re-doing extraction
  - Smart fallback: checks previous_results first, then loads from disk, then errors
  - Console feedback (yellow 📂) when loading from disk
  - Better error messages indicating missing dependency files
  - Added 4 new unit tests (111 total tests passing)

- **Schema bundling recursive references** - Fixed critical bug in schema bundling that caused unresolved $refs
  - Problem: Bundler only copied first-level definitions from common.schema.json, but didn't recursively resolve nested $refs
  - Example: When bundling `Metadata` definition, it didn't also copy `Author`, `Registration`, `SupplementFile`, etc.
  - Impact: All 5 bundled schemas had 5-7 unresolved $refs each, causing validation failures
  - Solution: Implemented recursive definition collection using a worklist algorithm
  - Result: All 5 schemas now pass validation with 0 unresolved $refs
  - **Tests added**: 12 unit tests + 5 integration tests in `tests/unit/test_json_bundler.py` and `tests/integration/test_schema_bundling.py`

### Removed

- **Duplicate test files** - Removed stray duplicate unit test files (`tests/unit/* 2.py`) so pytest does not execute the same suite twice.
- **test.py** - Removed temporary exploratory test file from project root
- **SETUP_COMPLETE.md** - Removed redundant setup announcement file
  - Content already covered in DEVELOPMENT.md, CONTRIBUTING.md, and README.md
  - Was a one-time setup summary, not ongoing documentation

---

## Version History Notes

### Version Numbering

We follow **Semantic Versioning** (MAJOR.MINOR.PATCH):

- **MAJOR** version: Incompatible API changes, breaking changes
- **MINOR** version: New functionality in a backward-compatible manner
- **PATCH** version: Backward-compatible bug fixes

### Categories

- **Added**: New features
- **Changed**: Changes in existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security vulnerability fixes

### Migration Guides

For breaking changes (MAJOR version bumps), see `docs/migrations/` directory for detailed migration guides.

---

## What's Next?

See `ROADMAP.md` for planned features and improvements.

Considering:
- Batch processing support
- Result caching system
- Additional LLM providers (Gemini, local models)
- Multilingual support
- API server (FastAPI wrapper)
- Database integration for result storage

---

## Links

- **Repository**: https://github.com/RobTolboom/PDFtoPodcast
- **Issue Tracker**: https://github.com/RobTolboom/PDFtoPodcast/issues
- **Documentation**: See README.md and docs/ directory
- **License**: See LICENSE and COMMERCIAL_LICENSE.md
