# Fix 31 Failing Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all 31 failing tests caused by code refactoring that moved iterative loop logic into `IterativeLoopRunner` without updating tests.

**Architecture:** Four root causes across 5 test files. Code fixes for missing `to_dict()` fields (2 fields). Test fixes for wrong patch targets, stale assertions, and changed default values.

**Tech Stack:** Python, pytest, unittest.mock

---

## Root Cause Summary

| Category | Tests | Root Cause | Fix Type |
|----------|-------|-----------|----------|
| 1 | 21 unit + 2 integration | Tests patch `orchestrator._run_*_step` but code calls `steps.validation.run_*_step` via closures | Test fix |
| 2 | 8 integration | `to_dict()` missing `best_iteration` and `warning` keys | Code fix |
| 3 | 1 unit | `extract_metrics({}, "invalid")` hits early-return guard before ValueError | Test fix |
| 4 | 1 unit | `_extract_report_metrics({})` returns `"missing"` not `"unknown"` via wrapper | Test fix |

---

### Task 1: Add `best_iteration` and `warning` to `IterativeLoopResult.to_dict()`

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py:136-168`

**Step 1: Add `warning` field to `IterativeLoopResult` dataclass**

At `loop_runner.py:145`, add a `warning` field after `error`:

```python
error: str | None = None
warning: str | None = None
failed_at_iteration: int | None = None
```

**Step 2: Add `best_iteration` and `warning` to `to_dict()`**

At `loop_runner.py:161-168`, add before the `return result` statement:

```python
        if self.best_iteration_num is not None:
            result["best_iteration"] = self.best_iteration_num
        if self.warning:
            result["warning"] = self.warning
```

**Step 3: Set `warning` in `_create_max_iterations_result()`**

At `loop_runner.py:581-590`, add `warning` to the IterativeLoopResult constructor:

```python
warning=f"Max iterations ({self.config.max_iterations}) reached without meeting quality threshold",
```

**Step 4: Set `warning` in `_create_early_stop_result()`**

At `loop_runner.py:556-565`, add `warning` to the IterativeLoopResult constructor:

```python
warning=f"Early stopping: quality degradation detected after {self.tracker.iteration_count} iterations",
```

**Step 5: Run test to verify the code fix**

Run: `python -m pytest tests/unit/test_iterative_validation_correction.py::TestBestIterationSelection -v`
Expected: PASS (these tests don't depend on the patch targets)

**Step 6: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py
git commit -m "fix: add best_iteration and warning to IterativeLoopResult.to_dict()"
```

---

### Task 2: Fix patch targets in `test_iterative_validation_correction.py`

**Files:**
- Modify: `tests/unit/test_iterative_validation_correction.py`

All tests in `TestIterativeLoop`, `TestEdgeCases`, and `TestErrorHandling` patch the wrong module. The closures in `validation.py` call `run_validation_step` and `run_correction_step` by name lookup in `src.pipeline.steps.validation`, NOT via the backward-compat aliases in `orchestrator`.

**Step 1: Replace ALL patch targets**

Throughout the file, replace these patch decorators and context managers:

| Old (wrong) | New (correct) |
|-------------|---------------|
| `@patch("src.pipeline.orchestrator._run_validation_step")` | `@patch("src.pipeline.steps.validation.run_validation_step")` |
| `@patch("src.pipeline.orchestrator._run_correction_step")` | `@patch("src.pipeline.steps.validation.run_correction_step")` |
| `patch("src.pipeline.orchestrator._run_validation_step")` | `patch("src.pipeline.steps.validation.run_validation_step")` |
| `patch("src.pipeline.orchestrator._run_correction_step")` | `patch("src.pipeline.steps.validation.run_correction_step")` |

