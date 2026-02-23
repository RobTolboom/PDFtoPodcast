# Consistent Step Output Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make all 6 pipeline steps produce consistent `═══ STEP N: NAME ═══` headers, suppress debug messages in compact mode, and show N/A for zero-value metrics.

**Architecture:** Changes touch 3 files: appraisal step (header + debug gating), podcast logic (header format), and loop_runner (N/A display). Each change is isolated and testable.

**Tech Stack:** Python, Rich console, pytest

---

### Task 1: Add `console` parameter to `run_appraisal_step` for output suppression

**Files:**
- Modify: `src/pipeline/steps/appraisal.py:124-175`
- Test: `tests/unit/test_loop_runner.py` (existing appraisal tests)

**Step 1: Add optional `console` parameter to `run_appraisal_step`**

In `src/pipeline/steps/appraisal.py`, modify the function signature at line 124 to accept an optional `console` parameter, same pattern used by `run_appraisal_validation_step` and `run_appraisal_correction_step`:

```python
def run_appraisal_step(
    extraction_result: dict[str, Any],
    publication_type: str,
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
    console: Console | None = None,
) -> dict[str, Any]:
```

Add at the top of the function body (after docstring):

```python
    output = console or _console
```

Replace all `_console.print(` calls within this function (lines 137, 145, 159, 160, 172) with `output.print(`.

**Step 2: Pass quiet console from `run_appraisal_with_correction`**

In `run_appraisal_with_correction` (line 478), pass the `quiet_console` to `run_appraisal_step` at line 518:

```python
        initial_appraisal = run_appraisal_step(
            extraction_result=extraction_result,
            publication_type=publication_type,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
            console=quiet_console,
        )
```

Also update the `regenerate_initial_fn` closure (around line 585) to pass `console=quiet_console`.

**Step 3: Enable loop_runner banner for appraisal**

In `run_appraisal_with_correction`, change `show_banner=False` (line 541) to `show_banner=True`. Remove the verbose-only header block at lines 491-495.

**Step 4: Run tests**

Run: `make format && make lint && make test-fast`
Expected: All pass. The quiet_console suppresses appraisal sub-step output in compact mode, loop_runner now prints the `═══ STEP 4:` banner.

**Step 5: Commit**

```bash
git add src/pipeline/steps/appraisal.py
git commit -m "feat: consistent STEP 4 header and suppress appraisal debug in compact mode"
```

---

### Task 2: Show N/A for zero-value metrics in loop_runner

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py:636-647`
- Test: `tests/unit/test_loop_runner.py`

**Step 1: Write failing test**

Add a test to the `TestCompactModeOutput` class in `tests/unit/test_loop_runner.py`:

```python
def test_initial_quality_shows_na_for_zero_metrics(self):
    """_display_initial_quality should show N/A for metrics that are 0.0."""
    console, buf = self._make_console()
    config = IterativeLoopConfig(
        metric_type=MetricType.EXTRACTION,
        max_iterations=1,
        show_banner=False,
    )

    validate_fn = MagicMock(
        return_value=self._create_validation_result(
            completeness=0.95, accuracy=0.98, schema_compliance=0.97
        )
    )
    correct_fn = MagicMock()

    runner = IterativeLoopRunner(
        config=config,
        initial_result={"data": "test"},
        validate_fn=validate_fn,
        correct_fn=correct_fn,
        console_instance=console,
    )

    from src.pipeline.quality.metrics import QualityMetrics

    metrics = QualityMetrics(
        schema_compliance_score=0.95,
        completeness_score=0.90,
        accuracy_score=0.0,
        quality_score=0.948,
    )
    runner._display_initial_quality(metrics)

    output = buf.getvalue()
    assert "Schema: 95.0%" in output
    assert "Completeness: 90.0%" in output
    assert "Accuracy: N/A" in output
    assert "Accuracy: 0.0%" not in output
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_loop_runner.py::TestCompactModeOutput::test_initial_quality_shows_na_for_zero_metrics -v`
Expected: FAIL — currently shows `Accuracy: 0.0%` instead of `Accuracy: N/A`.

**Step 3: Implement N/A display for zero metrics**

In `loop_runner.py`, modify `_display_initial_quality` (line 636). Change the accuracy check:

```python
    def _display_initial_quality(self, metrics: QualityMetrics) -> None:
        """Display compact initial validation quality with threshold warning."""
        parts = []
        if metrics.schema_compliance_score is not None:
            parts.append(f"Schema: {metrics.schema_compliance_score:.1%}")
        if metrics.completeness_score is not None:
            parts.append(f"Completeness: {metrics.completeness_score:.1%}")
        if metrics.accuracy_score is not None:
            if metrics.accuracy_score == 0.0:
                parts.append("Accuracy: N/A")
            else:
                parts.append(f"Accuracy: {metrics.accuracy_score:.1%}")

        metrics_line = " | ".join(parts)
        self.console.print(f"  {metrics_line} → Quality: {metrics.quality_score:.1%}")

        meets = is_quality_sufficient_from_metrics(metrics, self.thresholds)
        if not meets:
            self.console.print("  [yellow]⚠ Below threshold — running correction[/yellow]")
