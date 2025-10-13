# Extraction Prompts - Medical Literature Data Extraction

> **📖 For system architecture and design decisions, see [ARCHITECTURE.md](../ARCHITECTURE.md)**

This directory contains LLM prompts for extracting structured data from medical research PDFs. Each prompt is optimized for a specific publication type and works together with its corresponding JSON schema.

---

## 🚀 Quick Start

### Which Prompt for Which Study?

| Study Type | Prompt File | Schema File | Use For |
|------------|-------------|-------------|---------|
| **RCT/Clinical Trial** | `Extraction-prompt-interventional.txt` | `interventional_trial_bundled.json` | Randomized trials, clinical studies |
| **Cohort/Case-Control** | `Extraction-prompt-observational.txt` | `observational_analytic_bundled.json` | Observational studies |
| **Meta-analysis/Review** | `Extraction-prompt-evidence-synthesis.txt` | `evidence_synthesis_bundled.json` | Systematic reviews |
| **Prediction Model** | `Extraction-prompt-prediction.txt` | `prediction_prognosis_bundled.json` | Risk models, prognostic studies |
| **Editorial/Opinion** | `Extraction-prompt-editorials.txt` | `editorials_opinion_bundled.json` | Commentaries, editorials |

### Basic Usage

```python
# 1. Load prompt and schema
prompt = open('prompts/Extraction-prompt-interventional.txt').read()
schema = json.load(open('schemas/interventional_trial_bundled.json'))

# 2. Extract with LLM
result = llm.generate(prompt + "\n\n" + pdf_text)

# 3. Validate
jsonschema.validate(json.loads(result), schema)
```

---

## 📋 Prompt System Overview

### Complete Four-Component Framework

This extraction system consists of **four prompt types** that work together:

| Component | File | Purpose | When Used |
|-----------|------|---------|-----------|
| **Classification** | `Classification.txt` | Identify publication type & extract metadata | First step (always) |
| **Extraction** | `Extraction-prompt-{type}.txt` | Extract structured data from PDF | After classification |
| **Validation** | `Extraction-validation.txt` | Verify accuracy and completeness | After extraction |
| **Correction** | `Extraction-correction.txt` | Fix identified issues | Only if validation fails |

### Pipeline Flow

```
PDF → Classification Prompt → Type Identified
                                     ↓
                      Select Extraction Prompt + Schema
                                     ↓
                      Extraction Prompt → Structured JSON
                                     ↓
                      Validation Prompt → Quality Report
                                     ↓
                      (if failed) → Correction Prompt
```

---

## 📝 Prompt Types

### 1. Classification (`Classification.txt`)

**Purpose**: Pre-processing step to identify publication type and extract metadata.

**Output**: Publication type selection + metadata (authors, DOI, journal, etc.)

**Six Publication Categories:**
1. `interventional_trial` - RCTs, clinical trials
2. `observational_analytic` - Cohort, case-control studies
3. `evidence_synthesis` - Systematic reviews, meta-analyses
4. `prediction_prognosis` - Prediction models, ML algorithms
5. `editorials_opinion` - Editorials, commentaries
6. `overig` - Case reports, guidelines (no extraction prompt available)

**Key Features:**
- Automated metadata extraction (title, authors, DOI, PMID)
- Confidence scoring (0.0-1.0)
- Vancouver citation formatting
- Early publication handling
- Anesthesiology domain specialization

---

### 2. Extraction Prompts (5 Type-Specific)

Each extraction prompt is tailored to its publication type's unique data structure.

#### `Extraction-prompt-interventional.txt`
- **For**: RCTs, cluster-RCTs, crossover trials
- **Key Fields**: `arms`, `interventions`, `results.per_arm`, `results.contrasts`
- **Standards**: CONSORT 2010, TIDieR, RoB 2.0
- **Focus**: Randomization, sample sizes, primary outcomes

#### `Extraction-prompt-observational.txt`
- **For**: Cohort studies, case-control studies
- **Key Fields**: `exposures`, `groups`, `results.per_group`, `results.contrasts`
- **Standards**: STROBE, ROBINS-I
- **Focus**: Exposure groups, confounding, causal inference

#### `Extraction-prompt-evidence-synthesis.txt`
- **For**: Systematic reviews, meta-analyses
- **Key Fields**: `review_type`, `eligibility`, `search`, `prisma_flow`, `syntheses`
- **Standards**: PRISMA 2020, AMSTAR-2, GRADE
- **Focus**: Search strategy, PRISMA flow, meta-analysis results

#### `Extraction-prompt-prediction.txt`
- **For**: Prediction models, prognostic studies
- **Key Fields**: `predictors`, `datasets`, `models`, `performance`
- **Standards**: TRIPOD, PROBAST
- **Focus**: Model development, validation, performance metrics

#### `Extraction-prompt-editorials.txt`
- **For**: Editorials, commentaries, opinion pieces
- **Key Fields**: `article_type`, `stance_overall`, `arguments`
- **Focus**: Argument structure, evidence linking, rhetorical analysis

---

### 3. Validation (`Extraction-validation.txt`)

**Purpose**: Universal quality assurance for all extraction types.

**Key Features:**
- Hallucination detection
- Completeness scoring
- Accuracy verification
- Structured quality report

**Output Format:**
```json
{
  "verification_summary": {
    "overall_status": "passed|warning|failed",
    "completeness_score": 0.95,
    "accuracy_score": 0.98
  },
  "issues": [...],
  "recommendations": [...]
}
```

---

### 4. Correction (`Extraction-correction.txt`)

