# Correction Loop Improvements Design

**Date:** 2026-02-17
**Branch:** `fix/correction-loop-improvements`
**Status:** Approved

## Problem

The iterative correction loop degrades quality instead of improving it. The root causes are:

1. **Binary schema scoring cliff**: `validation.py:289` uses `1.0 if is_valid else 0.0`. One schema error drops the schema component from 1.0 to 0.0, causing `schema_compliance_score` to cliff from ~86% to ~50%.

2. **LLM emits empty strings for pattern fields**: The correction prompt tells the LLM not to emit `null`, but says nothing about empty strings `""`. The LLM fills optional pattern-constrained fields (orcid, issn, pmid, ISO 8601 durations) with `""`, which fails regex validation.

3. **Schema repair doesn't fix pattern violations**: `schema_repair.py` only handles array simplification and disallowed properties, not empty-string pattern violations.

4. **Identical retry after rollback**: After reverting to best-so-far, the loop sends the exact same extraction + validation report, so the LLM makes the same mistakes.

5. **No early exit for stuck loops**: The loop burns through all iterations even when corrections consistently degrade quality.

## Fixes

### Fix 1: Deterministic empty-string repair in `schema_repair.py`

Add `_repair_pattern_violations()` that walks the schema tree, finds string fields with `pattern`/`minimum`/`enum` constraints, and removes values that violate them (for optional fields only).

### Fix 2: Proportional schema scoring in `validation.py`

Replace `schema_score = 1.0 if is_valid else 0.0` with:
```python
total_fields = completeness["total_fields"]
schema_score = max(0.0, 1.0 - len(errors) / max(total_fields, 1))
```

### Fix 3: Explicit correction prompt rule

Add to `prompts/Extraction-correction.txt` Rule 1: "If you do not have a value for an optional field with a regex pattern constraint, MUST omit the field entirely. NEVER emit an empty string."

### Fix 4: Previous-failure context in retries

Inject `_correction_hints` into the validation dict before passing to `correct_fn`. The correction step reads this and appends it to the LLM context so the LLM knows what went wrong in previous attempts.

### Fix 5: Stuck loop early exit

Add `consecutive_rollbacks` counter in `IterativeLoopRunner.run()`. After 2 consecutive rollbacks without improvement, exit early.

## Files Changed

| File | Change |
|------|--------|
| `src/pipeline/schema_repair.py` | Add pattern/minimum/enum violation repair |
| `src/validation.py` | Proportional schema scoring formula |
| `prompts/Extraction-correction.txt` | Add empty-string omission rule |
| `src/pipeline/iterative/loop_runner.py` | Failure hints injection + stuck loop detection |
| `src/pipeline/steps/validation.py` | Read `_correction_hints` from validation dict |
| `tests/` | Unit tests for all fixes |
| `CHANGELOG.md` | Document changes |

## Acceptance Criteria

- Schema repair removes empty strings violating patterns for optional fields
- Schema scoring is proportional (3 errors / 200 fields = ~98.5%, not 0%)
- Correction prompt explicitly forbids empty strings for pattern fields
- Retry corrections include previous failure context
- Stuck loops exit after 2 consecutive rollbacks
- All existing tests pass
- New unit tests cover each fix
