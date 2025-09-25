# Extraction Prompts - Schema-Specific Versions

## Overview

Based on analysis of the 5 bundled JSON schemas, specialized extraction prompts have been created for each study type. The original single prompt was designed only for interventional trials and was incompatible with other schema structures. These optimized prompts provide schema-specific validation rules and are optimized for efficient language model processing.

## 🔗 Schema-Prompt Integration

These extraction prompts are part of a **two-component system** that works together with the JSON schemas:

### Two-Component Framework

| Component | Location | Purpose | Use |
|-----------|----------|---------|-----|
| **Extraction Prompts** | `prompts/` folder (HERE) | Guide LLMs to extract structured data | Feed to language models with PDFs |
| **JSON Schemas** | `schemas/` folder | Define structure and validation rules | Validate extracted JSON output |

### How They Work Together

```mermaid
graph LR
    A[PDF Document] --> B[LLM + Extraction Prompt]
    B --> C[Raw JSON Output]
    C --> D[Schema Validation]
    D --> E[✅ Validated Structured Data]

    F[prompts/] --> B
    G[schemas/] --> D
```

### Critical Integration Points

- **Schema Compatibility**: Each prompt is designed for its corresponding bundled schema
- **Field Alignment**: Prompts enforce exact schema field names and structures
- **Validation Requirements**: Prompts include schema-specific validation rules
- **Output Format**: Prompts ensure JSON output matches schema expectations

**⚠️ Important**: Always use prompts WITH their corresponding schemas. Using prompts alone without validation can result in unreliable data extraction.

### 📁 Project Context

This prompts folder is part of a larger medical literature extraction framework:

```
PDFtoPodcast/
├── prompts/                          # ← YOU ARE HERE
│   ├── Extraction-prompt-interventional.txt    # LLM extraction prompts
│   ├── Extraction-prompt-observational.txt     # (5 specialized prompts)
│   ├── Extraction-prompt-evidence-synthesis.txt
│   ├── Extraction-prompt-prediction.txt
│   ├── Extraction-prompt-editorials.txt
│   └── README.md                               # This guide
│
├── schemas/                          # ← COMPANION FOLDER
│   ├── *_bundled.json              # Production validation schemas
│   ├── *.schema.json              # Development schemas
│   └── README.md                   # Schema documentation & integration guide
│
└── json-bundler.py                  # Tool to create standalone schemas
```

**🔗 For complete integration guidance**: See the comprehensive [`schemas/README.md`](../schemas/README.md) which includes:
- LLM integration patterns and code examples
- Token optimization metrics and best practices
- Production deployment guidelines
- Microservice architecture patterns

## Created Files

### 1. `Extraction-prompt-interventional.txt`
- **Schema**: `interventional_trial_bundled.json`
- **Key Fields**: `arms`, `interventions`, `results.per_arm`, `results.contrasts`
- **Validation**: Focuses on randomization, n_randomised, primary outcomes
- **Use Case**: RCTs, cluster-RCTs, crossover trials, factorial designs

### 2. `Extraction-prompt-observational.txt`
- **Schema**: `observational_analytic_bundled.json`
- **Key Fields**: `exposures`, `groups`, `results.per_group`, `results.contrasts`
- **Validation**: Exposure groups, confounding assessment, causal inference
- **Use Case**: Cohort studies, case-control studies, cross-sectional analyses

### 3. `Extraction-prompt-evidence-synthesis.txt`
- **Schema**: `evidence_synthesis_bundled.json`
- **Key Fields**: `review_type`, `eligibility`, `search`, `prisma_flow`, `syntheses`
- **Validation**: PICO criteria, search strategy, meta-analysis results
- **Use Case**: Systematic reviews, meta-analyses, network meta-analyses, umbrella reviews

### 4. `Extraction-prompt-prediction.txt`
- **Schema**: `prediction_prognosis_bundled.json`
- **Key Fields**: `predictors`, `datasets`, `models`, `performance`
- **Validation**: Model development vs validation, EPV, discrimination metrics
- **Use Case**: Prediction models, prognostic studies, ML/AI algorithms

### 5. `Extraction-prompt-editorials.txt`
- **Schema**: `editorials_opinion_bundled.json`
- **Key Fields**: `article_type`, `stance_overall`, `arguments`
- **Validation**: Argument structure, stakeholder analysis, rhetorical assessment
- **Use Case**: Editorials, commentaries, opinion pieces, letters, perspectives

