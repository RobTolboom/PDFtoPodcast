# Validation Strategy: Dual Validation Approach

## Overview

The PDFtoPodcast extraction pipeline uses **both** schema validation and LLM validation in a complementary, two-tier approach.

## Why Both?

### Schema Validation (validation.py)
Strengths:
- Fast - milliseconds, no API calls
- Free - no LLM costs
- Precise - catches structural errors with certainty
- Actionable - clear error messages

Limitations:
- Cannot verify semantic correctness
- Cannot check against source PDF
- No domain knowledge

### LLM Validation (Extraction-validation.txt)
Strengths:
- Smart - understands context and meaning
- Source-aware - compares extraction to PDF
- Domain-aware - spots medically implausible values

Limitations:
- Slow - 30-60+ seconds per validation
- Expensive - API costs for large prompts
- Non-deterministic - may vary slightly

## Implementation

### Step 3a: Schema Validation (Always runs)
```python
schema_validation = validate_extraction_quality(data, schema)
quality_score = schema_validation['quality_score']  # 0.0 - 1.0
```

What it checks:
- JSON structure matches schema
- All required fields present
- Correct data types
- Enum values valid
- Format constraints (patterns, ranges)
- Completeness (required vs optional fields)

Output:
- quality_score: 0.0-1.0 (50% schema compliance + 50% completeness)
- validation_errors: List of specific errors
- completeness: Field coverage statistics

### Step 3b: LLM Validation (Conditional - only if quality_score >= 0.5)
```python
if quality_score >= SCHEMA_QUALITY_THRESHOLD:
    llm_validation = llm.generate_json(
        prompt=pdf_text + extraction + schema_results,
        system_prompt=validation_prompt
    )
```

What it checks:
- Does extracted data match PDF content?
- Are values medically plausible?
- Are there contradictions or inconsistencies?
- Is important information missing?
- Are relationships between fields logical?

Output:
- verification_summary: Overall pass/fail status
- quality_assessment: Narrative description
- recommendations: Specific improvements needed

### Combined Result
```json
{
  "schema_validation": { /* schema results */ },
  "verification_summary": {
    "overall_status": "passed|failed",
    "schema_compliance": 0.85,
    "completeness_score": 0.92,
    "accuracy_score": 0.88
  },
  "validation_errors": [...],
  "quality_assessment": "...",
  "recommendations": [...]
}
```

## Quality Metrics

| Metric                    | Source                           | Purpose                                                       |
|---------------------------|----------------------------------|---------------------------------------------------------------|
| `quality_score`           | `validate_extraction_quality`   | Weighted blend (50% schema compliance, 50% completeness)      |
| `schema_compliance`       | Schema validation output        | Fraction of required constraints satisfied                    |
| `completeness_score`      | Schema validation output        | Coverage of optional and required fields                      |
| `accuracy_score`          | LLM verification summary        | Semantic correctness compared to the source PDF               |
| `critical_issues`         | LLM verification summary        | Count of blocking issues; any value > 0 fails thresholds      |
| `overall_quality`         | Iteration metadata              | Composite score used when picking the best iteration          |

Default quality thresholds (from `EXTRACTION_THRESHOLDS` in `src/pipeline/quality/thresholds.py`):

- Completeness score >= 0.90
- Accuracy score >= 0.95
- Schema compliance score >= 0.95
- Critical issues = 0

## Decision Logic

```
Extraction
    v
Schema Validation
    v
quality_score < 50%? ---> Skip LLM ---> Correction (schema errors)
    v
quality_score >= 50%
    v
LLM Validation
    v
Both passed? ---> Done
    v
Issues found? ---> Correction (combined feedback)
```

## Benefits

1. Efficiency: Schema validation filters out broken extractions (saves ~$0.10-0.50 per failed extraction)
2. Quality: LLM catches subtle errors schema can't detect
3. Cost-Effective: Only pay for LLM when extraction has decent structure
4. Fast Feedback: Schema errors identified in <100ms
5. Comprehensive: Structural + semantic validation
6. Fail-Fast: Bad extractions caught early

## Configuration

```python
# run_pipeline.py / src/config.py
SCHEMA_QUALITY_THRESHOLD = 0.5  # 50%
```

Tuning the threshold:
- Higher (0.7-0.9): More strict, fewer LLM calls, lower cost, may miss fixable extractions
- Lower (0.3-0.4): More lenient, more LLM calls, higher cost, more thorough validation
- Default (0.5): Balanced approach

