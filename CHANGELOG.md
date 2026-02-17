# Changelog

All notable changes to PDFtoPodcast will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
