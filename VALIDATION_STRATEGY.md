# Validation Strategy: Dual Validation Approach

## Overview

The PDFtoPodcast extraction pipeline uses **both** schema validation and LLM validation in a complementary, two-tier approach.

## Why Both?

### Schema Validation (validation.py)
**Strengths:**
- ⚡ **Fast** - Milliseconds, no API calls
- 💰 **Free** - No LLM costs
- 🎯 **Precise** - Catches structural errors with certainty
- 📋 **Actionable** - Clear error messages

**Limitations:**
- ❌ Can't verify semantic correctness
- ❌ Can't check against source PDF
- ❌ No domain knowledge

### LLM Validation (Extraction-validation.txt)
**Strengths:**
- 🧠 **Smart** - Understands context and meaning
- 📄 **Source-aware** - Compares extraction to PDF
- 🏥 **Domain-aware** - Spots medically implausible values

**Limitations:**
- 🐌 **Slow** - 30-60+ seconds per validation
- 💸 **Expensive** - API costs for large prompts
- 🎲 **Non-deterministic** - May vary slightly

## Implementation

### Step 3a: Schema Validation (Always runs)
```python
schema_validation = validate_extraction_quality(data, schema)
quality_score = schema_validation['quality_score']  # 0.0 - 1.0
```

**What it checks:**
- JSON structure matches schema
- All required fields present
- Correct data types
- Enum values valid
- Format constraints (patterns, ranges)
- Completeness (required vs optional fields)

**Output:**
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

**What it checks:**
- Does extracted data match PDF content?
- Are values medically plausible?
- Are there contradictions or inconsistencies?
- Is important information missing?
- Are relationships between fields logical?

**Output:**
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

## Decision Logic

```
Extraction
    ↓
Schema Validation
    ↓
quality_score < 50%? ──→ Skip LLM ──→ Correction (schema errors)
    ↓
quality_score >= 50%
    ↓
LLM Validation
    ↓
Both passed? ──→ Done ✅
    ↓
Issues found? ──→ Correction (combined feedback)
```

## Benefits

1. **Efficiency**: Schema validation filters out broken extractions (saves ~$0.10-0.50 per failed extraction)
2. **Quality**: LLM catches subtle errors schema can't detect
3. **Cost-Effective**: Only pay for LLM when extraction has decent structure
4. **Fast Feedback**: Schema errors identified in <100ms
5. **Comprehensive**: Structural + semantic validation
6. **Fail-Fast**: Bad extractions caught early

## Configuration

```python
# run_pipeline.py
SCHEMA_QUALITY_THRESHOLD = 0.5  # 50%
```

**Tuning the threshold:**
- Higher (0.7-0.9): More strict, fewer LLM calls, lower cost, may miss fixable extractions
- Lower (0.3-0.4): More lenient, more LLM calls, higher cost, more thorough validation
- Default (0.5): Balanced approach

## Cost Comparison

**Without schema validation** (always run LLM):
- Every extraction: ~$0.10-0.50 for validation
- Failed extractions: ~$0.10-0.50 wasted
- 100 extractions (50% quality): ~$50

**With dual validation** (current approach):
- Good extractions (50%): ~$0.10-0.50 × 50 = $25
- Bad extractions (50%): ~$0 (schema only)
- 100 extractions: ~$25 + minimal compute
- **Savings: ~50%**

## Example Scenarios

### Scenario 1: Severely Broken Extraction
```json
{
  "schema_version": "v2.0"
  // Missing required fields: metadata, study_design, population...
}
```
- ✅ Schema validation: FAIL (quality: 0.20)
- ❌ LLM validation: SKIPPED (below threshold)
- → Go directly to correction with schema errors
- **Saved: ~$0.20 LLM call**

### Scenario 2: Structurally Good, Semantically Wrong
```json
{
  "schema_version": "v2.0",
  "metadata": { "title": "...", "doi": "..." },
  "population": {
    "n_randomised": 100,
    "age_mean": -5  // ❌ Negative age!
  }
}
```
- ✅ Schema validation: PASS (quality: 0.85)
- ✅ LLM validation: RUN (finds semantic error)
- → LLM catches: "Negative age is implausible"
- **Value: Found error schema missed**

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
- ✅ Schema validation: PASS (quality: 0.95)
- ✅ LLM validation: PASS
- → Done! No correction needed
- **Benefit: High confidence in quality**

## Maintenance

The dual-validation approach is maintained in:
- `src/validation.py` - Schema validation implementation
- `prompts/Extraction-validation.txt` - LLM validation prompt
- `run_pipeline.py` - Orchestration and threshold logic

To modify behavior:
1. Adjust `SCHEMA_QUALITY_THRESHOLD` in run_pipeline.py
2. Update schema validation scoring in validation.py
3. Refine LLM validation prompt for better semantic checks
