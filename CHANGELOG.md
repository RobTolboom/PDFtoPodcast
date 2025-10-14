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