**Purpose**: Fix issues identified by validation prompt.

**When Used**: Only when validation fails or returns warnings.

**Process:**
1. Takes original extraction + validation report
2. Re-extracts missing data
3. Fixes identified inaccuracies
4. Re-validates corrected output

---

## 💻 Integration Examples

### Complete Pipeline Example

```python
import json
import jsonschema
from pathlib import Path

# Step 1: Classify
classification_prompt = open('prompts/Classification.txt').read()
classification = llm.generate(classification_prompt + "\n\n" + pdf_text)
pub_type = json.loads(classification)['publication_type']

# Step 2: Select appropriate extraction prompt and schema
prompt_map = {
    'interventional_trial': ('Extraction-prompt-interventional.txt',
                            'interventional_trial_bundled.json'),
    'observational_analytic': ('Extraction-prompt-observational.txt',
                               'observational_analytic_bundled.json'),
    # ... other types
}

if pub_type == 'overig':
    print("No extraction prompt for 'overig' type")
    exit()

prompt_file, schema_file = prompt_map[pub_type]
extraction_prompt = open(f'prompts/{prompt_file}').read()
schema = json.load(open(f'schemas/{schema_file}'))

# Step 3: Extract
extraction = llm.generate(extraction_prompt + "\n\n" + pdf_text)
extracted_data = json.loads(extraction)

# Step 4: Validate against schema
try:
    jsonschema.validate(extracted_data, schema)
    print("✅ Schema validation passed")
except jsonschema.ValidationError as e:
    print(f"❌ Schema validation failed: {e.message}")
    exit()

# Step 5: LLM validation (optional but recommended)
validation_prompt = open('prompts/Extraction-validation.txt').read()
validation_input = f"""
EXTRACTED_JSON: {json.dumps(extracted_data, indent=2)}
PDF_CONTENT: {pdf_text}
SCHEMA: {json.dumps(schema, indent=2)}
"""
quality_report = llm.generate(validation_prompt + "\n\n" + validation_input)
quality = json.loads(quality_report)

if quality['verification_summary']['overall_status'] == 'passed':
    print("✅ Quality verification passed")
else:
    print("⚠️ Quality verification has issues")
    # Optionally: run correction step
```

### Batch Processing Example

```python
def process_literature_batch(pdf_files):
    """Process multiple PDFs with appropriate prompts."""
    results = []

    for pdf_file in pdf_files:
        # Classify
        pub_type = classify_pdf(pdf_file)

        if pub_type == 'overig':
            continue

        # Extract with appropriate prompt
        extracted = extract_with_prompt(pdf_file, pub_type)

        # Validate
        if validate_extraction(extracted, pub_type):
            results.append(extracted)

    return results
```

---

## 🎯 Prompt Design Principles

### 1. Evidence-Locked Extraction
- **Only extract from PDF content** - No external knowledge
- **Main text priority** - Methods/Results/Discussion over Abstract
- **Source references required** - Page, table, figure citations

### 2. Data Source Prioritization (v2.3)
All prompts prioritize main text over abstracts:

**Priority Order:**
1. Results sections - Primary source for numerical data
2. Methods sections - Complete methodology
3. Discussion sections - Context, limitations
4. Tables/Figures - Detailed results
5. Abstract - Only for verification

### 3. Schema Alignment
- Each prompt matches its corresponding schema structure
- Field names identical between prompt and schema
- Validation rules embedded in prompts

### 4. Token Optimization (v2.1)
- Markdown formatting removed for 15-25% token reduction
- Plain text structure maintained
- All instructions preserved

---

## 🔧 Troubleshooting

### Common Issues

**Problem**: Schema validation fails
- **Solution**: Ensure using correct prompt for study type
- **Check**: Prompt-schema pairing is correct

**Problem**: Low completeness scores
- **Solution**: Verify PDF has full Methods/Results sections (not just abstract)
- **Check**: PDF quality and OCR accuracy

**Problem**: Missing required fields
- **Solution**: Check if PDF contains necessary information
- **Check**: Prompt is extracting from main text, not just abstract

**Problem**: Extraction warnings
- **Solution**: Review PDF quality and completeness
- **Check**: Parsing warnings in validation output

---

## 📚 Version History

### v2.3 (Current) - September 2025
- **Data Source Prioritization** - Main text priority over abstract
- **Completeness improvements** - Systematic section extraction
- **Section-specific instructions** - Methods/Results/Tables priority

### v2.2 - September 2025
- **Quality assurance** - Added Extraction-validation.txt
- **Correction prompt** - Added Extraction-correction.txt
- **Three-component system** → Four-component system

### v2.1 - September 2025
- **Token optimization** - Removed markdown formatting
- **15-25% efficiency** - Reduced API costs
- **Content preservation** - All functionality maintained

### v2.0 - September 2025
- **Schema specialization** - Created 5 type-specific prompts
- **Structural alignment** - Matched schema requirements
- **Validation rules** - Type-specific validation

### v1.0 - Previous
- **Single prompt** - Interventional trial focus only
- **Limited scope** - Not compatible with other types

---

## 🔗 Related Documentation

- **[../schemas/readme.md](../schemas/readme.md)** - Schema design and LLM integration
- **[../ARCHITECTURE.md](../ARCHITECTURE.md)** - System architecture
- **[../src/README.md](../src/README.md)** - Module API documentation
- **[../CONTRIBUTING.md](../CONTRIBUTING.md)** - Development guidelines
- **[../README.md](../README.md)** - Project overview
