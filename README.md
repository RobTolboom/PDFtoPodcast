# 📄 PDFtoPodcast: Medical Literature Extraction Pipeline

[![License: PPL 3.0.0](https://img.shields.io/badge/License-PPL%203.0.0-blue.svg)](LICENSE)
[![Commercial License Available](https://img.shields.io/badge/Commercial-License%20Available-green.svg)](COMMERCIAL_LICENSE.md)

**Intelligent medical literature data extraction pipeline using LLM vision capabilities for complete data fidelity.**

This pipeline extracts structured data from medical research PDFs with a focus on **preserving tables, figures, and complex formatting** that are critical for clinical trials and medical research papers.

---

## 🔗 Quick Links

| Documentation | Description |
|---------------|-------------|
| **[Installation](#-installation)** | Get started in 5 minutes |
| **[Usage Guide](#-usage)** | Web UI and CLI instructions |
| **[Architecture](#️-architecture)** | Pipeline design and flow |
| **[Contributing](CONTRIBUTING.md)** | Development guidelines |
| **[API Reference](src/README.md)** | Module documentation |

---

## ✨ Key Features

- **🎯 Direct PDF Upload** - No text extraction, LLMs analyze PDFs directly using vision capabilities
- **📊 Complete Data Preservation** - Tables, figures, charts fully analyzed and extracted
- **🏥 Medical Literature Focused** - Optimized for clinical trials, systematic reviews, observational studies
- **🔄 Four-Step Pipeline** - Classification → Extraction → Validation → Correction
- **✅ Dual Validation** - Schema validation + LLM semantic validation for quality assurance
- **🤖 Multi-Provider** - Supports both OpenAI (GPT-5) and Claude (Opus/Sonnet)
- **📐 Schema-Based** - JSON Schema enforcement for structured outputs
- **💾 Smart File Management** - Automatic file naming using PDF filename

---

## 🏗️ Architecture

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
│  │      │ Output: validation.json (or -correctedN)      │ │ │
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
│  │      • Output: extraction-correctedN.json              │ │
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
```

**For detailed architecture and design decisions, see [ARCHITECTURE.md](ARCHITECTURE.md)**

---

## 📦 Installation

### Requirements
- Python 3.10+
- OpenAI API key (for GPT-5) or Anthropic API key (for Claude)

### Setup

```bash
# Clone repository
git clone https://github.com/RobTolboom/PDFtoPodcast.git
cd PDFtoPodcast

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

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
OPENAI_MAX_TOKENS=4096
ANTHROPIC_MAX_TOKENS=4096

# Optional: Temperature (0.0 = deterministic)
LLM_TEMPERATURE=0.0

# Optional: Timeout (seconds)
LLM_TIMEOUT=120

# Optional: PDF limits (API constraints)
MAX_PDF_PAGES=100             # Default: 100 (API limit)
MAX_PDF_SIZE_MB=32            # Default: 32 (API limit)
```

---

## 🚀 Usage

### Web Interface (Recommended)

The easiest way to use PDFtoPodcast is through the **Streamlit web interface**:

```bash
streamlit run app.py
```

**Features:**
- 📤 **Drag-and-drop PDF upload** with duplicate detection
- ⚙️ **Interactive pipeline configuration** (select steps, LLM provider, page limits)
- 🚀 **Real-time execution screen** with live progress tracking per step
- 👁️ **View results** for each pipeline step with JSON syntax highlighting
- 🔄 **Re-run individual steps** without full pipeline execution
- 📁 **Previously uploaded files library** for easy file selection
- ⚠️ **Intelligent error handling** with actionable recovery guidance
- 🔍 **Verbose logging toggle** for detailed pipeline diagnostics

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
python run_pipeline.py path/to/paper.pdf --step validation_correction \
    --max-iterations 2 \
    --completeness-threshold 0.85 \
    --accuracy-threshold 0.90

# Keep intermediate files
python run_pipeline.py path/to/paper.pdf --keep-tmp
```

### Command-Line Options

```
usage: run_pipeline.py [-h] [--max-pages MAX_PAGES] [--keep-tmp]
                       [--llm-provider {openai,claude}]
                       [--step {classification,extraction,validation,correction,validation_correction}]
                       [--max-iterations MAX_ITERATIONS]
                       [--completeness-threshold FLOAT]
                       [--accuracy-threshold FLOAT]
                       [--schema-threshold FLOAT]
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

## 📊 Supported Publication Types

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

## 📂 Output Structure

All outputs are saved in `tmp/` directory with PDF filename-based naming:

```
tmp/
├── sample_paper-classification.json
├── sample_paper-extraction.json
├── sample_paper-validation.json
├── sample_paper-extraction-corrected.json  # If correction needed
└── sample_paper-validation-corrected.json  # Final validation
```

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

## 🔄 Iterative Validation-Correction

The pipeline uses an **iterative correction loop** to progressively improve extraction quality until it meets your requirements.

### How It Works

1. **Initial Validation**: Extract data, then validate (schema + LLM)
2. **Quality Assessment**: Check if extraction meets quality thresholds:
   - Completeness ≥90% (how much of PDF data extracted)
   - Accuracy ≥95% (correctness, no hallucinations)
   - Schema compliance ≥95% (structural correctness)
   - Critical issues = 0 (no critical errors)
3. **Correction If Needed**: If quality insufficient, run correction with validation feedback
4. **Re-validate**: Validate corrected extraction
5. **Repeat**: Continue until quality sufficient OR max iterations reached (default: 3)
6. **Best Result**: Always returns highest quality iteration

### Early Stopping

The loop automatically stops early if:
- Quality degrades for 2 consecutive iterations
- Schema validation fails (<50% quality)
- LLM API failures after 3 retries with exponential backoff (1s, 2s, 4s)

### Configuration

**Default Settings:**
- Max iterations: 3 (total of 4 attempts: initial + 3 corrections)
- Completeness threshold: 0.90 (90%)
- Accuracy threshold: 0.95 (95%)
- Schema compliance threshold: 0.95 (95%)

**Customize via CLI:**
```bash
python run_pipeline.py paper.pdf --step validation_correction \
    --max-iterations 2 \
    --completeness-threshold 0.85 \
    --accuracy-threshold 0.90
```

**Customize via Web UI:**
Settings screen → "Validation & Correction" section → Adjust sliders

### Output Files

Each iteration is saved for traceability:
```
tmp/
├── paper-extraction.json              # Initial extraction (iteration 0)
├── paper-validation.json              # Initial validation
├── paper-extraction-corrected1.json   # First correction (iteration 1)
├── paper-validation-corrected1.json   # Validation of correction
├── paper-extraction-corrected2.json   # Second correction (iteration 2)
└── paper-validation-corrected2.json   # Final validation
```

The pipeline returns the **best extraction** based on composite quality score (40% completeness + 40% accuracy + 20% schema).

**Final Status Codes:**
- `passed`: Quality thresholds met
- `max_iterations_reached`: Max iterations reached, using best result
- `early_stopped_degradation`: Stopped due to quality degradation
- `failed_schema_validation`: Schema validation failed (<50% quality)
- `failed_llm_error`: LLM API error after retries
- `failed_invalid_json`: Correction produced invalid JSON
- `failed_unexpected_error`: Unexpected error occurred

---

## 💰 Cost Considerations

### PDF Upload vs Text Extraction

| Approach | Tokens/Page | Data Quality | Best For |
|----------|-------------|--------------|----------|
| **Text extraction** (old) | ~500 | ❌ Tables lost | Simple documents |
| **PDF upload** (current) | ~1,500-3,000 | ✅ Complete fidelity | Medical research |

### Cost Example (20-page paper)

| Provider | Input Cost | Output Cost | Total per Paper |
|----------|------------|-------------|-----------------|
| **OpenAI GPT-5** | $0.20 (40k tokens) | $0.60 (4k tokens) | **~$0.80** |
| **Claude Opus 4.1** | $0.60 (40k tokens) | $2.40 (4k tokens) | **~$3.00** |

**Full pipeline (4 steps):** ~$3-12 per paper depending on provider and corrections needed.

---

## 🎯 Validation Strategy

The pipeline uses a **two-tier validation approach** for cost-effectiveness:

### Tier 1: Schema Validation (Always runs)
- ⚡ Fast (milliseconds)
- 💰 Free (local validation)
- 🎯 Catches ~80% of errors (structural issues)
- Uses `jsonschema` library

### Tier 2: LLM Validation (Conditional)
- 🐌 Slow (30-60 seconds)
- 💸 Expensive (API cost)
- 🧠 Catches ~20% of errors (semantic issues)
- Only runs if schema quality ≥ 50%

**Threshold:** `SCHEMA_QUALITY_THRESHOLD = 0.5` (configurable in `run_pipeline.py`)

**For detailed validation strategy, see [VALIDATION_STRATEGY.md](VALIDATION_STRATEGY.md)**

---

## 🛠️ Development

### Project Structure

```
PDFtoPodcast/
├── run_pipeline.py              # Main CLI entry point
├── app.py                       # Streamlit web UI entry point
├── requirements.txt             # Dependencies
├── .env                         # Configuration (create from .env.example)
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

## 🔒 API Limits & Constraints

### OpenAI API Limits
- **Max pages:** 100 per PDF
- **Max file size:** 32 MB
- **Models:** gpt-5 (vision-capable model)
- **Format:** Base64-encoded PDF

### Claude API Limits
- **Max pages:** 100 per PDF
- **Max file size:** 32 MB
- **Models:** Claude Opus 4.1, Sonnet 4.5, Haiku 3.5
- **Format:** Base64-encoded PDF with `application/pdf` media type

---

## 📚 Documentation

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

## 🤝 Contributing

Contributions welcome! Please:

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines
2. Fork the repository
3. Create a feature branch
4. Add tests for new features
5. Update documentation
6. Submit pull request

---

## 📝 License

This project uses a **dual-license model**:

### Free Use (Prosperity Public License 3.0.0)
- ✅ **Academic research** - Free forever
- ✅ **Non-commercial use** - Free forever
- ✅ **Commercial trial** - Free for 30 days (company-wide)
- 📄 See [LICENSE](LICENSE) for full terms

### Commercial Use
- 💼 After 30-day trial, commercial use requires a paid license
- 📊 Flexible pricing: Subscription or Pay-per-PDF
- 🏢 Self-hosted on your infrastructure
- 📄 See [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md) for terms
- 📧 For commercial licensing inquiries: Open a GitHub issue or discussion

---

## 📧 Contact

For questions or issues, please open a GitHub issue.

---

**Built with ❤️ for medical research data extraction**
