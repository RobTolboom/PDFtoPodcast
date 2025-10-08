# 📄 PDFtoPodcast: Medical Literature Extraction Pipeline

[![License: PPL 3.0.0](https://img.shields.io/badge/License-PPL%203.0.0-blue.svg)](LICENSE)
[![Commercial License Available](https://img.shields.io/badge/Commercial-License%20Available-green.svg)](COMMERCIAL_LICENSE.md)

**Intelligent medical literature data extraction pipeline using LLM vision capabilities for complete data fidelity.**

This pipeline extracts structured data from medical research PDFs with a focus on **preserving tables, figures, and complex formatting** that are critical for clinical trials and medical research papers.

---

## ✨ Key Features

- **🎯 Direct PDF Upload** - No text extraction, LLMs analyze PDFs directly using vision capabilities
- **📊 Complete Data Preservation** - Tables, figures, charts fully analyzed and extracted
- **🏥 Medical Literature Focused** - Optimized for clinical trials, systematic reviews, observational studies
- **🔄 Four-Step Pipeline** - Classification → Extraction → Validation → Correction
- **✅ Dual Validation** - Schema validation + LLM semantic validation for quality assurance
- **🤖 Multi-Provider** - Supports both OpenAI (GPT-4o) and Claude (Opus/Sonnet)
- **📐 Schema-Based** - JSON Schema enforcement for structured outputs
- **💾 DOI-Based Storage** - Automatic file naming using publication DOI

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
│  STEP 3: Validation (Dual-Tier)                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 3a. Schema Validation (Fast, Local, Free)             │ │
│  │     • Check structure & types                          │ │
│  │     • Calculate quality score (0.0-1.0)                │ │
│  │     • Completeness analysis                            │ │
│  └────────────────────────────────────────────────────────┘ │
│                            │                                  │
│                 Quality ≥ 50%? ─────No─────→ Skip LLM        │
│                            │                                  │
│                           Yes                                 │
│                            ↓                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 3b. LLM Validation (Slow, Expensive, Thorough)         │ │
│  │     • Upload PDF for comparison                        │ │
│  │     • Semantic accuracy check                          │ │
│  │     • Hallucination detection                          │ │
│  │     • Completeness verification                        │ │
│  │     Output: validation.json                            │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                            │
                    Validation Failed?
                            │
                           Yes
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 4: Correction (Conditional)                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ • Upload PDF with validation report                    │ │
│  │ • Fix identified issues                                │ │
│  │ • Re-extract missing data                              │ │
│  │ • Re-validate corrected output                         │ │
│  │ Output: extraction-corrected.json                      │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 📦 Installation

### Requirements
- Python 3.10+
- OpenAI API key (for GPT-4o) or Anthropic API key (for Claude)

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
OPENAI_MODEL=gpt-4o           # Default: gpt-4o (vision support)
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

### Basic Usage

```bash
# Run with OpenAI (default)
python run_pipeline.py path/to/paper.pdf

# Run with Claude
python run_pipeline.py path/to/paper.pdf --llm-provider claude

# Process only first 10 pages (for testing)
python run_pipeline.py path/to/paper.pdf --max-pages 10

# Keep intermediate files
python run_pipeline.py path/to/paper.pdf --keep-tmp
```

### Command-Line Options

```
usage: run_pipeline.py [-h] [--max-pages MAX_PAGES] [--keep-tmp]
                       [--llm-provider {openai,claude}] pdf

positional arguments:
  pdf                   Path to PDF file

optional arguments:
  -h, --help            Show help message
  --max-pages MAX_PAGES Limit number of pages (for testing)
  --keep-tmp            Keep intermediate files in tmp/
  --llm-provider {openai,claude}
                        Choose LLM provider (default: openai)
```

### Programmatic Usage

```python
from pathlib import Path
from src.llm import get_llm_provider
from src.schemas_loader import load_schema

# Initialize LLM provider
llm = get_llm_provider("openai")  # or "claude"

# Load schema for extraction
schema = load_schema("interventional_trial")

# Extract data from PDF with vision
data = llm.generate_json_with_pdf(
    pdf_path=Path("paper.pdf"),
    schema=schema,
    system_prompt="Extract clinical trial data including all tables and figures",
    max_pages=20  # Optional: limit pages
)

print(f"Extracted {len(data)} fields")
```

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

All outputs are saved in `tmp/` directory with DOI-based naming:

```
tmp/
├── 10-1186-s12871-025-02345-6-classification.json
├── 10-1186-s12871-025-02345-6-extraction.json
├── 10-1186-s12871-025-02345-6-validation.json
├── 10-1186-s12871-025-02345-6-extraction-corrected.json  # If correction needed
└── 10-1186-s12871-025-02345-6-validation-corrected.json  # Final validation
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

## 💰 Cost Considerations

### PDF Upload vs Text Extraction

| Approach | Tokens/Page | Data Quality | Best For |
|----------|-------------|--------------|----------|
| **Text extraction** (old) | ~500 | ❌ Tables lost | Simple documents |
| **PDF upload** (current) | ~1,500-3,000 | ✅ Complete fidelity | Medical research |

### Cost Example (20-page paper)

**OpenAI GPT-4o:**
- Input: 20 pages × 2,000 tokens = 40,000 tokens ($0.20)
- Output: ~4,000 tokens ($0.60)
- **Total per paper: ~$0.80**

**Claude Opus 4.1:**
- Input: 20 pages × 2,000 tokens = 40,000 tokens ($0.60)
- Output: ~4,000 tokens ($2.40)
- **Total per paper: ~$3.00**

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

See `VALIDATION_STRATEGY.md` for detailed explanation.

---

## 🛠️ Development

### Project Structure

```
PDFtoPodcast/
├── run_pipeline.py              # Main entry point
├── requirements.txt             # Dependencies
├── .env                         # Configuration (create from .env.example)
├── src/                         # Core modules
│   ├── config.py                # Settings & configuration
│   ├── llm.py                   # LLM providers (OpenAI, Claude)
│   ├── prompts.py               # Prompt loading
│   ├── schemas_loader.py        # Schema management
│   ├── validation.py            # Validation utilities
│   └── README.md                # Module documentation
├── prompts/                     # Prompt templates
│   ├── Classification.txt       # Step 1 prompt
│   ├── Extraction-prompt-*.txt  # Step 2 prompts (5 types)
│   ├── Extraction-validation.txt# Step 3 prompt
│   ├── Extraction-correction.txt# Step 4 prompt
│   └── README.md                # Prompt guidelines
├── schemas/                     # JSON schemas
│   ├── classification.schema.json
│   ├── validation.schema.json
│   ├── interventional_trial_bundled.json
│   ├── observational_analytic_bundled.json
│   ├── evidence_synthesis_bundled.json
│   ├── prediction_prognosis_bundled.json
│   ├── editorials_opinion_bundled.json
│   └── readme.md                # Schema documentation
├── tmp/                         # Output directory (auto-created)
└── VALIDATION_STRATEGY.md       # Validation design doc
```

### Adding a New Publication Type

1. Create extraction prompt: `prompts/Extraction-prompt-{type}.txt`
2. Create schema: `schemas/{type}.schema.json`
3. Bundle schema: `schemas/{type}_bundled.json`
4. Update `src/schemas_loader.py` SCHEMA_MAPPING
5. Update `src/prompts.py` prompt_mapping
6. Test with sample PDF

### Running Tests

```bash
# Test schema loading
python -c "from src.schemas_loader import load_schema; \
           schema = load_schema('classification'); \
           print('✓ Classification schema loaded')"

# Test LLM connection
python -c "from src.llm import get_llm_provider; \
           llm = get_llm_provider('openai'); \
           print('✓ OpenAI provider initialized')"

# Run on sample PDF
python run_pipeline.py samples/sample_trial.pdf --max-pages 5
```

---

## 🔒 API Limits & Constraints

### OpenAI API Limits
- **Max pages:** 100 per PDF
- **Max file size:** 32 MB
- **Models:** gpt-4o, gpt-4o-mini, o1 (vision-capable models)
- **Format:** Base64-encoded PDF

### Claude API Limits
- **Max pages:** 100 per PDF
- **Max file size:** 32 MB
- **Models:** Claude Opus 4.1, Sonnet 4.5, Haiku 3.5
- **Format:** Base64-encoded PDF with `application/pdf` media type

---

## 📚 Documentation

- **`src/README.md`** - Core module documentation
- **`VALIDATION_STRATEGY.md`** - Dual validation approach
- **`prompts/README.md`** - Prompt engineering guidelines
- **`schemas/readme.md`** - Schema design and bundling

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Update documentation
5. Submit pull request

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
