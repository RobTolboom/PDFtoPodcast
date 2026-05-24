# Changelog

All notable changes to PDFtoPodcast will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Raise default reasoning effort for validation and correction steps to `high`** — more thinking budget for the validation→correction loop produces more precise error identification and better targeted fixes, improving completeness scores; overridable via `REASONING_EFFORT_VALIDATION` and `REASONING_EFFORT_CORRECTION` env vars
- **Upgrade default OpenAI model from `gpt-5.1` to `gpt-5.5`** — GPT-5.5 (released 2026-04-24) reduces hallucinated claims by 52.5% on high-stakes medical prompts and improves structured output quality; overridable via `OPENAI_MODEL` env var

### Fixed

- **Max correction iterations raised from 3 to 5** — default for both `IterativeLoopConfig.max_iterations` and the `--max-iterations` CLI flag changed from 3 to 5, giving the correction loop more attempts to reach the 95% schema compliance threshold before giving up
- **Show summary schema validation no longer fails on provider-injected fields** — `_metadata` and `usage` fields added by LLM providers are now stripped from the show summary response before jsonschema validation, preventing spurious "Additional properties are not allowed" failures when the schema has `additionalProperties: false`
- **Podcast synopsis `maxLength` raised from 500 to 750 characters** — a 2–3 sentence synopsis for a complex interventional trial can legitimately exceed 500 characters; the manual length check in `podcast_logic.py` is updated to match
- **`schema_repair.py` now removes incomplete optional object fields** — when an optional field (e.g. `sensitivity_analyses[n].effect`) is present but its value is a dict missing required sub-schema fields (e.g. `type` and `point`), the field is removed entirely rather than left as an invalid object; this deterministically fixes the `sensitivity_analyses/0/effect: 'type' is a required property` schema compliance error that occurred when a paper reported sensitivity analyses qualitatively without numeric estimates
- **`FigureSummary.key_values` schema extended to allow depth-1 objects** — `common.schema.json` now accepts values that are flat objects (e.g. CONSORT exclusion breakdowns) in addition to scalars; all five bundled schemas regenerated
- **`ContrastResult.effect` made optional in `interventional_trial` and `observational_analytic` schemas** — prevents spurious required-field validation errors when a paper reports qualitative sensitivity analyses without numeric effect estimates
- **`schema_repair.py` normalises bare `schema_version` values** — the LLM sometimes produces `"1.0"` instead of `"v1.0"`; the repair layer now adds the missing `v` prefix before validation so the field is never flagged as a constraint violation
- **`schema_repair.py` drops malformed JSON-fragment strings from object-typed arrays** — the LLM occasionally serialises an object into a JSON string and inserts that string into an array that should contain objects; such strings (containing `{`, `}`, `[`, `]`, `"`, or `:`) are now silently dropped before validation instead of being kept as unrestorable items
- **`schema_repair.py` flattens depth-2+ `key_values` objects in `figures_summary`** — when the LLM produces deeply nested objects inside `key_values` (depth-2 or more), they are flattened to depth-1 using dot-separated keys (e.g. `exclusions.pre_screening.medical`) so the result conforms to the schema constraint
- **Podcast abbreviation check is now case-sensitive** — removing `re.IGNORECASE` from the abbreviation regex prevents false positives where words like `invasive` or `Versus` were incorrectly matched against abbreviations `vs`, eliminating spurious abbreviation warnings for transcripts that contain no real abbreviations

## [0.2.0] - 2026-04-26

### Fixed

- Correction loop headers now appear **before** `Correcting...` instead of after the previous correction's result (GH #38)
- Step headers for STEP 4 (Critical Appraisal) and STEP 5 (Report Generation) now print immediately when the step starts, before any LLM call, so the user always sees which step is running

### Security

