# Changelog

All notable changes to PDFtoPodcast will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Professional development documentation structure
  - ARCHITECTURE.md - Complete system architecture documentation
  - CONTRIBUTING.md - Developer contribution guide
  - DEVELOPMENT.md - Local development workflow guide
  - API.md - Module and function reference
  - TESTING.md - Testing strategy and guidelines

### Changed
- Nothing yet

### Deprecated
- Nothing yet

### Removed
- Nothing yet

### Fixed
- Nothing yet

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
  - DOI-based filename generation
  - Consistent naming across pipeline steps
  - Automatic `tmp/` directory management
  - JSON output for all intermediate and final results

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