This affects the following test methods:
- `TestIterativeLoop.test_loop_passes_first_iteration` (line 266-267)
- `TestIterativeLoop.test_loop_max_iterations_reached` (line 298-299)
- `TestIterativeLoop.test_loop_early_stopping_degradation` (line 366-367)
- `TestEdgeCases.test_schema_validation_failure` (line 462)
- `TestEdgeCases.test_llm_error_retries_exhausted` (line 481)
- `TestEdgeCases.test_json_decode_error` (line 501-502)
- `TestEdgeCases.test_unexpected_error` (line 531)
- `TestEdgeCases.test_progress_callback_invoked` (line 586)
- `TestEdgeCases.test_custom_quality_thresholds` (line 630)
- `TestErrorHandling.test_llm_failure_returns_error_status` (line 678-679)
- `TestErrorHandling.test_llm_retry_mechanism_exists` (line 717-718)
- `TestErrorHandling.test_schema_failure_early_exit` (line 758)
- `TestErrorHandling.test_unexpected_error_graceful_fail` (line 789-790)
- `TestErrorHandling.test_json_decode_error_handling` (line 826-827)

**Step 2: Run a single test to verify patch target fix**

Run: `python -m pytest tests/unit/test_iterative_validation_correction.py::TestIterativeLoop::test_loop_passes_first_iteration -xvs 2>&1 | tail -20`
Expected: PASS with `final_status == "passed"`

**Step 3: Commit**

```bash
git add tests/unit/test_iterative_validation_correction.py
git commit -m "fix(tests): correct patch targets for iterative validation tests"
```

---

### Task 3: Fix error status and assertion expectations in unit tests

**Files:**
- Modify: `tests/unit/test_iterative_validation_correction.py`

The `IterativeLoopRunner` uses generic `"failed"` status (not specific `"failed_llm_error"`, etc.). Some tests also check for keys/values that changed.

**Step 1: Fix `test_llm_error_retries_exhausted` (line 481-499)**

The loop_runner catches LLMError after `_with_llm_retry` exhausts retries. The generic `_create_error_result` returns `final_status="failed"` and the error message is the exception message directly.

Change assertions from:
```python
assert result["final_status"] == "failed_llm_error"
assert "error" in result
assert "LLM provider error after 3 retries" in result["error"]
# Should have tried 1 initial + 3 retries = 4 calls
assert mock_validation.call_count == 4
```
To:
```python
assert result["final_status"] == "failed"
assert "error" in result
assert "API rate limit" in result["error"]
# _with_llm_retry does 1 initial + 3 retries = 4 calls within single validate_fn invocation
assert mock_validation.call_count == 4
```

**Step 2: Fix `test_json_decode_error` (line 504-529)**

JSONDecodeError propagates through `_with_llm_retry` (which only catches LLMError) to the loop_runner's generic `except Exception`.

Change assertions from:
```python
assert result["final_status"] == "failed_invalid_json"
assert "error" in result
assert "invalid JSON" in result["error"]
```
To:
```python
assert result["final_status"] == "failed"
assert "error" in result
```

**Step 3: Fix `test_unexpected_error` (line 531-545)**

Change assertion from:
```python
assert result["final_status"] == "failed_unexpected_error"
```
To:
```python
assert result["final_status"] == "failed"
```

**Step 4: Fix `test_loop_max_iterations_reached` assertion on `warning`**

The `warning` key should now exist in `to_dict()` output (from Task 1). No change needed for the assertion `assert "warning" in result`. But the test also checks `result["iterations"][i]["validation"]` which should still work since `to_legacy_list()` preserves the `"validation"` key.

Verify: no changes needed for this test after Task 1+2.

**Step 5: Fix `test_llm_failure_returns_error_status` (line 675-713)**

The correction mock raises LLMError. With `_with_llm_retry`, this will be retried. After retries exhausted, the error propagates. The loop_runner catches it with generic `except Exception`.

Change assertions from:
```python
assert result["final_status"] in ["failed_llm_error", "max_iterations_reached"]
```
To:
```python
assert result["final_status"] in ["failed", "max_iterations_reached"]
```

**Step 6: Fix `test_llm_retry_mechanism_exists` (line 715-754)**

The test mocks `time.sleep` but `_with_llm_retry` uses `time.sleep`. Need to patch the correct sleep location.

Change the `patch("time.sleep")` to `patch("src.pipeline.steps.validation.time.sleep")` (or keep as-is and verify if `time.sleep` in `_with_llm_retry` is the same).

Actually, `_with_llm_retry` does `wait_time = 2**retry; time.sleep(wait_time)` where `time` is imported at module level. The patch should be `patch("src.pipeline.steps.validation.time.sleep")`.

Also update:
```python
assert mock_sleep.call_count >= 1
```
This should still pass since `_with_llm_retry` calls `time.sleep` between retries.