- Bump `python-dotenv` to `>=1.2.2` — fixes symlink-following arbitrary file overwrite (CVE, GH #15)
- Bump `pillow` to `>=12.2.0` — fixes FITS GZIP decompression bomb (GH #14)
- Pin `tornado>=6.5.5` — fixes cookie attribute injection (GH #13), DoS via excessive multipart parts (GH #9), and incomplete cookie attribute validation (GH #8)
- Pin `Pygments>=2.20.0` — fixes ReDoS via inefficient GUID regex (GH #12)
- Pin `requests>=2.33.0` — fixes insecure temp file reuse in `extract_zipped_paths` (GH #11)

### Added

- **Podcast Show Summary** - Plain-text episode companion generated alongside the podcast transcript
  - Citation in Vancouver/NLM style, 2-3 sentence narrative synopsis, structured "Study at a glance" bullets
  - Adapts bullet structure to study type (RCT, observational, systematic review, prediction, editorial)
  - Includes exact numbers (ORs, CIs, p-values) and inline GRADE certainty ratings
  - Second LLM call within existing podcast generation step (no new pipeline step)
  - Light validation: synopsis length, bullet count, GRADE language alignment
  - Rendered as plain text in podcast markdown, copy-pasteable into podcast apps
  - CLI shows summary bullet count in pipeline summary table
  - Streamlit UI shows expandable summary with copy button

### Changed

- Consistent `═══ STEP N: NAME ═══` headers across all 6 pipeline steps (classification through podcast)
- Appraisal debug messages (Tool routing, Running...) hidden in compact mode, visible with `--verbose`
- Zero-value metrics display as "N/A" instead of "0.0%" in quality summaries
- Iterative correction loop console output redesigned for readability: "Correction N of M" format with compact before→after quality deltas, plain-language failure messages, and `--verbose` / `-v` CLI flag for detailed debugging output
- Iterative correction loop now uses best-so-far result when a correction degrades quality, instead of feeding the degraded result into the next correction attempt
- Correction loop improvements: deterministic repair for pattern/minimum/enum constraint violations in `schema_repair.py`, proportional schema scoring (replaces binary pass/fail cliff), explicit empty-string omission rule in correction prompt, previous-failure context injected into correction retries, and early exit after 2 consecutive quality degradations

## [0.1.0] - 2026-02-17

Initial release of PDFtoPodcast: an LLM-powered pipeline that extracts structured data from medical research PDFs and generates critical appraisal reports and podcast-ready transcripts.

### Added

- **6-step pipeline** (Classification → Extraction → Validation/Correction → Appraisal → Report → Podcast) with modular step architecture (`src/pipeline/steps/`)
- **Critical Appraisal** with automatic tool routing (RoB 2, ROBINS-I, PROBAST, AMSTAR 2/ROBIS) and per-outcome GRADE certainty ratings
- **Report Generation** with block-based JSON architecture, LaTeX/WeasyPrint PDF rendering, iterative validation-correction loop, and Matplotlib figure generation (RoB traffic light, forest plot, PRISMA, CONSORT)
- **Podcast Generation** with TTS-ready transcript, single-pass validation (word count, GRADE language alignment, numerical accuracy), and markdown rendering
- **Iterative validation-correction loop** (`IterativeLoopRunner`) with configurable quality thresholds, early stopping on degradation, best-iteration selection, and deterministic schema repair layer
- **Schema-based structured extraction** for 5 publication types (interventional trial, observational analytic, evidence synthesis, prediction/prognosis, editorial/opinion) via direct PDF upload to OpenAI GPT-5.1
- **JSON schemas** with automated bundling (`schemas/json-bundler.py`) for OpenAI structured output, plus dedicated appraisal, report, and podcast schemas
- **Streamlit web UI** with real-time execution progress, per-step settings (quality thresholds, iteration limits), artifact downloads (PDF, JSON, markdown), and iteration history tables
- **CLI** with single-step execution (`--step`), quality threshold configuration, output selection (`--output report|podcast|both`), and comprehensive summary tables
- **Comprehensive test suite** (524 tests: unit + integration) with pytest markers, and professional documentation (ARCHITECTURE.md, CONTRIBUTING.md, DEVELOPMENT.md, API.md, TESTING.md)

### Changed

- English-only system (Dutch/bilingual support removed)
- Modular package architecture: `src/pipeline/steps/`, `src/llm/`, `src/streamlit_app/`, `src/rendering/`
- Numbered iteration file naming (`extraction0.json`, `extraction1.json`, ...)

### Removed

- Dutch/bilingual language support
- Non-functional `--quiet`/`--verbose` CLI flags and unused `PipelineOutputManager`

### Fixed

- Iterative correction loop: retry logic off-by-one, counter scoping across iterations, file overwrites during re-validation, double validation waste, schema quality field path mismatches, and loop hang on schema failure
- Schema validation: bundler recursion and self-referencing definitions, DOI pattern rejection, null value handling, evidence synthesis field misalignment, and schema compliance key mismatch
- CLI and Streamlit UI: import error (`run_four_step_pipeline` → `run_full_pipeline`), summary table showing 0% quality, navigation state persistence, execution lock for long-running LLM calls, real-time feedback visibility, and auto-redirect behavior

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

---

[Unreleased]: https://github.com/RobTolboom/PDFtoPodcast/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/RobTolboom/PDFtoPodcast/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/RobTolboom/PDFtoPodcast/releases/tag/v0.1.0
