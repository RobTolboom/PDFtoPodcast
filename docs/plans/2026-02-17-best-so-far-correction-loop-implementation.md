# Best-So-Far Correction Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When a correction degrades quality, the next correction attempt uses the best-so-far result instead of the degraded one.

**Architecture:** Expand the existing `last_good_result` / `last_good_validation` variables in `IterativeLoopRunner.run()` to also handle quality degradation (not just schema failures). After each correction, compare quality to best-so-far; if worse, revert to best-so-far for the next attempt.

**Tech Stack:** Python 3.10+, pytest, existing `extract_metrics` from `src/pipeline/quality/metrics.py`

---

### Task 1: Write the failing test for best-so-far rollback

**Files:**
- Modify: `tests/unit/test_loop_runner.py`

**Step 1: Write the failing test**

Add this test to the `TestIterativeLoopRunner` class. The scenario:
- Iteration 0: quality 85% (below threshold, needs correction)
- Correction produces quality 70% (WORSE)
- Iteration 1: should use the iteration-0 result (85%) as input, NOT the 70% result
- Second correction produces quality 96% (passes threshold)

```python
def test_correction_rollback_on_quality_degradation(self):
    """Test that correction uses best-so-far when quality degrades.

    Scenario:
    - Iteration 0: quality ~85% (needs correction)
    - Correction 0: quality drops to ~70% (degraded)
    - Iteration 1: should roll back to iteration 0's result
    - Correction 1: quality rises to ~96% (passes)

    The key assertion: correct_fn's second call receives the
    iteration-0 result (best-so-far), NOT the degraded result.
    """
    config = IterativeLoopConfig(
        metric_type=MetricType.EXTRACTION,
        max_iterations=5,
        show_banner=False,
    )

    initial_result = {"data": "initial"}
    degraded_result = {"data": "degraded"}
    final_result = {"data": "final"}

    # Validation results
    validation_iter0 = self._create_validation_result(
        completeness=0.80, accuracy=0.85, schema_compliance=0.90
    )  # quality ~85%, below threshold
    validation_degraded = self._create_validation_result(
        completeness=0.60, accuracy=0.70, schema_compliance=0.80
    )  # quality ~68%, worse
    validation_pass = self._create_validation_result(
        completeness=0.95, accuracy=0.98, schema_compliance=0.97
    )  # quality ~96%, passes

    # Validate sequence:
    # 1. iter 0: validate initial -> validation_iter0 (needs correction)
    # 2. iter 0: correct -> validate corrected -> validation_degraded (worse)
    # 3. iter 1: reuses best-so-far validation (validation_iter0)
    # 4. iter 1: correct -> validate corrected -> validation_pass (passes)
    validate_fn = MagicMock(
        side_effect=[validation_iter0, validation_degraded, validation_pass]
    )

    # Correct returns degraded first, then final
    correct_fn = MagicMock(side_effect=[degraded_result, final_result])

    runner = IterativeLoopRunner(
        config=config,
        initial_result=initial_result,
        validate_fn=validate_fn,
        correct_fn=correct_fn,
    )
    result = runner.run()

    assert result.final_status == FINAL_STATUS_PASSED
    assert result.best_result == final_result

    # Key assertion: second correction got the INITIAL result (best-so-far),
    # not the degraded result
    assert correct_fn.call_count == 2
    second_call_args = correct_fn.call_args_list[1]
    assert second_call_args[0][0] == initial_result  # first positional arg = result
    assert second_call_args[0][1] == validation_iter0  # second positional arg = validation
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_loop_runner.py::TestIterativeLoopRunner::test_correction_rollback_on_quality_degradation -v`
Expected: FAIL — second correction currently receives `degraded_result`, not `initial_result`

**Step 3: Commit failing test**

```bash
git add tests/unit/test_loop_runner.py
git commit -m "test: add failing test for best-so-far correction rollback"
```

---

### Task 2: Implement best-so-far rollback in loop_runner.py

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py:438-452`

**Step 1: Add quality comparison after correction passes schema check**

In `loop_runner.py`, the `run()` method at line ~438 (after `# Correction succeeded`), replace the unconditional acceptance with a quality comparison. The change is in the block between the schema-quality check (line ~402) and the save/update block (line ~444):

Replace lines 438-452 (the block after `# Correction succeeded - update last good state`):

