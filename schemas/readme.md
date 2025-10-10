# Medical Literature Extraction Schemas

> **📖 For system architecture and pipeline details, see [ARCHITECTURE.md](../ARCHITECTURE.md)**

JSON Schema collection for structured data extraction from medical research PDFs. These schemas support all major research methodologies with full compliance to international reporting guidelines.

---

## 🚀 Quick Start

### Which Schema for Which Study?

| Study Type | Schema File | Standards | Use For |
|------------|-------------|-----------|---------|
| **RCT/Clinical Trial** | `interventional_trial_bundled.json` | CONSORT 2010, ICH-GCP | Randomized controlled trials |
| **Cohort/Case-Control** | `observational_analytic_bundled.json` | STROBE, ROBINS-I | Observational studies |
| **Meta-analysis/Review** | `evidence_synthesis_bundled.json` | PRISMA 2020, AMSTAR-2 | Systematic reviews |
| **Prediction Model** | `prediction_prognosis_bundled.json` | TRIPOD, PROBAST | Risk prediction models |
| **Editorial/Opinion** | `editorials_opinion_bundled.json` | N/A | Commentaries, editorials |

### Basic Validation

```python
import json
import jsonschema

# Load schema
schema = json.load(open('interventional_trial_bundled.json'))

# Load extracted data
data = json.load(open('extraction.json'))

# Validate
try:
    jsonschema.validate(data, schema)
    print("✅ Valid!")
except jsonschema.ValidationError as e:
    print(f"❌ Invalid: {e.message}")
```

---

## 📋 Schema Overview

### Two Schema Variants

| Variant | Files | Use Case | Pros | Cons |
|---------|-------|----------|------|------|
| **Modular** | `*.schema.json` + `common.schema.json` | Development, testing | Easy to maintain, reusable components | Requires external refs |
| **Bundled** | `*_bundled.json` | Production, APIs | Self-contained, no dependencies | Larger files |

**Recommendation:**
- **Development**: Use modular schemas
- **Production**: Use bundled schemas (faster, no dependencies)

---

## 📐 Schema Types

### 1. Interventional Trial Schema

**File**: `interventional_trial_bundled.json`

**For**: RCTs, cluster-RCTs, crossover trials, before-after studies

**Key Sections:**
- `arms[]` - Study arms/groups
- `interventions[]` - Treatments/interventions
- `outcomes[]` - Primary and secondary outcomes
- `results.per_arm[]` - Arm-specific results
- `results.contrasts[]` - Between-group comparisons

**Standards Compliance:**
- CONSORT 2010 - Complete reporting checklist
- ICH-GCP - Good Clinical Practice alignment
- RoB 2.0 - Cochrane Risk of Bias tool

**Key Features:**
- Randomization details
- CONSORT flow tracking
- Protocol deviations
- Adverse events (CTCAE v5.0)
- Sensitivity analyses

---

### 2. Observational Analytic Schema

**File**: `observational_analytic_bundled.json`

**For**: Cohort studies, case-control studies, cross-sectional analyses

**Key Sections:**
- `exposures[]` - Exposure variables
- `groups[]` - Exposure/comparison groups
- `outcomes[]` - Measured outcomes
- `results.per_group[]` - Group-specific results
- `results.contrasts[]` - Between-group comparisons

**Standards Compliance:**
- STROBE - Observational study reporting
- ROBINS-I - Risk of bias assessment
- GRADE - Evidence certainty

**Key Features:**
- Target trial emulation framework
- New user design support
- Propensity score methods
- Competing risks handling
- Causal inference (DAGs)

---

### 3. Evidence Synthesis Schema

**File**: `evidence_synthesis_bundled.json`

**For**: Systematic reviews, meta-analyses, network meta-analyses

**Key Sections:**
- `review_type` - Type of synthesis
- `eligibility` - PICO criteria
- `search` - Search strategy
- `prisma_flow` - Study selection flow
- `syntheses[]` - Meta-analysis results

**Standards Compliance:**
- PRISMA 2020 - Complete checklist
- AMSTAR-2 - Quality assessment
- GRADE - Evidence certainty
- Cochrane standards

**Key Features:**
- PRISMA flow diagram
- Search strategy documentation
- Meta-analysis results (I², τ²)
- Subgroup analyses
- Publication bias assessment
- GRADE evidence profiles

---

### 4. Prediction/Prognosis Schema

**File**: `prediction_prognosis_bundled.json`

**For**: Prediction models, prognostic studies, ML/AI algorithms

**Key Sections:**
- `predictors[]` - Model variables
- `datasets[]` - Development/validation cohorts
- `models[]` - Model specifications
- `performance[]` - Discrimination & calibration

**Standards Compliance:**
- TRIPOD - Prediction model reporting
- PROBAST - Risk of bias assessment
- TRIPOD-AI - AI/ML extensions

**Key Features:**
- Model development & validation
- C-statistic, AUC-ROC
- Calibration curves
- Clinical utility assessment
- EPV (events per variable)

---

### 5. Editorial/Opinion Schema

**File**: `editorials_opinion_bundled.json`

**For**: Editorials, commentaries, opinion pieces, letters

**Key Sections:**
- `article_type` - Editorial type classification
- `target_article` - Referenced article (if applicable)
- `arguments[]` - Pro/con arguments
- `stance_overall` - Overall position

**Key Features:**
- Argument tracking
- Evidence linking to external studies
- Stakeholder analysis
- Rhetorical assessment
- Citation metadata

---

## 🔄 Schema Deployment

### Modular Schemas (Development)

