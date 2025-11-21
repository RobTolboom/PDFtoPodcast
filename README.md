# PDFtoPodcast: Medical Literature Extraction Pipeline

[![License: PPL 3.0.0](https://img.shields.io/badge/License-PPL%203.0.0-blue.svg)](LICENSE)
[![Commercial License Available](https://img.shields.io/badge/Commercial-License%20Available-green.svg)](COMMERCIAL_LICENSE.md)

**Intelligent medical literature data extraction pipeline using LLM vision capabilities for complete data fidelity.**

This pipeline extracts structured data from medical research PDFs with a focus on **preserving tables, figures, and complex formatting** that are critical for clinical trials and medical research papers.

---

## Quick Links

| Documentation | Description |
|---------------|-------------|
| **[Installation](#installation)** | Get started in 5 minutes |
| **[Usage Guide](#usage)** | Web UI and CLI instructions |
| **[Architecture](#architecture)** | Pipeline design and flow |
| **[Contributing](CONTRIBUTING.md)** | Development guidelines |
| **[API Reference](src/README.md)** | Module documentation |

---

## Key Features

- Direct PDF-to-LLM processing (no intermediate text extraction) to preserve tables, figures, and layout.
- Publication-type-aware schemas for interventional, observational, synthesis, prognosis, opinion, and other papers.
- Iterative validation/correction loop with configurable accuracy, completeness, and schema thresholds.
- **Critical appraisal** with standardized tools (RoB 2, ROBINS-I, PROBAST, AMSTAR 2, GRADE ratings).
- Dual entry points: Streamlit dashboard for guided runs and CLI module for automation and scripting.
- Structured JSON outputs with deterministic file naming in `tmp/` for each pipeline step.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  PDF Input (≤100 pages, ≤32 MB)              │
└──────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 1: Classification                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ • Upload PDF to LLM (vision)                           │ │
│  │ • Identify publication type (6 categories)             │ │
│  │ • Extract metadata (DOI, authors, journal, etc)        │ │
│  │ Output: classification.json                            │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 2: Extraction                                          │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ • Upload PDF to LLM (vision)                           │ │
│  │ • Type-specific schema (interventional/observational)  │ │
│  │ • Extract tables, figures, complete data               │ │
│  │ Output: extraction.json                                │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 3: Validation & Correction (Iterative Loop)           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ While quality insufficient AND iterations < max:       │ │
│  │                                                          │ │
│  │  3a. Validation (Dual-Tier)                            │ │
│  │      ┌───────────────────────────────────────────────┐ │ │
│  │      │ Schema validation (fast, free)                │ │ │
│  │      │ • Check structure & types                     │ │ │
│  │      │ • Quality score ≥50% → proceed to LLM         │ │ │
│  │      │ • Quality score <50% → fail immediately       │ │ │
│  │      └───────────────────────────────────────────────┘ │ │
│  │      ┌───────────────────────────────────────────────┐ │ │
│  │      │ LLM validation (if schema passed)             │ │ │
│  │      │ • Upload PDF for comparison                   │ │ │
│  │      │ • Semantic accuracy check                     │ │ │
│  │      │ • Completeness verification                   │ │ │
│  │      │ Output: validation{N}.json                    │ │ │
│  │      └───────────────────────────────────────────────┘ │ │
│  │                                                          │ │
│  │  3b. Quality Assessment                                │ │
│  │      • Check completeness ≥90%                         │ │
│  │      • Check accuracy ≥95%                             │ │
│  │      • Check schema compliance ≥95%                    │ │
│  │      • Check critical_issues = 0                       │ │
│  │                                                          │ │
│  │  3c. If quality insufficient:                          │ │
│  │      • Run correction with validation feedback         │ │
│  │      • Upload PDF + validation report to LLM           │ │
│  │      • Fix identified issues                           │ │
│  │      • Output: extraction{N}.json                      │ │
│  │      • Loop back to 3a (validate corrected)            │ │
│  │                                                          │ │
│  │  3d. Early Stopping:                                   │ │
│  │      • If quality degrades 2 consecutive iterations    │ │
│  │      • Select best iteration and exit                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  Output: Best extraction + validation from all iterations    │
│  Status: passed / max_iterations_reached / early_stopped     │
└──────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 4: Critical Appraisal (Iterative Loop)                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ While quality insufficient AND iterations < max:       │ │
│  │                                                          │ │
│  │  4a. Appraisal (Study-Type Specific)                   │ │
│  │      • Upload PDF + extraction to LLM                   │ │
│  │      • Route to appropriate tool:                       │ │
│  │        - RoB 2 for RCTs (5 domains + overall)          │ │
│  │        - ROBINS-I for observational (7 domains)        │ │
│  │        - PROBAST for prediction models                 │ │
│  │        - AMSTAR 2 + ROBIS for meta-analyses            │ │
│  │        - Argument quality for editorials               │ │
│  │      • Assess each domain with rationales              │ │
│  │      • GRADE certainty ratings per outcome             │ │
│  │      Output: appraisal{N}.json                         │ │
│  │                                                          │ │
│  │  4b. Quality Assessment                                │ │
│  │      • Check logical consistency ≥90%                  │ │
│  │      • Check completeness ≥85%                         │ │
│  │      • Check evidence support ≥90%                     │ │
│  │      • Check schema compliance ≥95%                    │ │
│  │      • Check critical_issues = 0                       │ │
│  │                                                          │ │
│  │  4c. If quality insufficient:                          │ │
│  │      • Run correction with validation feedback         │ │
│  │      • Upload PDF + validation + extraction to LLM     │ │
│  │      • Fix inconsistencies and missing rationales      │ │
│  │      • Output: appraisal{N+1}.json                     │ │
│  │      • Loop back to 4b (validate corrected)            │ │
│  │                                                          │ │
│  │  4d. Early Stopping:                                   │ │
│  │      • If quality degrades 2 consecutive iterations    │ │
│  │      • Select best iteration and exit                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  Output: Best appraisal + validation from all iterations     │
│  Status: passed / max_iterations_reached / early_stopped     │
└──────────────────────────────────────────────────────────────┘
```

**For detailed architecture and design decisions, see [ARCHITECTURE.md](ARCHITECTURE.md)**

**For critical appraisal tools and methodology, see [features/appraisal.md](features/appraisal.md)**

*Tip:* Moet je voor legacy-workflows slechts één appraisal-run zonder iteratieve correcties draaien? Gebruik dan
`python run_pipeline.py paper.pdf --step appraisal --appraisal-single-pass` of schakel in de Streamlit settings de optie
“Enable iterative appraisal correction” uit. Dit schrijft de klassieke `paper-appraisal.json` / `paper-appraisal_validation.json`
bestanden weg naast de gebruikelijke `*-best.json` artefacten. Voor een complete handleiding zie [`docs/appraisal.md`](docs/appraisal.md).

### Running the appraisal step

| Mode        | Command / Action                                                                                          |
|-------------|-----------------------------------------------------------------------------------------------------------|
| CLI (full)  | `python run_pipeline.py paper.pdf --llm openai` – voert alle stappen incl. appraisal uit                  |
| CLI (only)  | `python run_pipeline.py paper.pdf --step appraisal --appraisal-max-iter 5 --appraisal-logical-threshold 0.92` |
| CLI legacy  | `python run_pipeline.py paper.pdf --step appraisal --appraisal-single-pass`                                |
| Streamlit   | Settings → enable “Appraisal” step, configure thresholds/iterations, optioneel single-pass toggle          |
| Retry only  | In de Execution UI op “Re-run appraisal” klikken – draait enkel de appraisal-stap opnieuw                  |

> The diagram shows provider hard limits (32 MB, 100 pages). By default the pipeline caps uploads at 10 MB
> to match the Streamlit uploader and `MAX_PDF_SIZE_MB` setting—raise it in your `.env` only if your provider
> account allows larger PDFs.

---

## Installation

### Prerequisites
- Python 3.10+ with `pip` and (optionally) `make` available on your PATH.
- Access to an OpenAI or Anthropic account with document/vision models enabled and a valid API key.
- Internet connectivity for LLM API calls and PDF uploads (approx. 1–3K tokens per PDF page).
- Local environment capable of opening a browser window for Streamlit (or a remote session that supports it).
- De-identify PDFs before processing; documents are transmitted to external LLM providers.

### Setup

```bash
# Clone repository
git clone https://github.com/RobTolboom/PDFtoPodcast.git
cd PDFtoPodcast

# (Optional) Create an isolated virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file in the project root (there is no committed template) and add your provider
credentials using the sample below.

Alternatively, run `make install` (or `make install-dev` for tooling) to reuse the Makefile targets.

### Environment Variables

Create `.env` file with:

```bash
# Required: Choose one or both providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Optional: Model selection
OPENAI_MODEL=gpt-5           # Default: gpt-5 (vision support)
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022  # Default: Sonnet 4.5

# Optional: Token limits
OPENAI_MAX_TOKENS=128000     # Default in config; lower if your account has tighter limits
ANTHROPIC_MAX_TOKENS=4096

# Optional: Temperature (0.0 = deterministic)
LLM_TEMPERATURE=0.0

# Optional: Timeout (seconds)
LLM_TIMEOUT=600              # Config default, rounded up to allow long extractions

# Optional: PDF limits (API constraints)
MAX_PDF_PAGES=100             # Default: 100 (API limit)
MAX_PDF_SIZE_MB=10            # Pipeline default (increase up to 32 MB if your provider allows it)
```

You can omit any optional keys—those shown above match the defaults baked into
`src/config.py`. Increase `MAX_PDF_SIZE_MB` only if your LLM provider account allows
larger uploads (OpenAI and Claude currently cap at 32 MB).

#### Obtaining API keys
- OpenAI: create a key from the [API Keys dashboard](https://platform.openai.com/account/api-keys).
- Anthropic: generate a key via the [Claude console](https://console.anthropic.com/settings/keys).
- Store keys securely (e.g., password manager) and avoid committing `.env` to version control.

---

## Usage

### Web Interface (Recommended)

The easiest way to use PDFtoPodcast is through the **Streamlit web interface**:

```bash
streamlit run app.py
```

**Features:**
-  **Drag-and-drop PDF upload** with duplicate detection
-  **Interactive pipeline configuration** (select steps, LLM provider, page limits)
-  **Real-time execution screen** with live progress tracking per step
-  **Inspect existing results** from the Settings screen with JSON syntax highlighting
-  **Re-run specific phases** by deselecting completed steps in Settings and starting the run again
-  **Previously uploaded files library** for easy file selection
-  **Intelligent error handling** with actionable recovery guidance
-  **Verbose logging toggle** for detailed pipeline diagnostics

>  The dedicated “Results” dashboard is still under development—after a run completes
> you return to Settings, where you can open or delete the generated JSON files.

**Perfect for:**
- First-time users
- Testing and experimentation
- Reviewing results interactively
- Real-time progress monitoring
- Non-technical users

---

### Command-Line Interface

For automation and batch processing, use the CLI:

```bash
# Run full pipeline (all 3 steps)
python run_pipeline.py path/to/paper.pdf

# Run with Claude
python run_pipeline.py path/to/paper.pdf --llm-provider claude

# Process only first 10 pages (for testing)
python run_pipeline.py path/to/paper.pdf --max-pages 10

# Run single step only
python run_pipeline.py path/to/paper.pdf --step classification

# Run iterative validation-correction with custom settings
python run_pipeline.py path/to/paper.pdf --step validation_correction ^
    --max-iterations 2 ^
    --completeness-threshold 0.85 ^
    --accuracy-threshold 0.90

# Keep intermediate files
python run_pipeline.py path/to/paper.pdf --keep-tmp

# Report rendering options
python run_pipeline.py path/to/paper.pdf --step report_generation ^
    --report-renderer weasyprint ^
    --disable-figures ^
    --no-report-compile-pdf
```

#### Logs & troubleshooting
- CLI runs stream to the terminal via Rich—rerun with `--keep-tmp` to inspect intermediate JSON under `tmp/`.
- In Streamlit, enable **Verbose logging** in Settings to display per-step token usage and metadata in the Execution screen.
- Errors always include a concise remediation checklist; review the linked JSON artefacts for deeper context.

### Command-Line Options (excerpt)

```
usage: run_pipeline.py [-h] [--max-pages MAX_PAGES] [--keep-tmp]
                       [--llm-provider {openai,claude}]
                       [--step {classification,extraction,validation,correction,validation_correction,report_generation}]
                       [--max-iterations MAX_ITERATIONS]
                       [--completeness-threshold FLOAT]
                       [--accuracy-threshold FLOAT]
                       [--schema-threshold FLOAT]
                       [--report-language {nl,en}]
                       [--report-renderer {latex,weasyprint}]
                       [--report-compile-pdf] [--no-report-compile-pdf]
                       [--enable-figures] [--disable-figures]
                       pdf

positional arguments:
  pdf                   Path to PDF file

optional arguments:
  -h, --help            Show help message
  --max-pages MAX_PAGES Limit number of pages (for testing)
  --keep-tmp            Keep intermediate files in tmp/
  --llm-provider {openai,claude}
                        Choose LLM provider (default: openai)
  --step {classification,extraction,validation,correction,validation_correction}
                        Run specific pipeline step (default: run all steps)
  --max-iterations MAX_ITERATIONS
                        Maximum correction attempts for validation_correction (default: 3)
  --completeness-threshold FLOAT
                        Minimum completeness score 0.0-0.99 (default: 0.90)
  --accuracy-threshold FLOAT
                        Minimum accuracy score 0.0-0.99 (default: 0.95)
  --schema-threshold FLOAT
                        Minimum schema compliance score 0.0-0.99 (default: 0.95)
  --report-language {nl,en}
                        Language for report generation (default: nl)
  --report-renderer {latex,weasyprint}
                        Renderer for report output (default: latex)
  --report-compile-pdf
  --no-report-compile-pdf
                        Enable/disable PDF compilation (LaTeX only; .tex/.md always written)
  --enable-figures
  --disable-figures
                        Toggle generation of report figures (traffic light, forest)
```

### Programmatic Usage

```python
from pathlib import Path
from src.pipeline import run_four_step_pipeline

# Run complete pipeline
results = run_four_step_pipeline(
    pdf_path=Path("paper.pdf"),
    max_pages=20,  # Optional: limit pages
    llm_provider="openai",  # or "claude"
    breakpoint_after_step=None  # Optional: "classification", "extraction", etc.
)

# Access results
print(f"Type: {results['classification']['publication_type']}")
print(f"Extracted fields: {len(results['extraction'])}")
```

**For detailed API documentation, see [src/README.md](src/README.md)**

---

## Supported Publication Types

The pipeline supports 6 publication type categories:

| Type | Description | Examples |
|------|-------------|----------|
| `interventional_trial` | Clinical trials with intervention | RCT, Cluster-RCT, Before-after, Single-arm |
| `observational_analytic` | Observational studies | Cohort, Case-control, Cross-sectional |
| `evidence_synthesis` | Systematic reviews | Meta-analysis, Network meta-analysis, Systematic review |
| `prediction_prognosis` | Prediction models | Risk prediction, Prognostic models, ML algorithms |
| `editorials_opinion` | Opinion pieces | Editorial, Commentary, Letter to editor |
| `overig` | Other | Case reports, Narrative reviews, Guidelines |

Each type has a specialized extraction schema optimized for its data structure.

---

## Output Structure

All outputs are saved in `tmp/` directory with PDF filename-based naming:

```
tmp/
├── sample_paper-classification.json
├── sample_paper-extraction0.json
├── sample_paper-validation0.json
├── sample_paper-extraction1.json          # Iteration 1 correction (if triggered)
├── sample_paper-validation1.json          # Validation after correction 1
├── sample_paper-extraction-best.json      # Best-scoring extraction (any iteration)
├── sample_paper-validation-best.json      # Validation paired with best extraction
└── sample_paper-extraction-best-metadata.json
```

Iteration files are numbered (`extraction0`, `extraction1`, …) so you can track every correction pass. When the pipeline selects a best iteration it also writes `*-best.json` artefacts plus metadata about the choice. Failed runs may emit `*-failed.json` diagnostics.

### Output Format

Each JSON file contains structured data conforming to its schema:

**Classification output:**
```json
{
  "metadata": {
    "title": "Study Title",
    "doi": "10.1186/s12871-025-02345-6",
    "journal": "BMC Anesthesiology",
    "authors": [...]
  },
  "publication_type": "interventional_trial",
  "classification_confidence": 0.95
}
```

**Extraction output:**
```json
{
  "schema_version": "v2.0",
  "metadata": {...},
  "study_design": {...},
  "population": {...},
  "interventions": [...],
  "outcomes": [...],
  "results": {...}
}
```

---

## Iterative Validation-Correction

Selecting the `validation_correction` step (CLI or Streamlit) triggers an iterative loop that validates each extraction and, if needed, re-prompts the LLM with targeted feedback.

- Default thresholds (completeness ≥90%, accuracy ≥95%, schema ≥95%, critical issues = 0) are configurable via CLI flags or the Streamlit Settings sliders.
- The first pass always runs schema validation; LLM validation only executes when schema quality is at least 50%.
- Up to three correction attempts run after the initial extraction. The loop stops early if quality degrades, schema quality drops below 50%, or the provider repeatedly errors.
- Every iteration writes JSON artefacts to `tmp/` (e.g., `paper-extraction1.json`, `paper-validation1.json`). The pipeline returns the best-scoring iteration.

Refer to [VALIDATION_STRATEGY.md](VALIDATION_STRATEGY.md) for scoring formulas, prompts, and trade-offs.

---

## Cost Considerations

### PDF Upload vs Text Extraction

| Approach | Tokens/Page | Data Quality | Best For |
|----------|-------------|--------------|----------|
| **Text extraction** (old) | ~500 |  Tables lost | Simple documents |
| **PDF upload** (current) | ~1,500-3,000 |  Complete fidelity | Medical research |

### Cost Example (20-page paper)

| Provider | Input Cost | Output Cost | Total per Paper |
|----------|------------|-------------|-----------------|
| **OpenAI GPT-5** | $0.20 (40k tokens) | $0.60 (4k tokens) | **~$0.80** |
| **Claude Opus 4.1** | $0.60 (40k tokens) | $2.40 (4k tokens) | **~$3.00** |

**Full pipeline (4 steps):** ~$3-12 per paper depending on provider and corrections needed.

> Pricing snapshot: October 2024 public rate cards. Recalculate with your provider’s latest pricing and negotiated discounts.

---

## Validation Strategy (Summary)

- Tier 1: Local schema validation with `jsonschema` verifies structure and required fields in milliseconds.
- Tier 2: Optional LLM validation cross-checks content against the PDF when schema quality meets the `SCHEMA_QUALITY_THRESHOLD` (default 0.5).
- Thresholds, retries, and correction prompts are documented in [VALIDATION_STRATEGY.md](VALIDATION_STRATEGY.md). Start there before altering validation behaviour.

---

## Development

### Project Structure

```
PDFtoPodcast/
├── run_pipeline.py              # Main CLI entry point
├── app.py                       # Streamlit web UI entry point
├── requirements.txt             # Dependencies
├── .env                         # Configuration (create manually; see README)
├── src/                         # Core modules
│   ├── config.py                # Settings & configuration
│   ├── prompts.py               # Prompt loading
│   ├── schemas_loader.py        # Schema management
│   ├── validation.py            # Validation utilities
│   ├── llm/                     # LLM provider package
│   ├── pipeline/                # Pipeline orchestration
│   └── streamlit_app/           # Web UI components
├── prompts/                     # Prompt templates
├── schemas/                     # JSON schemas
├── tests/                       # Test suite
└── tmp/                         # Output directory (auto-created)
```

**For complete module documentation, see [src/README.md](src/README.md)**

### Quick Development Commands

```bash
# Development workflow
make format       # Format code
make lint         # Check for issues
make typecheck    # Type checking
make check        # All checks

# Testing
make test         # Run all tests
make test-fast    # Quick tests
make test-coverage # With coverage

# Git workflow
make commit       # Prepare for commit
git commit -m "type: description"
git push
```

**For complete development guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md)**

---

## API Limits & Constraints

### OpenAI API Limits
- **Provider limit:** 100 pages, 32 MB per PDF
- **Pipeline default upload size:** 10 MB (adjust with `MAX_PDF_SIZE_MB`)
- **Models:** gpt-5 (vision-capable model)
- **Format:** Base64-encoded PDF

### Claude API Limits
- **Provider limit:** 100 pages, 32 MB per PDF
- **Pipeline default upload size:** 10 MB (adjust with `MAX_PDF_SIZE_MB`)
- **Models:** Claude Opus 4.1, Sonnet 4.5, Haiku 3.5
- **Format:** Base64-encoded PDF with `application/pdf` media type

---

## Documentation

| Document | Purpose |
|----------|---------|
| **[README.md](README.md)** (this file) | Quick start and overview |
| **[src/README.md](src/README.md)** | Module API reference |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | System design and decisions |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Development guidelines |
| **[DEVELOPMENT.md](DEVELOPMENT.md)** | Development workflow |
| **[VALIDATION_STRATEGY.md](VALIDATION_STRATEGY.md)** | Dual validation approach |
| **[prompts/README.md](prompts/README.md)** | Prompt engineering |
| **[schemas/readme.md](schemas/readme.md)** | Schema design |
| **[CHANGELOG.md](CHANGELOG.md)** | Version history |

---

## Contributing

Contributions welcome! Please:

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines
2. Fork the repository
3. Create a feature branch
4. Add tests for new features
5. Update documentation
6. Submit pull request

---

## License

This project uses a **dual-license model**:

### Free Use (Prosperity Public License 3.0.0)
-  **Academic research** - Free forever
-  **Non-commercial use** - Free forever
-  **Commercial trial** - Free for 30 days (company-wide)
-  See [LICENSE](LICENSE) for full terms

### Commercial Use
-  After 30-day trial, commercial use requires a paid license
-  Flexible pricing: Subscription or Pay-per-PDF
-  Self-hosted on your infrastructure
-  See [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md) for terms
-  For commercial licensing inquiries: Open a GitHub issue or discussion

---

## Contact

For questions or issues, please open a GitHub issue.

---

**Built with  for medical research data extraction**
