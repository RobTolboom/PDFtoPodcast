# Prompt Library

This directory stores the large-language-model prompt templates used across the PDFtoPodcast pipeline. Prompts are paired with JSON schemas so that every LLM response can be validated deterministically.

- Loading helpers live in `src/prompts.py` (`load_classification_prompt`, `load_extraction_prompt`, `load_validation_prompt`, `load_correction_prompt`).
- Schemas are bundled under `schemas/` with matching filenames (for example, `interventional_trial_bundled.json` accompanies `Extraction-prompt-interventional.txt`).
- Tests covering prompt integrity reside in `tests/unit/test_prompts.py`.

## Prompt Inventory

| Publication type | Prompt file | Schema file | Typical studies |
|------------------|-------------|-------------|-----------------|
| Classification (all PDFs) | `Classification.txt` | `classification_bundled.json` | Identifies publication type and metadata |
| Interventional trials | `Extraction-prompt-interventional.txt` | `interventional_trial_bundled.json` | Randomised, cluster, crossover trials |
| Observational analytic | `Extraction-prompt-observational.txt` | `observational_analytic_bundled.json` | Cohort, case-control, cross-sectional studies |
| Evidence synthesis | `Extraction-prompt-evidence-synthesis.txt` | `evidence_synthesis_bundled.json` | Systematic reviews, meta-analyses, guideline syntheses |
| Prediction and prognosis | `Extraction-prompt-prediction.txt` | `prediction_prognosis_bundled.json` | Risk prediction, prognostic modelling, ML studies |
| Editorials and opinion | `Extraction-prompt-editorials.txt` | `editorials_opinion_bundled.json` | Editorials, commentaries, expert opinion |
| Validation | `Extraction-validation.txt` | `validation_bundled.json` | Used for semantic quality checks after extraction |
| Correction | `Extraction-correction.txt` | Uses same schema as extraction prompt | Repairs failed extractions using validation feedback |

If classification returns `overig`, no extraction prompt is run; the pipeline exits after metadata capture.

## End-to-End Usage

```python
from pathlib import Path
from src.prompts import (
    load_classification_prompt,
    load_extraction_prompt,
    load_validation_prompt,
    load_correction_prompt,
)
from src.schemas_loader import load_schema

pdf_path = Path("paper.pdf")

# 1. Classification
classification_prompt = load_classification_prompt()
classification_schema = load_schema("classification")

# 2. Type-specific extraction
extraction_prompt = load_extraction_prompt("interventional_trial")
extraction_schema = load_schema("interventional_trial")

# 3. Validation and optional correction
validation_prompt = load_validation_prompt()
correction_prompt = load_correction_prompt()
```

In production the pipeline concatenates these prompts with PDF context and hands them to the selected provider (OpenAI or Claude). Always keep prompts and schemas synchronised so that required fields remain aligned.

## Maintenance Guidelines

1. **Version headers** - Every prompt starts with a version string (for example, "v2 STRICT"). Update the version when you change intent, instructions, or output fields. Reflect the change under "Version History" in this README.
2. **Schema alignment** - Verify that field names, nested structures, and required sections exactly match the companion schema. Use `make test-fast` (or `pytest tests/unit/test_prompts.py`) after edits.
3. **Language consistency** - Prompts are English instructions even when the target PDFs contain international terminology. Preserve the tone and explicit JSON requirements.
4. **Source referencing** - Extraction prompts mandate inline references (page numbers, tables, figures). Do not remove this requirement; validation relies on it.
5. **Cost sensitivity** - Keep prompts concise. Remove redundant prose and prefer bullet lists when adding new guidance.
6. **LLM neutrality** - Avoid provider-specific syntax. The same prompt text is sent to both OpenAI and Claude via the shared abstraction in `src/llm/`.
7. **Testing strategy** - When prompts change, regenerate or adjust fixtures under `tests/fixtures/expected_outputs/` if expected JSON differs. Integration tests (`tests/integration/test_pipeline.py`) should continue to pass with mocked providers.

## Prompt Lifecycle

```
PDF -> Classification prompt -> publication_type, metadata
        |
        +--> Extraction prompt (type-specific) -> extracted JSON
                |
                +--> Validation prompt -> quality report
                        |
                        +--> Correction prompt (optional) -> revised JSON
```

The validation report feeds structured feedback into the correction prompt when thresholds fail. See `VALIDATION_STRATEGY.md` for details on scoring and iteration limits.

## Version History

- **v2.3 (September 2025)** - Prioritised main-text sources over abstracts, strengthened section prompts for completeness.
- **v2.2 (September 2025)** - Added dedicated validation and correction prompt pair, moving to a four-stage pipeline.
- **v2.1 (September 2025)** - Removed Markdown formatting to cut token usage by roughly 20% while preserving instruction clarity.
- **v2.0 (September 2025)** - Introduced type-specific extraction prompts and bundled schemas for five publication categories.
- **v1.x** - Single interventional-only prompt; superseded by v2.0.

## Related Documentation

- `../schemas/readme.md` - Schema definitions and bundling process.
- `../ARCHITECTURE.md` - High-level system design.
- `../src/README.md` - Module overview and public API.
- `../CONTRIBUTING.md` - Contribution expectations, testing requirements.
- `../README.md` - Project introduction and quick start.