```

Also apply the same logic to `_display_before_after_quality` (line 653) — skip the before/after delta line when both values are 0.0 (just like unchanged metrics are already skipped):

In the loop at line 669, add a check:

```python
        for name, before, after in metrics_to_show:
            if before is None or after is None:
                continue
            if before == 0.0 and after == 0.0:
                continue  # Skip N/A metrics in before→after display
            delta = after - before
            if abs(delta) < 0.001:
                continue  # Skip unchanged metrics
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_loop_runner.py::TestCompactModeOutput::test_initial_quality_shows_na_for_zero_metrics -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `make format && make lint && make test-fast`
Expected: All pass.

**Step 6: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py tests/unit/test_loop_runner.py
git commit -m "feat: show N/A for zero-value metrics in compact quality display"
```

---

### Task 3: Add step number to podcast header

**Files:**
- Modify: `src/pipeline/podcast_logic.py:58`

**Step 1: Update podcast header**

In `podcast_logic.py` line 58, change:

```python
    console.print("\n[bold magenta]═══ PODCAST GENERATION ═══[/bold magenta]\n")
```

to:

```python
    console.print("\n[bold magenta]═══ STEP 6: PODCAST GENERATION ═══[/bold magenta]\n")
```

**Step 2: Run tests**

Run: `make format && make lint && make test-fast`
Expected: All pass.

**Step 3: Commit**

```bash
git add src/pipeline/podcast_logic.py
git commit -m "feat: add step number to podcast generation header"
```

---

### Task 4: Fix report single-pass header format

**Files:**
- Modify: `src/pipeline/steps/report.py:114`

**Step 1: Update report single-pass header**

In `report.py` line 114, change:

```python
    _console.print("\n[bold cyan]=== REPORT GENERATION (Phase 2 - Single Pass) ===[/bold cyan]\n")
```

to:

```python
    _console.print("\n[bold magenta]═══ STEP 5: REPORT GENERATION ═══[/bold magenta]\n")
```

This makes the single-pass report header consistent with the iterative-mode header (same step number, same color, same format).

**Step 2: Run tests**

Run: `make format && make lint && make test-fast`
Expected: All pass.

**Step 3: Commit**

```bash
git add src/pipeline/steps/report.py
git commit -m "feat: consistent STEP 5 header for single-pass report generation"
```

---

### Task 5: Fix appraisal single-pass header format

**Files:**
- Modify: `src/pipeline/steps/appraisal.py:417`

**Step 1: Update appraisal single-pass header**

In `appraisal.py` line 417, change:

```python
    _console.print("\n[bold magenta]=== CRITICAL APPRAISAL (Single Pass) ===[/bold magenta]\n")
```

to:

```python
    _console.print("\n[bold magenta]═══ STEP 4: CRITICAL APPRAISAL ═══[/bold magenta]\n")
```

**Step 2: Run tests**

Run: `make format && make lint && make test-fast`
Expected: All pass.

**Step 3: Commit**

```bash
git add src/pipeline/steps/appraisal.py
git commit -m "feat: consistent STEP 4 header for single-pass appraisal"
```

---

### Task 6: Update tests and documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/plans/2026-02-23-consistent-step-output-design.md` (mark complete)

**Step 1: Update CHANGELOG.md**

Add under "Unreleased":

```markdown
- Consistent `═══ STEP N: NAME ═══` headers across all 6 pipeline steps
- Appraisal debug messages (Tool routing, Running...) hidden in compact mode
- Zero-value metrics display as "N/A" instead of "0.0%" in quality summaries
```

**Step 2: Run full verification**

Run: `make format && make lint && make test-fast`
Expected: All pass.

**Step 3: Commit**

```bash
git add CHANGELOG.md docs/plans/2026-02-23-consistent-step-output-design.md
git commit -m "docs: update changelog for consistent step output formatting"
```