## Iterative Loop and Termination

The correction cycle lives in `run_validation_with_correction` (`src/pipeline/steps/validation.py`) and is implemented with the shared `IterativeLoopRunner`. It runs after an extraction fails the quality thresholds.

1. Run validation (schema + conditional LLM) against the current extraction.
2. Compare scores to `EXTRACTION_THRESHOLDS`.
3. If thresholds are missed and `iteration_num < max_iterations`, call the correction prompt (`prompts/Extraction-correction.txt`) to produce a new extraction, then loop.
4. Stop early when quality degrades over consecutive iterations, schema quality drops below the 0.5 threshold, or LLM calls fail repeatedly.
5. Persist results for every pass (`extraction{N}.json`, `validation{N}.json`), record quality metrics, and pick the best-scoring iteration before returning.

`max_iterations` (default: 3 corrections, yielding up to four total passes) is configurable through `--max-iterations` on the CLI or the Streamlit sliders. Early stopping on quality degradation and schema quality < 0.5 is enforced inside `IterativeLoopRunner`.

## Output Artefacts

`PipelineFileManager` (`src/pipeline/file_manager.py`) saves files in `tmp/` using the PDF stem as a prefix:

```
tmp/
  paper-extraction0.json        # Initial extraction
  paper-validation0.json        # Validation of initial extraction
  paper-extraction1.json        # First correction (if run)
  paper-validation1.json        # Validation after correction 1
  paper-extraction-best.json    # Highest-quality extraction
  paper-validation-best.json    # Validation paired with best extraction
  paper-extraction-best-metadata.json  # Selection rationale & metrics
  paper-extraction-failed.json  # Only present when a step fails
```

These artefacts can be inspected via the Streamlit Settings screen or manually from the filesystem.

## Cost Comparison

Without schema validation (always run LLM):
- Every extraction: ~$0.10-0.50 for validation
- Failed extractions: ~$0.10-0.50 wasted
- 100 extractions (50% quality): ~$50

With dual validation (current approach):
- Good extractions (50%): ~$0.10-0.50 x 50 = $25
- Bad extractions (50%): ~$0 (schema only)
- 100 extractions: ~$25 + minimal compute
- Savings: ~50%

## Example Scenarios

### Scenario 1: Severely Broken Extraction
```json
{
  "schema_version": "v2.0"
  // Missing required fields: metadata, study_design, population...
}
```
- Schema validation: FAIL (quality: 0.20)
- LLM validation: SKIPPED (below threshold)
- -> Go directly to correction with schema errors
- Saved: ~$0.20 LLM call

### Scenario 2: Structurally Good, Semantically Wrong
```json
{
  "schema_version": "v2.0",
  "metadata": { "title": "...", "doi": "..." },
  "population": {
    "n_randomised": 100,
    "age_mean": -5  //  Negative age!
  }
}
```
- Schema validation: PASS (quality: 0.85)
- LLM validation: RUN (finds semantic error)
- -> LLM catches: "Negative age is implausible"
- Value: Found error schema missed

### Scenario 3: Perfect Extraction
```json
{
  "schema_version": "v2.0",
  "metadata": { ... },
  "study_design": { ... },
  "population": { ... },
  // All fields present and correct
}
```
- Schema validation: PASS (quality: 0.95)
- LLM validation: PASS
- -> Done! No correction needed
- Benefit: High confidence in quality

## Maintenance

The dual-validation approach lives in:
- `src/validation.py` - schema validation implementation and scoring
- `src/pipeline/validation_runner.py` - dual validation orchestration
- `src/pipeline/steps/validation.py` - IterativeLoopRunner wiring + retry logic
- `src/pipeline/quality/thresholds.py` - centralized extraction thresholds
- `prompts/Extraction-validation.txt` - LLM validation prompt design
- `prompts/Extraction-correction.txt` - correction prompt consumed during retries
- `run_pipeline.py` - CLI wiring and defaults

To modify behavior:
1. Adjust `SCHEMA_QUALITY_THRESHOLD` in `run_pipeline.py`, or pass a custom value to `run_dual_validation`.
2. Update weighting or completeness rules in `validate_extraction_quality` (`src/validation.py`).
3. Refine the validation or correction prompts to emphasise domain-specific checks.
4. Tweak `EXTRACTION_THRESHOLDS` (`src/pipeline/quality/thresholds.py`) and `max_iterations` to balance cost with quality targets.
5. Extend `PipelineFileManager` if additional audit artefacts are required.