```python
                # Compare corrected quality against best-so-far
                corrected_metrics = extract_metrics(
                    corrected_validation, self.config.metric_type
                )
                best_so_far_metrics = extract_metrics(
                    last_good_validation, self.config.metric_type
                )

                if corrected_metrics.quality_score >= best_so_far_metrics.quality_score:
                    # Correction improved or maintained quality — accept it
                    last_good_result = corrected_result
                    last_good_validation = corrected_validation
                    correction_retry_count = 0

                    # Save corrected iteration
                    if self.save_iteration_fn:
                        self.save_iteration_fn(
                            iteration_num + 1, corrected_result, corrected_validation
                        )

                    # Update for next iteration
                    current_result = corrected_result
                    current_validation = corrected_validation
                else:
                    # Correction degraded quality — revert to best-so-far
                    self.console.print(
                        f"[yellow]⚠ Correction degraded quality "
                        f"({corrected_metrics.quality_score:.1%} < "
                        f"{best_so_far_metrics.quality_score:.1%}), "
                        f"reverting to best iteration for next attempt[/yellow]"
                    )
                    correction_retry_count = 0

                    # Save the degraded iteration for history (still useful for trajectory)
                    if self.save_iteration_fn:
                        self.save_iteration_fn(
                            iteration_num + 1, corrected_result, corrected_validation
                        )

                    # Revert to best-so-far for next correction attempt
                    current_result = last_good_result
                    current_validation = last_good_validation

                iteration_num += 1
```

Note: `extract_metrics` is already imported at line 21.

**Step 2: Run the failing test to verify it passes**

Run: `python -m pytest tests/unit/test_loop_runner.py::TestIterativeLoopRunner::test_correction_rollback_on_quality_degradation -v`
Expected: PASS

**Step 3: Run all loop_runner tests to check for regressions**

Run: `python -m pytest tests/unit/test_loop_runner.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py
git commit -m "feat: use best-so-far result when correction degrades quality"
```

---

### Task 3: Write test for degraded iteration still tracked in history

**Files:**
- Modify: `tests/unit/test_loop_runner.py`

**Step 1: Write the test**

Add this test to verify degraded iterations still appear in the trajectory:

```python
def test_degraded_iteration_still_tracked_in_trajectory(self):
    """Test that degraded iterations are still recorded in improvement_trajectory.

    Even when the loop reverts to best-so-far, the degraded iteration
    should appear in the trajectory for diagnostics.
    """
    config = IterativeLoopConfig(
        metric_type=MetricType.EXTRACTION,
        max_iterations=5,
        show_banner=False,
    )

    validation_iter0 = self._create_validation_result(
        completeness=0.80, accuracy=0.85, schema_compliance=0.90
    )
    validation_degraded = self._create_validation_result(
        completeness=0.60, accuracy=0.70, schema_compliance=0.80
    )
    validation_pass = self._create_validation_result(
        completeness=0.95, accuracy=0.98, schema_compliance=0.97
    )

    validate_fn = MagicMock(
        side_effect=[validation_iter0, validation_degraded, validation_pass]
    )
    correct_fn = MagicMock(
        side_effect=[{"data": "degraded"}, {"data": "final"}]
    )

    runner = IterativeLoopRunner(
        config=config,
        initial_result={"data": "initial"},
        validate_fn=validate_fn,
        correct_fn=correct_fn,
    )
    result = runner.run()

    # Trajectory should have 3 entries: iter0, degraded iter1, final iter2
    assert len(result.improvement_trajectory) == 3
    # The middle entry should show the dip
    assert result.improvement_trajectory[1] < result.improvement_trajectory[0]
```

**Step 2: Run the test**

Run: `python -m pytest tests/unit/test_loop_runner.py::TestIterativeLoopRunner::test_degraded_iteration_still_tracked_in_trajectory -v`
Expected: PASS (this should already work since we still add degraded iterations to the tracker in the next loop iteration)

**Step 3: Commit**

```bash
git add tests/unit/test_loop_runner.py
git commit -m "test: verify degraded iterations tracked in trajectory"
```

---

### Task 4: Run full test suite, format, and lint

**Files:** None (verification only)

**Step 1: Run format and lint**

Run: `make format && make lint`
Expected: Clean

**Step 2: Run fast tests**

Run: `make test-fast`
Expected: All tests pass

**Step 3: Commit any formatting fixes**

```bash
# Only if formatting changed anything
git add -u && git commit -m "style: format changes"
```

---

### Task 5: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add entry under Unreleased**

Add under the `## [Unreleased]` section:

```markdown
### Changed
- Iterative correction loop now uses best-so-far result when a correction degrades quality, instead of feeding the degraded result into the next correction attempt
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add best-so-far correction loop changelog entry"
```