## Shared Elements

All prompts maintain these common standards:
- **Evidence-locked rules**: Only extract from PDF content, no external knowledge
- **SourceRef requirements**: Precise page/table/figure references with anchor context
- **Vancouver citation**: Consistent bibliographic formatting with source attribution
- **Token fallback**: Graceful handling of large documents with truncation warnings
- **Anesthesiology focus**: Domain-specific details when present (ASA, procedures, PONV, etc.)
- **Schema validation**: Strict adherence to required fields per schema type
- **Plain text format**: Optimized for LLM processing (markdown formatting removed)

## Key Structural Differences

| Schema Type | Primary Structure | Results Format | Special Features |
|-------------|------------------|----------------|------------------|
| Interventional | Arms → Outcomes | per_arm + contrasts | Randomization, harms |
| Observational | Exposures → Groups | per_group + contrasts | Confounding, DAGs |
| Evidence Synthesis | Studies → Syntheses | pooled + per_study | PRISMA, heterogeneity |
| Prediction | Predictors → Models | performance metrics | C-statistic, calibration |
| Editorials | Arguments → Stance | narrative analysis | Rhetorical structure |

## Prompt Optimization

### Language Model Efficiency
All prompts have been optimized for efficient language model processing:

- **Markdown cleanup**: Removed all `**bold**`, `*bullet*` formatting for ~15-25% token reduction
- **Plain text structure**: Clean hierarchical organization with line breaks and numbered lists
- **Code preservation**: Maintained `` `backticks` `` for JSON field names and technical terms
- **Content integrity**: All instructions and validation rules preserved without information loss

### Trade-offs
- **LLM processing**: Optimized for language model efficiency and focus
- **Human readability**: Reduced visual formatting but maintained logical structure
- **Token cost**: Significant reduction in API token usage
- **Maintenance**: Simpler text format for easier updates and version control

## Usage Recommendations

### Study Type Identification
Select the appropriate prompt based on study type identification:
1. **Identify study design** from title/abstract/methods section
2. **Match to schema type** using the structural differences table
3. **Use corresponding prompt** for extraction
4. **Validate output** against the specific bundled schema

### Performance Guidelines
- **Token limits**: Each prompt ~2000-3000 tokens (post-optimization)
- **Fallback handling**: Prompts include truncation warnings for large documents
- **Error handling**: Built-in extraction warnings for ambiguous content
- **Quality assurance**: Schema-specific validation rules prevent common errors

## Implementation Notes

### Schema Compatibility
- **Validation mapping**: Each prompt validated against its corresponding bundled schema
- **Required fields**: Schema-specific required fields enforced (e.g., `arms` for trials, `exposures` for observational)
- **Field constraints**: Type-specific validation (e.g., `n_randomised` only for interventional studies)
- **Output format**: Single valid JSON objects without additional text or explanations

### Methodological Frameworks
- **Interventional**: RoB 2.0, CONSORT, TIDieR guidelines integration
- **Observational**: ROBINS-I, ROBINS-E, STROBE extensions, DAG methodology
- **Evidence Synthesis**: AMSTAR 2, ROBIS, CINeMA, GRADE assessment
- **Prediction**: PROBAST, TRIPOD-AI, CHARMS checklist compliance
- **Editorials**: Rhetorical analysis, stakeholder identification, bias assessment

### Technical Specifications
- **Evidence-locked**: Strict PDF-only extraction, no external knowledge injection
- **SourceRef consistency**: Page, table, figure references with contextual anchors
- **Vancouver citations**: Automated bibliographic string generation with source tracking
- **Error handling**: Structured `extraction_warnings[]` for ambiguous content

## Version History

### v2.1 (Current) - September 2025
- **Markdown cleanup**: Removed formatting for LLM optimization
- **Token reduction**: 15-25% efficiency improvement
- **Content preservation**: All functionality maintained

### v2.0 - September 2025
- **Schema specialization**: Created 5 schema-specific prompts
- **Original assessment**: Single prompt incompatible with 4/5 schemas
- **Validation rules**: Adapted per study type requirements
- **Structural alignment**: Matched prompt structure to schema requirements

### v1.0 - Previous
- **Original prompt**: Single interventional trial focused prompt
- **Limited scope**: Only compatible with interventional_trial schema

## 🚀 Quick Start - Complete Extraction Pipeline