**Structure:**
```
schemas/
├── common.schema.json              # Shared components
├── interventional_trial.schema.json
├── observational_analytic.schema.json
├── evidence_synthesis.schema.json
├── prediction_prognosis.schema.json
└── editorials_opinion.schema.json
```

**Example:**
```json
{
  "metadata": { "$ref": "common.schema.json#/$defs/Metadata" },
  "risk_of_bias": { "$ref": "common.schema.json#/$defs/RiskOfBias" }
}
```

**Pros:**
- Reusable components
- Easy maintenance
- Smaller file sizes
- Consistent definitions

**Cons:**
- Requires external file resolution
- Not suitable for CDN/API deployment

---

### Bundled Schemas (Production)

**Generate bundled schemas:**
```bash
python json-bundler.py
```

**Output:**
```
schemas/
├── interventional_trial_bundled.json
├── observational_analytic_bundled.json
├── evidence_synthesis_bundled.json
├── prediction_prognosis_bundled.json
└── editorials_opinion_bundled.json
```

**Pros:**
- Self-contained (no external refs)
- Fast loading
- CDN/API compatible
- Microservice ready

**Cons:**
- Larger file sizes
- Must regenerate after modular changes

---

## 💻 Usage Examples

### Validation

```python
import json
import jsonschema

# Load schema
schema = json.load(open('interventional_trial_bundled.json'))

# Validate extraction
data = json.load(open('extraction.json'))

try:
    jsonschema.validate(data, schema)
    print("✅ Valid")
except jsonschema.ValidationError as e:
    print(f"❌ Error: {e.message}")
    print(f"   Path: {'/'.join(str(p) for p in e.path)}")
```

### Integration with LLM

```python
from src.llm import get_llm_provider
from src.schemas_loader import load_schema

# Get LLM provider
llm = get_llm_provider("openai")

# Load schema
schema = load_schema("interventional_trial")

# Extract with schema enforcement
data = llm.generate_json_with_pdf(
    pdf_path="paper.pdf",
    schema=schema,
    system_prompt=extraction_prompt,
    max_pages=20
)

# Data is already validated by LLM
print(f"Extracted {len(data['arms'])} study arms")
```

### Batch Processing

```python
def validate_batch(extraction_files, study_type):
    """Validate multiple extractions."""
    schema = load_schema(study_type)
    results = []

    for file in extraction_files:
        data = json.load(open(file))
        try:
            jsonschema.validate(data, schema)
            results.append(("✅", file))
        except jsonschema.ValidationError as e:
            results.append(("❌", file, e.message))

    return results
```

---

## 🛠️ json-bundler.py Tool

### Purpose
Generate self-contained bundled schemas from modular schemas.

### Usage

```bash
# Bundle all schemas
python json-bundler.py

# Specify directory
python json-bundler.py --directory /path/to/schemas
```

### Output

```
Using common schema ID: common.schema.json
Found 5 schema(s) to bundle:
  - interventional_trial.schema.json
  - observational_analytic.schema.json
  - evidence_synthesis.schema.json
  - prediction_prognosis.schema.json
  - editorials_opinion.schema.json

Processing interventional_trial.schema.json...
  ✅ Created: interventional_trial_bundled.json

🎉 Successfully bundled 5/5 schemas
```

### How It Works

1. Reads modular schema
2. Finds all `$ref` to `common.schema.json`
3. Inlines referenced definitions
4. Rewrites refs to local `#/$defs/...`
5. Outputs self-contained schema

---

## 🌍 International Standards

All schemas comply with international reporting guidelines:

| Domain | Guidelines Supported |
|--------|---------------------|
| **Clinical Trials** | CONSORT 2010, ICH-GCP, FDA/EMA requirements |
| **Observational** | STROBE, ROBINS-I, ROBINS-E |
| **Reviews** | PRISMA 2020, AMSTAR-2, Cochrane standards |
| **Prediction** | TRIPOD, TRIPOD-AI, PROBAST |
| **Quality Assessment** | RoB 2.0, ROBINS-I, PROBAST, AMSTAR-2, GRADE |

### Registry Support

All schemas support international trial registries:

- ClinicalTrials.gov (US)
- EudraCT/EU-CTR/CTIS (EU)
- UMIN-CTR/JPRN (Japan)
- PACTR (Africa)
- IRCT (Iran)
- ANZCTR (Australia/NZ)

---

## 🔧 Troubleshooting

### Common Issues

**Schema validation fails**
- Check correct schema for study type
- Verify JSON syntax
- Check required fields are present

**Bundling fails**
- Verify `common.schema.json` exists
- Check JSON syntax in modular schemas
- Ensure valid `$ref` syntax

**External refs not resolving**
- Use bundled schemas for production
- Check file paths are correct
- Verify schema files are accessible

**Performance issues**
- Use bundled schemas (faster loading)
- Cache parsed schemas in memory
- Validate incrementally for large datasets

---

## 📚 Version History

### v2.0 - September 2025
- 5 specialized schemas (one per study type)
- Bundled production schemas
- Modular architecture with shared components
- JSON Schema 2020-12 compliance
- International standards alignment

### v1.0 - Previous
- Single schema for interventional trials
- Limited study type support

---

## 🔗 Related Documentation

- **[../prompts/README.md](../prompts/README.md)** - Prompt engineering and schema-prompt integration
- **[../ARCHITECTURE.md](../ARCHITECTURE.md)** - System architecture and design decisions
- **[../src/README.md](../src/README.md)** - Module API documentation
- **[../CONTRIBUTING.md](../CONTRIBUTING.md)** - Development guidelines
- **[../README.md](../README.md)** - Project overview

---

**For detailed compliance information, international standards, and advanced usage patterns, see [ARCHITECTURE.md](../ARCHITECTURE.md)**
