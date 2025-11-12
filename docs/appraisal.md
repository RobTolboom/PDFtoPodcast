# Critical Appraisal Guide

This document summarizes how the appraisal stage behaves, how to operate it via CLI/Streamlit, and what files/tests/data are available.

## Study-type routing & tools

| Classification            | Tool(s) used                     | Prompt                                  |
|--------------------------|----------------------------------|-----------------------------------------|
| `interventional_trial`   | RoB 2 + GRADE                    | `prompts/Appraisal-interventional.txt`  |
| `observational_analytic` | ROBINS-I + GRADE                 | `prompts/Appraisal-observational.txt`   |
| `evidence_synthesis`     | AMSTAR 2 + ROBIS + GRADE         | `prompts/Appraisal-evidence-synthesis.txt` |
| `prediction_prognosis`   | PROBAST                          | `prompts/Appraisal-prediction.txt`      |
| `diagnostic`             | PROBAST (diagnostic variant)     | `prompts/Appraisal-prediction.txt`      |
| `editorials_opinion`     | Argument quality & transparency  | `prompts/Appraisal-editorials.txt`      |

Validation/correction prompts live in `prompts/Appraisal-validation.txt` and `prompts/Appraisal-correction.txt`. Both emit structured JSON validated against `schemas/appraisal_validation.schema.json` / `schemas/appraisal.schema.json`.

## CLI usage

```bash
# Run entire pipeline (classification → extraction → validation_correction → appraisal)
python run_pipeline.py data/paper.pdf --llm openai

# Appraisal only, with custom thresholds / iterations
python run_pipeline.py data/paper.pdf \
    --step appraisal \
    --appraisal-max-iter 5 \
    --appraisal-logical-threshold 0.92 \
    --appraisal-completeness-threshold 0.88

# Legacy single-pass mode (no iterative correction, writes paper-appraisal.json)
python run_pipeline.py data/paper.pdf --step appraisal --appraisal-single-pass
```

CLI output highlights:
- Final status (`passed`, `max_iterations_reached`, `early_stopped_degradation`, …)
- Iteration count & best iteration number
- Risk of bias summary (tool + overall judgement)
- GRADE per-outcome counts

## Streamlit usage

1. Open the UI (`streamlit run app.py`) and upload/select a PDF.
2. In **Settings**:
   - Ensure “Appraisal” is included in `steps_to_run`.
   - Configure threshold sliders (logical/completeness/evidence/schema) and max iterations.
   - Toggle “Enable iterative appraisal correction” on/off for iterative vs single-pass mode.
3. In the **Execution** screen:
   - A fourth status card (“Appraisal”) appears after Validation & Correction.
   - Result section shows risk-of-bias summary, GRADE snippet, applicability notes, iteration history (table + quality trajectory chart) and the podcast bottom line.
   - Use the **🔁 Re-run appraisal** button to redo only the appraisal step without restarting earlier pipeline stages.

## File outputs

| File                                  | Description                                         |
|---------------------------------------|-----------------------------------------------------|
| `tmp/{id}-appraisal{n}.json`          | Appraisal iteration N                               |
| `tmp/{id}-appraisal_validation{n}.json` | Validation report for iteration N                 |
| `tmp/{id}-appraisal-best.json`        | Highest-quality appraisal (iterative mode)          |
| `tmp/{id}-appraisal_validation-best.json` | Validation of best iteration                    |
| `tmp/{id}-appraisal.json`             | Legacy single-pass appraisal (if enabled)           |
| `tmp/{id}-appraisal_validation.json`  | Legacy single-pass validation (if enabled)          |

## Tests & sample data

- **Unit tests**: `tests/unit/test_appraisal_quality.py` and `tests/unit/test_appraisal_functions.py` cover routing, threshold logic, metric extraction, best-iteration selection, and the single-pass toggle.
- **Integration tests**: `tests/integration/test_appraisal_full_loop.py` mocks all five study types and exercises the full appraisal → validation → correction loop with file persistence.
- **Fixtures**: Sample appraisal/extraction payloads live inside the integration test module (see fixtures named `mock_extraction_*`, `mock_appraisal_response`, etc.) and can be reused for manual verification.

For the full specification (prompt instructions, scoring weights, acceptance criteria), see `features/appraisal.md`.
