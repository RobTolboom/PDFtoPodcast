# Consistent Step Output Formatting

**Date:** 2026-02-23
**Branch:** feature/readable-loop-output
**Status:** Design approved

## Goal

Make all 6 pipeline steps produce consistent, user-readable console output by fixing 5 identified issues.

## Issues

### Issue 1: Appraisal header missing `═══ STEP 4:` format

**Current:** `run_appraisal_step()` prints `Critical Appraisal` as plain cyan bold. The iterative path sets `show_banner=False`, so no `═══ STEP 4:` header is shown.

**Fix:** Set `show_banner=True` in `run_appraisal_with_correction()`. Remove the verbose-only header. Suppress the plain `Critical Appraisal` sub-header inside `run_appraisal_step()` when called from the iterative path (via a `console` parameter, same pattern as other sub-steps).

### Issue 2: Appraisal debug messages always visible

**Current:** Lines 159-160 always print `Running {prompt_name} critical appraisal...` and `Tool routing: {publication_type} -> {prompt_name}`.

**Fix:** Gate behind verbose mode. In compact mode, suppress these messages using the same `console` parameter pattern used by validation/correction sub-steps.

### Issue 3: `Accuracy: 0.0%` in appraisal quality display

**Current:** Compact quality line shows all metrics including `Accuracy: 0.0%`, which is confusing since appraisal has no meaningful accuracy metric.

**Fix:** In loop_runner's compact quality display, show `N/A` instead of `0.0%` for metrics that are exactly 0.0.

### Issue 4: Podcast header missing step number

**Current:** `═══ PODCAST GENERATION ═══`

**Fix:** Change to `═══ STEP 6: PODCAST GENERATION ═══`.

### Issue 5: Step numbering consistency

All 6 steps will use `═══ STEP N: NAME ═══` format:
- Steps 1-2: Already correct
- Step 3: Already correct (loop_runner)
- Step 4: Fixed via show_banner=True
- Step 5: Already correct in iterative mode; single-pass header also needs updating
- Step 6: Fixed in podcast_logic.py

## Files to Modify

1. `src/pipeline/steps/appraisal.py` — header, debug messages, verbose gating
2. `src/pipeline/podcast_logic.py` — add step number to header
3. `src/pipeline/iterative/loop_runner.py` — N/A for 0.0% metrics

## User Preferences

- Debug messages (Tool routing, Running...): verbose only
- Zero metrics: show as "N/A"
- Headers: numbered format (`═══ STEP N: NAME ═══`)
