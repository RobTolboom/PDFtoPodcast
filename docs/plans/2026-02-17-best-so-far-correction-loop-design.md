# Best-So-Far Correction Loop

## Goal

When the iterative correction loop produces a result that is worse than the previous best, the next correction attempt should use the best-so-far result instead of the degraded one.

## Problem

Currently, `IterativeLoopRunner.run()` always feeds the most recent corrected result into the next correction iteration, even when that correction degraded quality. This means the LLM is trying to fix an already-worse version, compounding errors.

Example observed in practice:
- Iteration 0: quality 92.6% (good)
- Correction produces quality 84.4% (worse — schema compliance dropped from 84.9% to 50.0%)
- Iteration 1: uses the 84.4% result as input, digging deeper into a bad version

## Design

### Approach: Expand existing `last_good_*` tracking

The `last_good_result` / `last_good_validation` variables already exist in `loop_runner.py` for schema-failure retries. Expand their role to also handle quality degradation.

### Core change (`loop_runner.py`, lines ~438-452)

After correction passes schema validation, compare corrected quality against best-so-far:

- **If better or equal:** Accept corrected result, update `last_good_*` (current behavior)
- **If worse:** Log warning, revert `current_result` to `last_good_result`, use `last_good_validation` for next correction

The degraded result is still recorded in the `IterationTracker` for history/trajectory purposes.

### What stays the same

- `IterationTracker` — still records all iterations including degraded ones
- `select_best_iteration()` — unchanged, still works for final selection
- Schema-failure retry logic — unchanged
- Degradation detection — unchanged (trajectory shows degraded attempts)
- All other pipeline steps — no changes

### Display

When rolling back, print:
```
⚠ Correction degraded quality (84.4% < 92.6%), reverting to best iteration for next attempt
```

### Edge cases

- **First iteration (iteration 0):** `last_good_validation` is set after initial validation (line 337), so the comparison always has a valid baseline.
- **Equal quality:** Accepted (>= comparison), since new result may fix different issues even at same score.

## Scope

- **Files changed:** `src/pipeline/iterative/loop_runner.py` (~15 lines modified)
- **Tests:** Update existing loop_runner tests, add test for quality-degradation rollback
- **No schema changes, no prompt changes, no new dependencies**

## Acceptance Criteria

1. When correction degrades quality, next iteration uses the best-so-far result
2. Degraded results are still recorded in iteration history
3. Console output clearly indicates when a rollback occurs
4. All existing tests pass
5. New test covers the rollback scenario

## Branch

`feature/best-so-far-correction`