### Essential Two-Step Process
**Step 1**: Extract with prompt → **Step 2**: Validate with schema

### Complete Workflow
```
1. Identify study type from PDF title/abstract
2. Get BOTH components:
   Prompt: Extraction-prompt-[type].txt           (from prompts/ folder)
   Schema: [type]_bundled.json                    (from schemas/ folder)
3. Extract: Use prompt with PDF input in your LLM
4. Validate: ALWAYS validate JSON output against bundled schema
5. ✅ Result: Validated, structured medical literature data
```

### Schema-Prompt Pairs (MUST use together)
| Study Type | Extraction Prompt | Validation Schema | Required |
|------------|-------------------|------------------|----------|
| **RCT/Trial** | `Extraction-prompt-interventional.txt` | `interventional_trial_bundled.json` | ✅ |
| **Cohort/Case-control** | `Extraction-prompt-observational.txt` | `observational_analytic_bundled.json` | ✅ |
| **Meta-analysis/Review** | `Extraction-prompt-evidence-synthesis.txt` | `evidence_synthesis_bundled.json` | ✅ |
| **Prediction model** | `Extraction-prompt-prediction.txt` | `prediction_prognosis_bundled.json` | ✅ |
| **Editorial/Opinion** | `Extraction-prompt-editorials.txt` | `editorials_opinion_bundled.json` | ✅ |

### 💡 Why Both Components Are Required
- **Prompt alone**: Can extract data, but no guarantee of structure or completeness
- **Schema alone**: Can validate structure, but can't extract from PDFs
- **Together**: Reliable, validated, structured extraction pipeline

### 💻 Integration Examples

#### Python Example: Complete Extraction Pipeline
```python
import json
import jsonschema

# 1. Load both prompt and schema
prompt = open('prompts/Extraction-prompt-interventional.txt').read()
schema = json.load(open('schemas/interventional_trial_bundled.json'))

# 2. Extract with LLM (your_llm_function)
pdf_text = extract_text_from_pdf('study.pdf')
llm_input = prompt + "\n\n" + pdf_text
json_output = your_llm.generate(llm_input)

# 3. Parse and validate
try:
    extracted_data = json.loads(json_output)
    jsonschema.validate(extracted_data, schema)
    print("✅ Extraction successful and validated!")
    return extracted_data
except (json.JSONDecodeError, jsonschema.ValidationError) as e:
    print(f"❌ Error: {e}")
```

#### Batch Processing Example
```python
def process_literature_batch(pdf_files, study_type):
    # Schema-prompt mapping
    pairs = {
        'interventional': ('Extraction-prompt-interventional.txt',
                          'interventional_trial_bundled.json'),
        'observational': ('Extraction-prompt-observational.txt',
                         'observational_analytic_bundled.json'),
        'synthesis': ('Extraction-prompt-evidence-synthesis.txt',
                     'evidence_synthesis_bundled.json')
    }

    prompt_file, schema_file = pairs[study_type]
    prompt = open(f'prompts/{prompt_file}').read()
    schema = json.load(open(f'schemas/{schema_file}'))

    results = []
    for pdf_file in pdf_files:
        # Extract and validate each PDF
        data = extract_and_validate(pdf_file, prompt, schema)
        results.append(data)

    return results
```

### Integration Tips
- **API efficiency**: Use optimized prompts to reduce token costs
- **Schema validation**: ALWAYS validate against bundled schemas - this catches 80%+ of extraction errors
- **Error handling**: Check `extraction_warnings[]` in output for data quality issues
- **Prompt-schema pairing**: Never mix prompts and schemas from different study types
- **Fallback**: Handle `truncated: true` cases for large documents

### 🔗 Advanced Integration
For comprehensive integration patterns including microservice architectures, token optimization strategies, and production deployment guides, see the [`schemas/README.md`](../schemas/README.md) which provides detailed LLM integration documentation.

## Troubleshooting

### Common Issues
- **Schema validation errors**: Ensure using correct prompt for study type
- **Missing required fields**: Check PDF contains necessary information sections
- **Token limits**: Use fallback handling for large documents
- **Extraction warnings**: Review PDF quality and completeness

### Output Quality
- **SourceRef precision**: Verify page/table/figure references are accurate
- **Vancouver citations**: Ensure bibliographic information extracted correctly
- **Field mapping**: Confirm schema field names match prompt expectations