**Step 7: Fix `test_schema_failure_early_exit` (line 756-785)**

This test only patches `_run_validation_step` (already fixed in Task 2). The assertions should be correct:
```python
assert result["final_status"] == "failed_schema_validation"
```
Wait - the mock returns `schema_validation.quality_score = 0.30` but `_get_schema_quality()` reads `verification_summary.schema_compliance_score` not `schema_validation.quality_score`. The mock has `schema_compliance_score: 0.35`. Since 0.35 < 0.50, the schema check fails and triggers retry+eventual failure. Assertion should pass. Verify after running.

**Step 8: Fix `test_unexpected_error_graceful_fail` (line 787-822)**

Change assertion from:
```python
assert result["final_status"] == "failed_unexpected_error"
```
To:
```python
assert result["final_status"] == "failed"
```

**Step 9: Fix `test_json_decode_error_handling` (line 824-861)**

Change assertion from:
```python
assert result["final_status"] == "failed_invalid_json"
```
To:
```python
assert result["final_status"] == "failed"
```

**Step 10: Run all unit tests in this file**

Run: `python -m pytest tests/unit/test_iterative_validation_correction.py -v 2>&1 | tail -40`
Expected: All 30 tests PASS

**Step 11: Commit**

```bash
git add tests/unit/test_iterative_validation_correction.py
git commit -m "fix(tests): update assertions to match IterativeLoopRunner behavior"
```

---

### Task 4: Fix patch targets and assertions in `test_validation_correction_metadata_stripping.py`

**Files:**
- Modify: `tests/integration/test_validation_correction_metadata_stripping.py`

**Step 1: Replace ALL patch targets**

Same replacement as Task 2:

| Old (wrong) | New (correct) |
|-------------|---------------|
| `@patch("src.pipeline.orchestrator._run_validation_step")` | `@patch("src.pipeline.steps.validation.run_validation_step")` |
| `@patch("src.pipeline.orchestrator._run_correction_step")` | `@patch("src.pipeline.steps.validation.run_correction_step")` |

This affects:
- `test_correction_notes_stripped_from_final_result` (line 121-122)
- `test_correction_notes_stripped_from_all_iterations` (line 184-185)
- `test_metadata_fields_stripped_from_final_result` (line 232-233)

**Step 2: Fix iteration key name in `test_correction_notes_stripped_from_all_iterations`**

The legacy dict format uses `"result"` not `"extraction"`. Change line 228:

From:
```python
"correction_notes" not in iteration["extraction"]
```
To:
```python
"correction_notes" not in iteration["result"]
```

And the assertion message at line 229:
From:
```python
f"Iteration {i} extraction should not contain correction_notes"
```
To:
```python
f"Iteration {i} result should not contain correction_notes"
```

**Step 3: Run integration tests**

Run: `python -m pytest tests/integration/test_validation_correction_metadata_stripping.py -v 2>&1 | tail -15`
Expected: All 3 tests PASS

**Step 4: Commit**

```bash
git add tests/integration/test_validation_correction_metadata_stripping.py
git commit -m "fix(tests): correct patch targets in metadata stripping tests"
```

---

### Task 5: Fix `test_report_full_loop.py` assertions for `best_iteration` key

**Files:**
- Modify: `tests/integration/test_report_full_loop.py`

After Task 1, `to_dict()` includes `best_iteration`. But `best_iteration_num` is only set in `_create_success_result`, `_create_max_iterations_result`, and `_create_early_stop_result`. We need to verify it's populated correctly.

**Step 1: Verify `best_iteration` is present for `test_report_requires_correction` (line 386)**

The test expects `result["best_iteration"] == 1`. After Task 1, this should work because `_create_success_result` sets `best_iteration_num=iteration_num`. The test flow: iter 0 quality insufficient → correction → iter 1 quality sufficient → `_create_success_result(result, validation, iteration_num=1)`.

BUT: `_create_success_result` in `loop_runner.py:531` does NOT set `best_iteration_num`:
```python
return IterativeLoopResult(
    best_result=result,
    best_validation=validation,
    ...
    # missing: best_iteration_num=iteration_num
)
```

We need to fix this in loop_runner.py. Add `best_iteration_num=iteration_num` to `_create_success_result` constructor call.

