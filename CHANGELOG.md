# Changelog

All notable changes to PDFtoPodcast will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Fixed
- **Evidence Synthesis Schema Validation** - Fixed 6 schema validation errors for meta-analysis/systematic review extractions
  - **Fix 1:** Added `is_primary` boolean field to `SynthesisOutcome` schema - prompt was requesting this field but schema didn't allow it
  - **Fix 2:** Added `source` field to `risk_of_bias_summary` - LLM was adding source references but schema rejected them
  - **Fix 3:** Added `source` field to `Synthesis` top-level object - prompt explicitly requested this field but schema was missing it
  - **Fix 4:** Removed redundant `outcome_id` requirement from nested `PairwiseMetaAnalysis` - parent `Synthesis` object already has `outcome_id`, nested requirement caused validation failures
  - **Fix 5:** Added `synthesis_id` string field to `Synthesis` schema - prompt explicitly requested stable IDs (line 18, 167) but schema rejected this field
  - **Fix 6:** Clarified `authors` extraction in prompt - added explicit instruction that `last_name` is REQUIRED (schema requires it but prompt didn't mention it)
  - Root cause: Schema-prompt misalignment where prompt instructions requested fields that schema `additionalProperties: false` rejected, or schema required fields that prompt didn't instruct
  - Impact: Meta-analysis extractions now validate successfully, quality scores improved from 37.5-38.9% (failed) to passing
  - Files modified: `schemas/evidence_synthesis.schema.json` (source), `prompts/Extraction-prompt-evidence-synthesis.txt`, regenerated `evidence_synthesis_bundled.json`
  - Location: schemas/evidence_synthesis.schema.json lines 948 (is_primary), 587 (risk_of_bias_summary source), 1711 (Synthesis source), 1231-1243 (PairwiseMetaAnalysis outcome_id removal), 1707-1710 (synthesis_id); prompts/Extraction-prompt-evidence-synthesis.txt line 66 (authors instruction)

### Changed
- Marked `COMMERCIAL_LICENSE.md` as a draft pending legal review to prevent accidental publication of unapproved contract language.

### Added
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
  - Streamlit execution screen toont nu een aparte “Appraisal”-statuskaart, uitgebreide result summary (RoB, GRADE, applicability) en quality-score charts.
  - Iteration history tabel/visualisatie + 🔁 “Re-run appraisal” knop maken iteratieve correctie inzichtelijk en beheersbaar vanuit de UI.
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
  - **Implementation:**
    - orchestrator.py: 6 save locations (3 files each) + updated dependency loading
    - result_checker.py: Updated file mapping for extraction, validation, validation_correction
    - All 111 unit tests pass
  - **User Impact:**
    - Settings screen always shows the BEST extraction (quality-based, not chronological)
    - Future appraisal step will use the BEST extraction automatically
    - Complete traceability: know which iteration was selected and why
    - No manual file selection needed

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
  - Implementation in `src/pipeline/orchestrator.py` (5 helper functions + main loop)
  - Tests in `tests/unit/test_iterative_validation_correction.py` (143 total unit tests, all passing)
  - Non-breaking: Existing validation/correction steps remain unchanged for backward compatibility

- **Iterative Validation-Correction Loop (Fase 2)** - File management and persistence
  - Added logging after file saves for traceability (`console.print` statements)
  - Fixed file naming pattern: `extraction-corrected{N}.json` (using `-` not `_` between step and status)
  - Verified file persistence across all iterations (iteration 0 has no suffix, iterations 1+ have `-corrected{N}`)
  - Test suite: 3 tests in `tests/unit/test_file_management_iterations.py` verifying correct file naming
  - All iteration data kept in memory during loop execution (no lazy loading)
  - Implementation in `src/pipeline/orchestrator.py` (2 logging statements added)
  - Tests verify: iteration 0 naming, corrected suffix pattern, full multi-iteration save sequence

- **Iterative Validation-Correction Loop (Fase 3)** - Backward compatibility and pipeline integration
  - Added `STEP_VALIDATION_CORRECTION` constant to pipeline step constants
  - Updated `ALL_PIPELINE_STEPS` to use new combined step (replaces separate validation+correction in default pipeline)
  - Legacy steps (`STEP_VALIDATION`, `STEP_CORRECTION`) remain available for CLI backward compatibility
  - Added elif-branch in `run_single_step()` to dispatch to `run_validation_with_correction()`
  - Updated docstring with comprehensive step documentation including legacy step notes
  - Test suite: 6 backward compatibility tests in `tests/unit/test_backward_compatibility.py`
  - All 152 unit tests pass (including 6 new backward compat tests)
  - Fixed 2 execution screen tests to expect 3 pipeline steps instead of 4
  - Implementation in `src/pipeline/orchestrator.py` (constant, list update, elif-branch, validation logic)
  - Non-breaking: Old validation/correction steps still work, new combined step integrates seamlessly

- **Iterative Validation-Correction Loop (Fase 4)** - Streamlit UI integration with real-time updates
  - Added pandas dependency (>=2.0.0) for iteration history tables
  - Updated session state defaults: `max_correction_iterations=3`, quality thresholds (completeness=0.90, accuracy=0.95, schema=0.95)
  - Settings screen: New "Validation & Correction" section with max iterations input and 3 threshold sliders (capped at 0.99 to prevent infinite loops)
  - Execution screen: New `_display_validation_correction_result()` function (~75 lines) displays final status, iteration count, best iteration selection, history table (pandas DataFrame), and metrics
  - Updated pipeline step display from 4 to 3 steps: Classification, Extraction, Validation & Correction
  - Updated breakpoint options to include `validation_correction` step
  - All step definitions updated to use new 3-step model throughout Streamlit app
  - Implementation: `requirements.txt`, `session_state.py`, `settings.py` (step defs + UI section), `execution.py` (imports, display function, elif case, 3 display calls)
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
  - Implementation: `run_pipeline.py` (~148 lines added/modified), `src/pipeline/__init__.py` (1 export added)
  - Backward compatible: Full pipeline runs when no `--step` specified
  - Examples: `python run_pipeline.py paper.pdf --step validation_correction --max-iterations 2 --completeness-threshold 0.85`

- **Iterative Validation-Correction Loop (Fase 5)** - Comprehensive error handling tests
  - Added `TestErrorHandling` class with 5 new unit tests (193 lines)
  - Test coverage: LLM failures, retry mechanism, schema failures, unexpected errors, JSON decode errors
  - Verified error handling: LLM API failures retried 3 times with exponential backoff (1s, 2s, 4s)
  - Verified graceful degradation: All error types preserve iterations and return meaningful status codes
  - Test results: All 30 tests in `test_iterative_validation_correction.py` pass (25 existing + 5 new)
  - Error scenarios covered: failed_llm_error, failed_schema_validation, failed_invalid_json, failed_unexpected_error
  - Implementation: `tests/unit/test_iterative_validation_correction.py` (added TestErrorHandling class)
  - Validation: Error handling already implemented in Phase 1, tests confirm correct behavior

### Changed
- **Execution Screen Auto-Redirect** - Disabled automatic redirect to Settings screen after pipeline completion
  - Changed `auto_redirect_enabled` from `True` to `False` in execution state initialization
  - Users now stay on Execution screen after completion with full control
  - No 30-second countdown timer
  - Info message displayed: "Pipeline execution completed. View results in Settings screen or run again."
  - Timer logic preserved for potential future re-enable
  - Implementation: `src/streamlit_app/screens/execution.py` (2 locations)

- **Interventional Extraction Prompt & Schema Alignment** - Strengthened validation instructions and aligned prompt with schema requirements
  - Enhanced CLOSED WORLD ASSUMPTION: Explicit messaging that "additionalProperties":false applies at ALL nesting levels
  - Added ALL-OR-NOTHING RULE: Omit entire parent object rather than emitting partial data when confidence is low
  - Type correctness enforcement: Booleans must be JSON booleans (true/false), never strings ("true"/"false")
  - Numeric correctness: All numbers must be JSON numbers, never strings (no "1.5" or "95%")
  - Primary outcome fallback logic: When no primary outcome is explicitly stated, mark first outcome as is_primary:true to satisfy schema's `contains` constraint
  - P-value handling guidance: Exact numbers as JSON numbers (0.042), thresholds as strings ("<0.001"), no conversion
  - Enhanced PRE-FLIGHT CHECKLIST: 13 checks (was 10) including type validation, metadata exclusion, and nested key validation
  - Explicit disallowed keys: correction_notes, _metadata, _pipeline_metadata, vendor metadata
  - Resolves conflict: Schema already required at least one primary outcome via `contains` constraint, prompt now handles fallback case
  - Implementation: prompts/Extraction-prompt-interventional.txt (~220 lines)
  - Impact: Better LLM adherence to schema, fewer validation failures, clearer error messages

- **File Naming Schema** - Changed iteration file naming to use consistent numbering across all iterations
  - **BREAKING CHANGE**: Old iteration files will not be recognized by new code
  - Old schema: `extraction.json`, `extraction-corrected1.json`, `validation.json`, `validation-corrected1.json`
  - New schema: `extraction0.json`, `extraction1.json`, `validation0.json`, `validation1.json`
  - All iterations now have explicit numbers (0, 1, 2, ...) for better clarity and consistency
  - Updated file_manager.py: Changed `status` parameter to `iteration_number` in get_filename(), save_json(), and load_json()
  - Updated orchestrator.py: All save_json() calls now use iteration_number parameter (8 locations)
  - Updated result_checker.py: Glob patterns changed to match numbered files (`validation[0-9]*.json`)
  - Updated tests: All filename assertions updated to new schema (3 test files)
  - Updated documentation: settings.py docstring reflects new naming convention
  - Migration note: Users should clear tmp/ directory or delete old iteration files before using new version
  - Legacy 4-step pipeline now saves as extraction1.json/validation1.json (was extraction-corrected.json)
  - Implementation: 6 core files + 3 test files modified
  - All 111 unit tests pass with new naming scheme

- **Streamlit UI** - Updated deprecated `use_container_width` parameter to new `width` parameter
  - Replaced `use_container_width=True` with `width="stretch"` (13 occurrences)
  - Replaced `use_container_width=False` with `width="content"` (1 occurrence)
  - Updated 4 screen files: intro.py, settings.py, upload.py, execution.py
  - Affects st.button() and st.dataframe() components
  - Follows Streamlit deprecation notice (parameter will be removed after 2025-12-31)
  - No functional changes - maintains existing UI behavior

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
  - Implementation in `src/pipeline/orchestrator.py` covering all 4 pipeline steps

- **Enhanced Verbose Logging Metadata** - Comprehensive API response metadata for debugging and cost optimization
  - Response IDs for debugging and support tickets (both OpenAI and Claude)
  - Model tracking: exact model version used (e.g., "gpt-5-2025-04-14", "claude-3-5-sonnet-20241022")
  - Cached tokens display with cache hit percentage for cost optimization (OpenAI only)
  - Reasoning tokens and summary for GPT-5/o-series models with effort level
  - Response status and stop_reason tracking
  - Metadata stored in `_metadata` field in result dict (non-breaking addition)
  - Streamlit verbose display enhanced with:
    - Cache efficiency section showing cached token percentage
    - Reasoning tokens prominently displayed when significant
    - Response metadata section with model, response_id, status
    - Expandable reasoning summary for GPT-5/o-series (🧠 icon)
  - Updated OpenAI provider: 2 locations in `_parse_response_output()` (success + repair paths)
  - Updated Claude provider: 2 locations (`generate_json_with_schema()`, `generate_json_with_pdf()`)
  - Updated Streamlit: `_display_verbose_info()` in `src/streamlit_app/screens/execution.py`

### Fixed
- **Iterative Validation-Correction Loop** - Fixed validation file overwrite bug where post-correction validations were lost
  - **Bug**: After correction, validation{N}.json was saved with post-correction validation, then immediately overwritten when loop revalidated the same extraction with same iteration number
  - **Example**: validation1.json (post-correction) was overwritten by re-validation of extraction1 in next loop iteration
  - **Impact**: Initial validation data for each iteration was lost, making iteration history incomplete
  - **Root cause**: Loop re-validated current_extraction at start of each iteration, even though correction step already validated it
  - **Fix**: Reuse post-correction validation for next iteration quality check instead of re-validating
  - **Implementation**: Added `current_validation` variable to track validation state, skip validation when already available from correction
  - **Result**: Each iteration now preserves both extraction and validation files (extraction0 + validation0, extraction1 + validation1, etc.)
  - **Location**: `src/pipeline/orchestrator.py` - run_validation_with_correction() function
  - All 111 unit tests pass with fix

- **Result Checker** - Fixed KeyError when accessing validation_correction step in Streamlit settings screen
  - Added `validation_correction` key to `check_existing_results()` return dictionary
  - Added `validation_correction` mapping to `get_result_file_info()` file_map
  - Checks for validation files including iterations (`{id}-validation*.json`)
  - Aligns result checker with new 3-step pipeline architecture (classification, extraction, validation_correction)
  - Fixes KeyError: 'validation_correction' crash in `src/streamlit_app/screens/settings.py:155`
  - Implementation in `src/streamlit_app/result_checker.py`
  - Maintains backward compatibility with legacy validation/correction keys

- **Pipeline Orchestrator** - Fixed "Unsupported provider" error when running validation_correction step
  - Fixed `run_single_step()` passing OpenAIProvider object instead of string to `run_validation_with_correction()`
  - Removed unnecessary `llm = get_llm_provider(llm_provider)` call (line 1597)
  - Changed `llm_provider=llm` to `llm_provider=llm_provider` (line 1603) to pass string parameter
  - `run_validation_with_correction()` expects `llm_provider: str` and creates provider object internally
  - Fixes "Unsupported provider: <src.llm.openai_provider.OpenAIProvider object at 0x...>" error
  - Implementation in `src/pipeline/orchestrator.py` lines 1593-1608
  - Aligns with validation/correction step patterns that also accept string parameters

- **Metadata Stripping** - Fixed validation failure due to unexpected `correction_notes` field
  - Added `correction_notes` to `_strip_metadata_for_pipeline()` stripping logic
  - The correction step adds `correction_notes` for debugging (not part of extraction schema)
  - Now stripped before validation along with `usage`, `_metadata`, `_pipeline_metadata`
  - Fixes schema validation error: "Additional properties are not allowed ('correction_notes' was unexpected)"
  - Implementation in `src/pipeline/orchestrator.py` (line 186 in `_strip_metadata_for_pipeline()`)
  - Added unit test `test_strip_metadata_removes_correction_notes` in `tests/unit/test_orchestrator.py`
  - Updated 3 existing tests to verify correction_notes stripping behavior

- **File Naming Inconsistency** - Fixed validation files missing correct iteration suffix in validation-correction loop
  - Removed duplicate file saves from `_run_correction_step()` (lines 751, 785)
  - Loop now saves both extraction and validation files with iteration suffix `corrected{N}`
  - Fixed issue where `validation-corrected.json` was overwritten each iteration instead of creating numbered versions
  - Fixed missing `validation-corrected1.json` file (was only creating `validation-corrected.json`)
  - Post-correction validation now properly saved with iteration number for each loop iteration
  - Implementation in `src/pipeline/orchestrator.py`:
    - Removed file saves from `_run_correction_step()` (function only returns data now)
    - Added file saves in `run_validation_with_correction()` loop (lines 1076-1086, 1133-1142)
    - Added file saves in old 4-step STEP_CORRECTION flow (lines 1604-1609)
  - All 111 tests pass, backward compatible with 4-step pipeline

- **Metadata Leakage in Final Results** - Fixed correction_notes leaking into final results returned from validation-correction loop
  - Added `_strip_metadata_for_pipeline()` calls at 3 critical points to prevent correction_notes from appearing in final results:
    1. After correction in main loop before storing in `current_extraction` (line 1090)
    2. After correction in retry error handling path (line 1151)
    3. In legacy 4-step pipeline return before returning corrected extraction (lines 1779-1781)
  - Ensures `iterations[]` array only contains clean extraction data without correction_notes metadata
  - Ensures `best_extraction` selected from iterations is clean (no correction_notes field)
  - Ensures legacy 4-step pipeline returns clean corrected extraction
  - Prevents correction_notes from appearing in validation prompts, LLM inputs, or final results
  - Added comprehensive integration test suite: `tests/integration/test_validation_correction_metadata_stripping.py`
    - Tests correction_notes stripped from final result (best_extraction)
    - Tests correction_notes stripped from all stored iterations
    - Tests all metadata fields stripped (usage, _metadata, _pipeline_metadata, correction_notes)
  - Implementation in `src/pipeline/orchestrator.py` (3 stripping locations)
  - All 111 unit tests + 3 new integration tests pass

- Fixed schema bundler creating self-referencing definitions causing validation recursion errors
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
  - Backend correctly selected best iteration and saved correct files, but UI displayed wrong iteration as "BEST"
  - Fix: Added `best_iteration` key to 6 return locations in `run_iterative_extraction_validation_correction()`:
    1. Passed validation (early success) - returns current iteration number
    2. Early stopped degradation - returns `best["iteration_num"]` from quality-based selection
    3. Max iterations reached - returns `best["iteration_num"]` from quality-based selection
    4. LLM error recovery - returns `best["iteration_num"]` if best exists, else 0
    5. JSON decode error recovery - returns `best["iteration_num"]` if best exists, else 0
    6. Unexpected error recovery - returns `best["iteration_num"]` if best exists, else 0
  - Impact: Settings screen now correctly highlights which iteration was selected as "BEST" in iteration history table
  - Location: `src/pipeline/orchestrator.py` (lines 1030, 1090, 1145, 1302, 1346, 1388)

- **Streamlit Navigation** - Fixed "process already done" error when clicking "Back to Start" after pipeline completion
  - Root cause: Execution state (status, results, step_status, current_step_index) persisted in session state after "Back to Start" navigation
  - When user clicked "Back to Start" and re-ran pipeline with new PDF, old state indicated process was already complete
  - State machine saw `current_step_index >= len(steps_to_run)` and immediately declared completion without running pipeline
  - "Back" button in execution screen correctly called `reset_execution_state()`, but sidebar "Back to Start" button did not
  - Fix: Added `reset_execution_state()` call to "Back to Start" button handler in sidebar
  - State reset clears: execution.status → "idle", execution.results → None, all step_status → "pending", current_step_index → 0, errors, timestamps
  - Impact: Users can now run multiple pipelines in same session without app restart, navigation is symmetric (both back buttons reset state)
  - Location: `app.py` (lines 28, 75-76)
  - Fixed all steps now show "🔄 Running" status immediately before execution begins (added `st.rerun()` after status update)
  - Removed static "0.0s" elapsed time from running status (shown only for completed/failed)
  - Implemented proactive status updates to work within Streamlit's execution model constraints
  - Added `_mark_next_step_running()` helper to auto-update next step after completion
  - Improved user experience with immediate, accurate step status feedback

- **Partial Pipeline Runs** - Fixed "dependency not found" error when running individual steps
  - Added `PipelineFileManager.load_json()` to load cached results from `tmp/` folder
  - Enables running validation after classification+extraction (separate runs)
  - Enables re-running correction without re-doing extraction
  - Smart fallback: checks previous_results first, then loads from disk, then errors
  - Console feedback (yellow 📂) when loading from disk
  - Better error messages indicating missing dependency files
  - Added 4 new unit tests (111 total tests passing)

### Changed
- **Pipeline Execution Architecture** - Switched to step-by-step execution with real-time UI updates
  - Execute one step at a time with `st.rerun()` between steps instead of running all steps at once
  - Added `current_step_index` to execution state for progress tracking (0-3)
  - Users see immediate UI updates as each step completes (Classification → Extraction → Validation → Correction)
  - Fixes bug where multi-step selection showed static status during execution
  - Maintains all error handling, callbacks, and status tracking functionality
  - Special handling for correction step which returns dict with two keys

### Added
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

- Professional development documentation structure
  - ARCHITECTURE.md - Complete system architecture documentation
  - CONTRIBUTING.md - Developer contribution guide
  - DEVELOPMENT.md - Local development workflow guide
  - API.md - Module and function reference
  - TESTING.md - Testing strategy and guidelines

### Changed
- **Pipeline Orchestrator** - `src/pipeline/orchestrator.py` refactored for Streamlit callback support
  - Added `steps_to_run: list[str] | None` parameter for step filtering
  - Added `progress_callback: Callable | None` parameter for real-time UI updates
  - Maintained backwards compatibility with CLI interface (all existing parameters work)
  - Step filtering validates dependencies (validation needs extraction, correction needs validation)
  - Callback signature: `callback(step_name: str, status: str, data: dict)`
  - Callbacks invoked on state changes: starting, completed, failed, skipped

- Refactored `src/llm.py` (1,152 lines) into modular package structure
  - `src/llm/base.py` - Abstract base class and exceptions
  - `src/llm/openai_provider.py` - OpenAI provider implementation
  - `src/llm/claude_provider.py` - Claude provider implementation
  - `src/llm/__init__.py` - Backward-compatible public API
  - Improved code organization and maintainability
  - Easier to add new LLM providers in the future
  - All existing imports remain functional (backward compatible)

- Refactored `run_pipeline.py` (679 → 195 lines) by extracting to `src/pipeline/` package
  - `src/pipeline/orchestrator.py` - Main pipeline coordination logic
  - `src/pipeline/file_manager.py` - File naming and storage (PipelineFileManager)
  - `src/pipeline/validation_runner.py` - Dual validation strategy
  - `src/pipeline/utils.py` - Helper functions (DOI, breakpoints, etc.)
  - `src/pipeline/__init__.py` - Backward-compatible public API
  - Improved separation of concerns and testability
  - Reduced file complexity (each file <300 lines)
  - All existing imports remain functional (backward compatible)
- Refactored `app.py` (897 → 86 lines) by extracting to `src/streamlit_app/` package
  - `src/streamlit_app/file_management.py` - Upload handling, manifest, duplicate detection
  - `src/streamlit_app/result_checker.py` - Check existing pipeline results
  - `src/streamlit_app/json_viewer.py` - Display JSON results in modal dialogs
  - `src/streamlit_app/session_state.py` - Session state initialization
  - `src/streamlit_app/screens/intro.py` - Introduction/welcome screen
  - `src/streamlit_app/screens/upload.py` - PDF upload and file selection screen
  - `src/streamlit_app/screens/settings.py` - Pipeline configuration screen
  - `src/streamlit_app/__init__.py` - Backward-compatible public API
  - Improved separation of concerns and testability
  - Reduced main file complexity (897 → 86 lines, 90% reduction)
  - Each screen module <300 lines for better maintainability
  - All existing functionality preserved (backward compatible)

- Updated and reorganized README documentation
  - **src/README.md** - Updated for new modular package structure
    - Updated module overview to reflect llm/, pipeline/, and streamlit_app/ packages
    - Replaced references to monolithic llm.py with current package structure
    - Added pipeline/ package documentation (orchestrator, validation_runner, file_manager)
    - Added streamlit_app/ package overview
    - Improved API examples with current imports
    - Better organization with clear section headers
  - **README.md** - Improved organization and navigation
    - Added Quick Links table at top for easy navigation
    - Converted cost considerations to tables for better readability
    - Added app.py to project structure documentation
    - Consolidated development section with clear doc references
    - Improved programmatic usage examples with current API
    - Better documentation navigation table
  - **tests/README.md** - Enhanced test documentation
    - Added Quick Start section with common make commands
    - Better structure separating "running tests" from "writing tests"
    - Added Test Markers section with @pytest.mark examples
    - Improved Mocking section with complete code examples
    - Added Development Workflow section
    - Removed TODO section (moved to GitHub Issues)
  - **prompts/README.md** - Reorganized for better navigation
    - Added Quick Start section with prompt-schema mapping table
    - Reorganized into clear sections (Overview, Types, Integration, Principles)
    - Consolidated complete pipeline example with all four steps
    - Better troubleshooting section with common issues and solutions
    - Compacted version history for better readability
    - Reduced from 581 to 337 lines (42% reduction)
  - **schemas/readme.md** - Major reorganization for clarity
    - Added Quick Start with schema selection table
    - Clear separation of Modular vs Bundled deployment options
    - Concise schema type descriptions without excessive JSON examples
    - Focused usage examples (validation, LLM integration, batch processing)
    - Compact json-bundler.py tool documentation
    - Streamlined troubleshooting and international standards sections
    - Moved detailed compliance information to ARCHITECTURE.md
    - Reduced from 1257 to 440 lines (65% reduction!)
  - **ARCHITECTURE.md** - Added comprehensive Medical Standards & Compliance section
    - International Reporting Standards (CONSORT, PRISMA, TRIPOD, STROBE)
    - Quality Assessment Tools (RoB 2.0, ROBINS-I, PROBAST, AMSTAR-2)
    - Advanced Methodological Support (target trial emulation, causal inference)
    - Data Source Prioritization Strategy documentation
    - Document Processing & PDF Strategy details
    - Evidence-Locked Extraction principles
    - International Trial Registry Support (9 registries)
    - Anesthesiology Domain Specialization
    - Fulfills promises made in prompts/README.md and schemas/readme.md relocations
    - Increased from 575 to 1018 lines (comprehensive technical reference)
    - Fixed LLM Provider Layer header to reference src/llm/ package

- Fixed remaining references to old monolithic structure
  - **CONTRIBUTING.md** - Updated llm.py reference to llm/__init__.py
  - **DEVELOPMENT.md** - Updated project structure diagram with all modular packages

- Improved project organization by relocating test utilities
  - **validate_schemas.py** - Moved from project root to `tests/` directory
  - Updated references in DEVELOPMENT.md and Makefile
  - `make validate-schemas` target updated to use new location
  - Removed temporary `test.py` file (exploratory scratch file)

### Added
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
      - `_repair_json_quotes()`: JSON repair heuristics documented
      - `_parse_response_output()`: Multiple extraction strategies detailed
      - `generate_text()`: Full docstring with retry behavior
      - `generate_json_with_schema()`: Dual-validation strategy notes
      - `generate_json_with_pdf()`: Multimodal capabilities documentation
    - `src/pipeline/validation_runner.py`, `src/llm/__init__.py`, `src/pipeline/__init__.py` already at ⭐⭐⭐ level
    - Added +176 lines of documentation
  - **Fase 3: Streamlit Modules (9 bestanden)**
    - Batch 1: 5 utility modules upgraded
      - `src/streamlit_app/json_viewer.py`: Streamlit dialog behavior documented
      - `src/streamlit_app/result_checker.py`: File naming conventions and storage location
      - `src/streamlit_app/session_state.py`: Best practices notes and phase flow
      - `src/streamlit_app/screens/__init__.py`: Complete usage examples
      - `src/streamlit_app/screens/intro.py`: Layout structure details
    - Batch 2: 2 complex screen modules (299 + 291 lines) upgraded
      - `src/streamlit_app/screens/settings.py`: Tab structure, state management, workflow documentation
      - `src/streamlit_app/screens/upload.py`: Duplicate detection, manifest management, validation flow
    - `src/streamlit_app/__init__.py` and `src/streamlit_app/file_management.py` already at ⭐⭐⭐ level
    - Added +284 lines of documentation across 7 upgraded modules
  - **Fase 4: Test Modules (11 bestanden)**
    - Batch 1: Test utility upgraded
      - `tests/validate_schemas.py`: 4 functies met complete Args/Returns/Example
        - `get_nested_value()`: JSON Pointer path traversal documented
        - `check_refs_recursive()`: Reference resolution validation documented
        - `get_schema_stats()`: Schema complexity metrics documented
        - `validate_schema()`: Comprehensive validation checks documented
    - Batch 2: Test infrastructure upgraded
      - `tests/conftest.py`: Module docstring met fixture categories
      - Complete fixture overview (8 fixtures: Test Data, Mock Responses, Providers, Schemas)
      - Usage examples showing fixture usage in tests
      - Notes about function scope and Mock configuration
    - Unit test files analysis (9 bestanden):
      - All unit test files already at ⭐⭐⭐ level (test method names are self-documenting)
      - No action needed for test_file_manager.py, test_json_bundler.py, test_llm_base.py, etc.
    - Added +190 lines of documentation (152 + 38)
    - 2 logically structured commits with targeted improvements
  - **Overall Impact:**
    - 15 modules upgraded to ⭐⭐⭐ documentation (13 in phases 2-3, 2 in phase 4)
    - +650 lines of documentation added total
    - All docstrings follow project standards with Args/Returns/Raises/Example sections
    - Improved IDE tooltips and developer onboarding experience
    - 11 logically structured commits with clear descriptions
    - Comprehensive coverage: core modules, UI modules, test utilities

- Enhanced testing infrastructure with pytest markers and coverage
  - **pyproject.toml** - Added pytest marker registration: `@unit`, `@integration`, `@slow`, `@llm`
  - **pyproject.toml** - Configured coverage settings (80% threshold, HTML/terminal reports)
  - **tests/unit/test_json_bundler.py** - Added `@pytest.mark.unit` module marker
  - **tests/integration/test_schema_bundling.py** - Added `@pytest.mark.integration` module marker
  - **Makefile** - Updated test commands to use pytest markers:
    - `make test-unit` - Run unit tests via `-m "unit"` marker
    - `make test-integration` - Run integration tests via `-m "integration"` marker
    - `make test-fast` - Run fast unit tests excluding slow tests
  - Enables selective test execution and better test organization
  - Improves development workflow with faster feedback loops

### Deprecated
- Nothing yet

### Removed
- **test.py** - Removed temporary exploratory test file from project root
- **SETUP_COMPLETE.md** - Removed redundant setup announcement file
  - Content already covered in DEVELOPMENT.md, CONTRIBUTING.md, and README.md
  - Was a one-time setup summary, not ongoing documentation
  - No references from other documentation files

### Fixed
- **schemas/json-bundler.py** - Fixed critical bug in schema bundling that caused unresolved $refs
  - Problem: Bundler only copied first-level definitions from common.schema.json, but didn't recursively resolve nested $refs within those definitions
  - Example: When bundling `Metadata` definition, it didn't also copy `Author`, `Registration`, `SupplementFile`, etc. that Metadata references
  - Impact: All 5 bundled schemas had 5-7 unresolved $refs each, causing validation failures
  - Solution: Implemented recursive definition collection using a worklist algorithm
    - Added `include_local` parameter to `find_common_refs()` to detect local #/$defs/Name references
    - Modified `bundle_schema()` to recursively process nested dependencies until all are resolved
    - Each embedded definition is now scanned for additional references, which are added to the processing queue
  - Result: All 5 schemas now pass validation with 0 unresolved $refs
  - Files affected: All *_bundled.json schemas now correctly include all transitive dependencies
  - **Tests added**: Comprehensive test coverage following @CONTRIBUTING.md requirements
    - 12 unit tests in `tests/unit/test_json_bundler.py`
    - 5 integration tests in `tests/integration/test_schema_bundling.py`
    - Test fixtures: `tests/fixtures/schemas/` with nested reference examples
    - Regression test ensures nested refs (Metadata→Author, Registration→Registry) are all resolved
    - All 17 tests pass ✅

### Security
- Nothing yet

---

## [1.0.0] - 2025-01-09

### Added
- **Four-step extraction pipeline**
  - Step 1: Classification (publication type identification)
  - Step 2: Schema-based extraction
  - Step 3: Dual validation (schema + LLM)
  - Step 4: Conditional correction

- **LLM Provider Support**
  - OpenAI GPT-5 vision support
  - Claude Opus 4.1 / Sonnet 4.5 / Haiku 3.5 support
  - Abstract provider interface for extensibility
  - Direct PDF upload (no text extraction) for complete data fidelity

- **Publication Type Support**
  - Interventional trials (RCT, cluster-RCT, before-after, single-arm)
  - Observational analytic studies (cohort, case-control, cross-sectional)
  - Evidence synthesis (meta-analysis, systematic reviews)
  - Prediction/prognosis models (risk prediction, ML algorithms)
  - Editorials and opinion pieces (commentary, letters)
  - Other category (case reports, narrative reviews, guidelines)

- **Dual Validation Strategy**
  - Tier 1: Fast schema validation (jsonschema library)
  - Tier 2: Conditional LLM semantic validation (only if quality ≥ 50%)
  - Quality score calculation (schema compliance + completeness)
  - Cost optimization through conditional expensive validation

- **Schema System**
  - JSON Schema-based structured output enforcement
  - Schema bundling for LLM compatibility (inline all $ref)
  - Type-specific schemas for different publication types
  - Compatibility validation for OpenAI structured outputs

- **File Management**
  - PDF filename-based file naming
  - Consistent naming across pipeline steps
  - Automatic `tmp/` directory management
  - JSON output for all intermediate and final results

- **Web Interface**
  - Streamlit-based web UI for easy interaction
  - Drag-and-drop PDF upload with duplicate detection
  - Interactive pipeline configuration
  - View and download results for each step
  - Previously uploaded files library

- **Development Features**
  - Breakpoint system for step-by-step testing
  - Rich CLI output with progress indicators
  - Detailed error messages and recovery strategies
  - Environment variable configuration (.env support)

- **Documentation**
  - Comprehensive README.md with usage examples
  - VALIDATION_STRATEGY.md explaining dual validation design
  - Module-level documentation (src/README.md)
  - Schema documentation (schemas/readme.md)
  - Prompt engineering guidelines (prompts/README.md)

### Technical Details
- Python 3.10+ required
- Dependencies: openai, anthropic, jsonschema, rich, python-dotenv
- API limits: 100 pages, 32 MB per PDF (provider constraints)
- Token usage: ~1,500-3,000 tokens per page
- Cost: ~$0.80-$3.00 per 20-page paper (provider dependent)

### Configuration
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` for provider selection
- `OPENAI_MODEL` / `ANTHROPIC_MODEL` for model selection
- `LLM_TEMPERATURE` (default: 0.0 for deterministic extractions)
- `MAX_PDF_PAGES` / `MAX_PDF_SIZE_MB` for constraints
- `SCHEMA_QUALITY_THRESHOLD` (default: 0.5) for validation gating

### Licensing
- Dual-license model implemented:
  - Prosperity Public License 3.0.0 for non-commercial use
  - Commercial license available for commercial use
  - 30-day free trial for commercial evaluation

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

## [Unreleased] - What's Next?

See `ROADMAP.md` for planned features and improvements.

Considering:
- Batch processing support
- Web interface (Streamlit/Gradio)
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
