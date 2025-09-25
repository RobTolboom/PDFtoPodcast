# Extraction Prompts - Schema-Specific Versions

## Overview

Based on the 5 bundled JSON schemas, extraction prompts have been created for each type of publication.

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
- **Evidence-locked rules**: Only extract from PDF content
- **SourceRef requirements**: Precise page/table/figure references
- **Vancouver citation**: Consistent bibliographic formatting
- **Token fallback**: Graceful handling of large documents
- **Anesthesiology focus**: Domain-specific details when present

## Key Structural Differences

| Schema Type | Primary Structure | Results Format | Special Features |
|-------------|------------------|----------------|------------------|
| Interventional | Arms → Outcomes | per_arm + contrasts | Randomization, harms |
| Observational | Exposures → Groups | per_group + contrasts | Confounding, DAGs |
| Evidence Synthesis | Studies → Syntheses | pooled + per_study | PRISMA, heterogeneity |
| Prediction | Predictors → Models | performance metrics | C-statistic, calibration |
| Editorials | Arguments → Stance | narrative analysis | Rhetorical structure |

## Usage Recommendation

Select the appropriate prompt based on study type identification:
1. **Identify study design** from title/abstract/methods
2. **Match to schema type** using the table above
3. **Use corresponding prompt** for extraction
4. **Validate output** against the specific bundled schema

## Implementation Notes

- Each prompt has been validated against its corresponding schema's required fields
- Validation rules are adapted per study type (e.g., n_randomised only for trials)
- Domain expertise requirements vary (e.g., PROBAST for prediction, AMSTAR for synthesis)
- All prompts produce single valid JSON objects without additional text