**Step 2: Verify `best_iteration` for `test_max_iterations_reached` (line 437)**

The test expects `"best_iteration" in result`. `_create_max_iterations_result` already sets `best_iteration_num=best["iteration_num"]` (line 589). After Task 1, this will be in `to_dict()`. Should work.

**Step 3: Verify `best_iteration` for `test_early_stopping_on_degradation` (line 491)**

The test expects `result["best_iteration"] == 0`. `_create_early_stop_result` already sets `best_iteration_num=best["iteration_num"]`. Should work.

**Step 4: Verify dependency gating tests (lines 494-623)**

These test `result["status"] == "blocked"`. They don't use the iterative loop at all (they return early from dependency checks). No changes needed.

**Step 5: Verify `test_custom_quality_thresholds` (line 628-685)**

This test checks `result["final_status"] == "passed"` and `result["iteration_count"] == 1`. No `best_iteration` assertion. Should work.

**Step 6: Add `best_iteration_num` to `_create_success_result`**

At `loop_runner.py:531`, add to the constructor:

```python
best_iteration_num=iteration_num,
```

**Step 7: Run report integration tests**

Run: `python -m pytest tests/integration/test_report_full_loop.py -v 2>&1 | tail -20`
Expected: All 10 tests PASS

**Step 8: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py tests/integration/test_report_full_loop.py
git commit -m "fix: set best_iteration_num in success result and verify report loop tests"
```

---

### Task 6: Fix `test_quality_module.py` invalid metric type test

**Files:**
- Modify: `tests/unit/test_quality_module.py:195-198`

**Step 1: Fix `test_invalid_metric_type`**

The early-return guard `if not validation_result` fires for `{}` (falsy) before reaching the `ValueError`. Pass a non-empty dict to bypass the guard.

Change from:
```python
def test_invalid_metric_type(self):
    """Test that invalid metric type raises ValueError."""
    with pytest.raises(ValueError, match="Unknown metric type"):
        extract_metrics({}, "invalid")  # type: ignore
```
To:
```python
def test_invalid_metric_type(self):
    """Test that invalid metric type raises ValueError."""
    with pytest.raises(ValueError, match="Unknown metric type"):
        extract_metrics({"some_data": True}, "invalid")  # type: ignore
```

**Step 2: Run test**

Run: `python -m pytest tests/unit/test_quality_module.py::TestExtractMetrics::test_invalid_metric_type -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_quality_module.py
git commit -m "fix(tests): pass non-empty dict to trigger ValueError in metric type test"
```

---

### Task 7: Fix `test_report_quality.py` overall_status expectation

**Files:**
- Modify: `tests/unit/test_report_quality.py:108-116`

**Step 1: Fix `test_extract_with_no_validation_summary`**

The test calls `_extract_report_metrics({})`. In `report.py:62`, `_extract_report_metrics` is aliased to `extract_report_metrics_as_dict`, which routes through `extract_metrics({}, MetricType.REPORT)`. The early-return guard returns `QualityMetrics(overall_status="missing")` for empty dicts.

Change from:
```python
assert metrics["overall_status"] == "unknown"
```
To:
```python
assert metrics["overall_status"] == "missing"
```

**Step 2: Run test**

Run: `python -m pytest tests/unit/test_report_quality.py::TestExtractReportMetrics::test_extract_with_no_validation_summary -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_report_quality.py
git commit -m "fix(tests): update expected overall_status from 'unknown' to 'missing'"
```

---

### Task 8: Full verification run

**Step 1: Run all previously-failing tests**

```bash
python -m pytest tests/unit/test_iterative_validation_correction.py tests/integration/test_report_full_loop.py tests/integration/test_validation_correction_metadata_stripping.py tests/unit/test_quality_module.py tests/unit/test_report_quality.py -v 2>&1 | tail -50
```
Expected: All 31 previously-failing tests now PASS. Total: ~XX passed, 0 failed.

**Step 2: Run full test suite to verify no regressions**

```bash
make test-fast
```
Expected: No NEW failures beyond the previous pass count.

**Step 3: Run format and lint**

```bash
make format && make lint
```

**Step 4: Final commit if needed**

```bash
make commit
git commit -m "fix: resolve all 31 failing tests from iterative loop refactoring"
```
