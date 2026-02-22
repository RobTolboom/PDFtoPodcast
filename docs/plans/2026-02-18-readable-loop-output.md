# Readable Loop Output Implementation Plan

> **Status:** COMPLETE (2026-02-22)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the iterative correction loop console output human-readable by replacing technical jargon, redundant validation blocks, and confusing iteration numbering with a clean "Correction N of M" format showing before→after deltas.

**Architecture:** The output originates from two layers: (1) `loop_runner.py` controls iteration headers, quality summaries, retry/rollback messages, and final status; (2) step-specific functions in `validation_runner.py`, `steps/validation.py`, `steps/appraisal.py`, and `steps/report.py` print their own validation/correction banners and detail blocks. The plan consolidates output control into `loop_runner.py` and silences redundant detail from the step functions, while keeping step-level output available via a `verbose` flag for debugging.

**Tech Stack:** Python, Rich console library

---

## Design Principles

1. **"Correction N of M"** instead of "Iteration N" — humans count corrections, not loop indices
2. **Before → after on one line** per metric, with color-coded delta
3. **Hide implementation details** — no "Reusing post-correction validation", no "retry 1/2" internals
4. **Plain language for failures** — "Produced invalid output — retrying" not "Correction failed schema validation (quality: 0.00)"
5. **One clear summary line** at the end of the loop
6. **Verbose mode preserved** — the current detailed output remains available via `verbose=True` for debugging

## Target Output (extraction example)

```
=== STEP 3: ITERATIVE VALIDATION & CORRECTION ===

Validating extraction...
  Schema: 84.9% | Completeness: 83.0% | Accuracy: 99.0% → Quality: 89.8%
  ⚠ Below 95% threshold — running correction

Correction 1 of 3
  Validating... correcting... validating...
  Schema: 84.9% → 100.0% (+15.1%)
  Completeness: 83.0% → 93.0% (+10.0%)
  Accuracy: 99.0% → 98.0% (-1.0%)
  Quality: 89.8% → 96.4% (+6.6%) ✅

✅ Passed after 1 correction
```

## Target Output (appraisal example with failure + retry)

```
=== CRITICAL APPRAISAL WITH ITERATIVE CORRECTION ===

Validating appraisal...
  Schema: 90.0% | Completeness: 90.0% → Quality: 93.0%
  ⚠ Below threshold — running correction

Correction 1 of 3
  Validating... correcting...
  ✗ Produced invalid output — retrying
  Correcting... validating...
  Schema: 90.0% → 98.0% (+8.0%)
  Quality: 93.0% → 94.5% (+1.5%) ✅

✅ Passed after 1 correction (1 retry)
```

## Target Output (stuck loop with rollback)

```
Correction 1 of 3
  Validating... correcting... validating...
  Quality: 89.8% → 85.2% (-4.6%) — reverting to best

Correction 2 of 3
  Correcting... validating...
  Quality: 89.8% → 84.0% (-5.8%) — reverting to best
  ⚠ 2 consecutive corrections degraded quality — stopping early

✅ Best result: initial extraction (89.8%)
```

---

### Task 1: Add `verbose` flag to `IterativeLoopConfig` and `loop_runner.py`

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py:102-128` (IterativeLoopConfig dataclass)
- Test: `tests/unit/test_loop_runner.py`

**Step 1: Write the failing test**

In `tests/unit/test_loop_runner.py`, add a test that verifies the `verbose` field exists and defaults to `False`:

```python
class TestIterativeLoopConfigVerbose:
    """Test verbose flag on IterativeLoopConfig."""

    def test_verbose_defaults_to_false(self):
        config = IterativeLoopConfig(metric_type=MetricType.EXTRACTION)
        assert config.verbose is False

    def test_verbose_can_be_set_true(self):
        config = IterativeLoopConfig(metric_type=MetricType.EXTRACTION, verbose=True)
        assert config.verbose is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_loop_runner.py::TestIterativeLoopConfigVerbose -v`
Expected: FAIL with `TypeError: unexpected keyword argument 'verbose'`

**Step 3: Write minimal implementation**

Add to `IterativeLoopConfig` dataclass in `loop_runner.py:128`:

```python
verbose: bool = False  # Show detailed validation/correction output (debugging)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_loop_runner.py::TestIterativeLoopConfigVerbose -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py tests/unit/test_loop_runner.py
git commit -m "feat: add verbose flag to IterativeLoopConfig"
```

---

### Task 2: Replace "Iteration N" headers with "Correction N of M" in `loop_runner.py`

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py:283-285` (iteration header)
- Modify: `src/pipeline/iterative/loop_runner.py:534-562` (`_display_quality_scores`)
- Modify: `src/pipeline/iterative/loop_runner.py:345-355` (validation save + reuse message)
- Modify: `src/pipeline/iterative/loop_runner.py:393-396` (correction header)
- Test: `tests/unit/test_loop_runner.py`

The key mental model change: iteration 0 is "initial validation". Iterations 1+ are "Correction N of max_iterations". The loop variable `iteration_num` starts at 0 (initial), so correction number = `iteration_num` (since correction runs at end of iteration 0, producing iteration 1's result).

**Step 1: Write failing tests**

```python
class TestReadableOutput:
    """Test human-readable console output."""

    def test_initial_validation_header_no_iteration_number(self, capsys):
        """Initial validation should not show 'Iteration 0'."""
        # Setup a runner that passes on first validation (no correction needed)
        # Capture console output, verify "Iteration 0" is NOT present
        # Verify "Validating" IS present
        ...

    def test_correction_shows_n_of_max(self, capsys):
        """Correction should show 'Correction 1 of 3' not 'Iteration 1'."""
        # Setup a runner that needs 1 correction
        # Capture console output, verify "Correction 1 of 3" IS present
        # Verify "Iteration" is NOT present
        ...

    def test_reuse_validation_message_hidden(self, capsys):
        """'Reusing post-correction validation' should not appear."""
        # Setup runner, capture output
        # Verify "Reusing" is NOT in output
        ...
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_loop_runner.py::TestReadableOutput -v`
Expected: FAIL

**Step 3: Implement the output changes**

In `loop_runner.py`, modify the main `run()` method:

**Line 283-285** — Replace iteration header:
```python
# OLD:
self.console.print(f"\n[bold cyan]─── Iteration {iteration_num} ───[/bold cyan]")

# NEW:
if iteration_num == 0:
    # Initial validation — no "iteration" number shown
    pass  # Header printed by _display_initial_validation below
else:
    correction_num = iteration_num
    self.console.print(
        f"\n[bold cyan]Correction {correction_num} of "
        f"{self.config.max_iterations}[/bold cyan]"
    )
```

**Line 345-355** — Remove "Reusing post-correction validation" and "Saved validation" messages (keep only in verbose mode):
```python
# Validation file saving — only show in verbose mode
if self.config.verbose:
    self.console.print(f"[dim]Saved validation: {validation_path}[/dim]")

# ...

# Reusing validation — only show in verbose mode
if self.config.verbose:
    self.console.print(
        f"[dim]Reusing post-correction validation for iteration {iteration_num}[/dim]"
    )
```

**Line 393-396** — Remove separate "Running correction" line (correction is announced by the "Correction N of M" header):
```python
# OLD:
self.console.print(
    f"\n[yellow]Running correction (iteration {iteration_num})...[/yellow]"
)

# NEW: Only show in verbose mode
if self.config.verbose:
    self.console.print(
        f"\n[yellow]Running correction (iteration {iteration_num})...[/yellow]"
    )
```

**`_display_quality_scores`** — Replace "Iteration N:" prefix with contextual label:
```python
# OLD:
f"[cyan]Iteration {iteration_num}:[/cyan] "
f"Quality {metrics.quality_score:.1%}{delta_str} | "
f"Schema {metrics.schema_compliance_score:.1%} | "
f"Complete {metrics.completeness_score:.1%} | "
f"{status_str}"

# NEW: This method is only called after validation completes.
# For iteration 0, it's the initial quality line.
# For iteration 1+, it's the post-correction quality.
# The caller (run()) now handles headers, so this just shows metrics.
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_loop_runner.py::TestReadableOutput -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `make test-fast`
Expected: All pass (existing tests may need assertion updates for changed output)

**Step 6: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py tests/unit/test_loop_runner.py
git commit -m "feat: replace iteration headers with 'Correction N of M' format"
```

---

### Task 3: Add compact before→after quality display in `loop_runner.py`

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py` (new `_display_before_after_quality` method)
- Test: `tests/unit/test_loop_runner.py`

After a correction completes, `loop_runner.py` should display a compact before→after block. Currently, the detailed pre/post correction output is in `steps/validation.py:280-454`. We add a compact version in `loop_runner.py` and suppress the verbose step-level output (Task 4).

**Step 1: Write failing test**

```python
def test_before_after_quality_displayed(self, capsys):
    """After correction, should show before→after per metric."""
    # Setup runner with 1 correction
    # Capture output
    # Verify lines like "Schema: 84.9% → 100.0% (+15.1%)" appear
    ...
```

**Step 2: Implement `_display_before_after_quality` method**

Add new method to `IterativeLoopRunner`:

```python
def _display_before_after_quality(
    self,
    before_metrics: QualityMetrics,
    after_metrics: QualityMetrics,
) -> None:
    """Display compact before→after quality comparison."""
    metrics_to_show = [
        ("Schema", before_metrics.schema_compliance_score, after_metrics.schema_compliance_score),
        ("Completeness", before_metrics.completeness_score, after_metrics.completeness_score),
        ("Accuracy", before_metrics.accuracy_score, after_metrics.accuracy_score),
    ]

    for name, before, after in metrics_to_show:
        # Skip metrics that are None (not all loop types have all metrics)
        if before is None or after is None:
            continue
        delta = after - before
        if abs(delta) < 0.001:
            continue  # Skip unchanged metrics
        color = "green" if delta > 0 else "red"
        self.console.print(
            f"  {name}: {before:.1%} → {after:.1%} [{color}]({delta:+.1%})[/{color}]"
        )

    # Overall quality line with pass/fail indicator
    q_delta = after_metrics.quality_score - before_metrics.quality_score
    color = "green" if q_delta >= 0 else "red"
    meets = is_quality_sufficient_from_metrics(after_metrics, self.thresholds)
    suffix = " ✅" if meets else ""
    self.console.print(
        f"  Quality: {before_metrics.quality_score:.1%} → "
        f"{after_metrics.quality_score:.1%} [{color}]({q_delta:+.1%})[/{color}]{suffix}"
    )
```

Call this in `run()` after the corrected quality is compared (around line 454-468), replacing the step-level pre/post blocks:

```python
if corrected_metrics.quality_score >= best_so_far_metrics.quality_score:
    # Accepted — show before→after
    if not self.config.verbose:
        self._display_before_after_quality(best_so_far_metrics, corrected_metrics)
    ...
else:
    # Degraded — show rollback line
    if not self.config.verbose:
        self.console.print(
            f"  Quality: {best_so_far_metrics.quality_score:.1%} → "
            f"{corrected_metrics.quality_score:.1%} "
            f"[red]({corrected_metrics.quality_score - best_so_far_metrics.quality_score:+.1%})[/red]"
            f" — reverting to best"
        )
```

**Step 3: Run tests**

Run: `pytest tests/unit/test_loop_runner.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py tests/unit/test_loop_runner.py
git commit -m "feat: add compact before→after quality display in loop runner"
```

---

### Task 4: Suppress verbose step-level output when `verbose=False`

**Files:**
- Modify: `src/pipeline/validation_runner.py:93-170` (extraction validation detail)
- Modify: `src/pipeline/steps/validation.py:275-454` (correction pre/post blocks)
- Modify: `src/pipeline/steps/appraisal.py:238-271, 325-366` (appraisal validation/correction)
- Modify: `src/pipeline/steps/report.py` (report validation/correction, same pattern)
- Test: `tests/unit/test_loop_runner.py`

**Approach:** Pass a `verbose` flag (or a `quiet_console` that swallows output) through to the step functions. When `verbose=False`, the step functions suppress their banner headers, quality detail blocks, and per-metric output — but still print single-line progress indicators ("Validating...", "Correcting...", "Validating...") on the same line for the compact format.

**Option A (recommended):** Create a `QuietConsole` wrapper that suppresses `console.print()` calls in step functions. The loop runner passes either the real console or the quiet console depending on `verbose`. This avoids modifying every step function signature.

**Option B:** Add a `verbose` parameter to each step function (`run_dual_validation`, `run_extraction_correction_step`, `run_appraisal_validation_step`, etc.).

**Recommendation: Option A** — less invasive, fewer signature changes.

**Step 1: Create `QuietConsole` in `loop_runner.py`**

```python
class _QuietConsole:
    """Console wrapper that suppresses output. Used when verbose=False."""

    def print(self, *args, **kwargs):
        pass  # Swallow all output

    def __getattr__(self, name):
        return lambda *args, **kwargs: None
```

**Step 2: Pass quiet console to step functions**

In `loop_runner.py`, when calling `self.validate_fn()` and `self.correct_fn()`, the step functions use a module-level `console` variable. We need the step-setup code (in `steps/validation.py`, `steps/appraisal.py`) to respect a console override.

Actually, looking at the code more carefully: the step functions (`run_dual_validation`, `run_extraction_correction_step`, etc.) use their own module-level `console = Console()`. The `IterativeLoopRunner` has its own `self.console`.

**Revised approach:** The cleanest way is to have the loop runner print its own compact output, and suppress step-level output by temporarily replacing the module-level console in the step modules. However, this is fragile.

**Better revised approach:** Add an optional `console` parameter to the step functions that defaults to the module-level console. The loop runner's callback wrappers (in `steps/validation.py:564+` and `steps/appraisal.py`) pass the quiet console when `verbose=False`.

This requires:
1. Add `console` parameter to: `run_dual_validation()`, `run_extraction_correction_step()`, `run_appraisal_validation_step()`, `run_appraisal_correction_step()`, `run_report_validation_step()`, `run_report_correction_step()`
2. In each function, use the passed console instead of the module-level one
3. In the callback wrappers (the closures inside the `run_iterative_*` functions), pass `quiet_console` when verbose is False

**Step 1: Write failing test**

```python
def test_verbose_false_suppresses_step_detail(self, capsys):
    """When verbose=False, step-level detail blocks should not appear."""
    # Setup runner with verbose=False (default)
    # Capture output
    # Verify "═══ VALIDATION ═══" is NOT present
    # Verify "Pre-Correction Quality:" is NOT present
    # Verify "Post-Correction Quality:" is NOT present
    ...

def test_verbose_true_shows_step_detail(self, capsys):
    """When verbose=True, step-level detail blocks should appear."""
    # Setup runner with verbose=True
    # Capture output
    # Verify "═══ VALIDATION ═══" IS present
    ...
```

**Step 2: Implement console parameter threading**

For each step function, add `console: Console | None = None` parameter:

```python
def run_dual_validation(
    extraction_result, pdf_path, max_pages, publication_type, llm,
    console=None,  # NEW
    ...
):
    if console is None:
        console = _module_console  # Use module-level default
    ...
```

In the loop setup functions (e.g., `run_iterative_validation_correction` in `steps/validation.py:550+`), create the quiet console and pass it:

```python
from ...pipeline.iterative.loop_runner import _QuietConsole

quiet = _QuietConsole() if not verbose else None

def validate_fn(extraction):
    return run_validation_step(
        ...,
        console=quiet,  # Suppress step-level output
    )
```

**Step 3: Add inline progress indicators**

When `verbose=False`, the loop runner should print inline progress dots during validation and correction. Add spinner-style output in `run()`:

```python
# Before calling validate_fn:
if not self.config.verbose:
    self.console.print("  Validating...", end=" ")

# Before calling correct_fn:
if not self.config.verbose:
    self.console.print("correcting...", end=" ")

# After post-correction validation:
if not self.config.verbose:
    self.console.print("validating...", end="")
    self.console.print()  # Newline
```

This produces: `  Validating... correcting... validating...` on one line.

**Step 4: Run tests**

Run: `make test-fast`
Expected: All pass

**Step 5: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py src/pipeline/validation_runner.py \
    src/pipeline/steps/validation.py src/pipeline/steps/appraisal.py \
    src/pipeline/steps/report.py tests/unit/test_loop_runner.py
git commit -m "feat: suppress verbose step output, add inline progress indicators"
```

---

### Task 5: Improve failure/retry and rollback messages

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py:420-506` (failure, retry, rollback messages)
- Test: `tests/unit/test_loop_runner.py`

**Step 1: Write failing tests**

```python
class TestReadableFailureMessages:
    """Test human-readable failure and retry messages."""

    def test_schema_failure_shows_plain_language(self, capsys):
        """Schema failure should say 'Produced invalid output' not 'Correction failed schema validation'."""
        ...

    def test_rollback_shows_reverting(self, capsys):
        """Rollback should say 'reverting to best' not technical details."""
        ...

    def test_consecutive_rollback_shows_stopping(self, capsys):
        """Consecutive rollbacks should say 'stopping early'."""
        ...
```

**Step 2: Update messages**

```python
# Line 422-425 — Schema failure (when verbose=False):
if not self.config.verbose:
    self.console.print("  ✗ Produced invalid output — retrying")
else:
    self.console.print(
        f"[red]Correction failed schema validation "
        f"(quality: {schema_quality:.2f})[/red]"
    )

# Line 444-448 — Retry message: suppress when not verbose (the "retrying" is already shown above)
if self.config.verbose:
    self.console.print(
        f"[yellow]Retrying correction from last good iteration "
        f"(retry {correction_retry_count}/{self.config.max_correction_retries})...[/yellow]"
    )

# Line 471-476 — Rollback (when verbose=False, handled in Task 3's before→after display)
# The "— reverting to best" suffix is already added in Task 3

# Line 502-506 — Consecutive rollbacks:
if not self.config.verbose:
    self.console.print(
        f"  ⚠ {consecutive_rollbacks} consecutive corrections degraded quality — stopping early"
    )
else:
    self.console.print(
        f"\n[yellow]⚠️ {consecutive_rollbacks} consecutive corrections "
        f"degraded quality. Stopping early.[/yellow]"
    )
```

**Step 3: Run tests**

Run: `make test-fast`
Expected: All pass

**Step 4: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py tests/unit/test_loop_runner.py
git commit -m "feat: use plain language for failure, retry, and rollback messages"
```

---

### Task 6: Improve final status summary lines

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py:593-682` (final result methods)
- Test: `tests/unit/test_loop_runner.py`

Replace technical final status messages with clear summaries.

**Step 1: Write failing tests**

```python
class TestReadableFinalStatus:
    def test_success_shows_correction_count(self, capsys):
        """Success should say 'Passed after N corrections' not 'Quality sufficient at iteration N'."""
        ...

    def test_early_stop_shows_best_result(self, capsys):
        """Early stop should show which result was selected and its quality."""
        ...
```

**Step 2: Update final status messages**

```python
# _create_success_result (line 597):
if not self.config.verbose:
    corrections = iteration_num  # iteration 0 = no corrections, 1 = 1 correction, etc.
    if corrections == 0:
        self.console.print("\n[green]✅ Passed on initial validation[/green]")
    else:
        self.console.print(f"\n[green]✅ Passed after {corrections} correction{'s' if corrections > 1 else ''}[/green]")
else:
    self.console.print(f"\n[green]✅ Quality sufficient at iteration {iteration_num}[/green]")

# _create_early_stop_result (line 620-623):
if not self.config.verbose:
    best_quality = ...  # extract from best iteration
    self.console.print(f"\n[yellow]✅ Best result: iteration {best['iteration_num']} ({best_quality:.1%})[/yellow]")
else:
    # Keep existing verbose output
    ...

# _create_max_iterations_result (line 646-649):
if not self.config.verbose:
    self.console.print(f"\n[yellow]⚠ Reached max corrections ({self.config.max_iterations}) — using best result[/yellow]")
else:
    # Keep existing verbose output
    ...

# Suppress "Best result saved" / "Best validation saved" file paths when not verbose:
if self.config.verbose and result_path:
    self.console.print(f"[green]✅ Best result saved: {result_path}[/green]")
if self.config.verbose and validation_path:
    self.console.print(f"[green]✅ Best validation saved: {validation_path}[/green]")
```

**Step 3: Run tests**

Run: `make test-fast`
Expected: All pass

**Step 4: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py tests/unit/test_loop_runner.py
git commit -m "feat: improve final status summary lines for readability"
```

---

### Task 7: Wire `verbose` flag through to CLI and Streamlit

**Files:**
- Modify: `src/pipeline/steps/validation.py:550-630` (extraction loop setup)
- Modify: `src/pipeline/steps/appraisal.py:130-220` (appraisal loop setup)
- Modify: `src/pipeline/steps/report.py` (report loop setup)
- Modify: `src/pipeline/orchestrator.py` (if it passes config)
- Modify: `run_pipeline.py` (CLI entry point — add `--verbose` flag)
- Test: `tests/unit/test_loop_runner.py`

**Step 1: Add `--verbose` CLI flag**

In `run_pipeline.py`, add:
```python
parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed validation/correction output")
```

**Step 2: Thread `verbose` through pipeline**

The `verbose` flag needs to reach `IterativeLoopConfig`. Each `run_iterative_*` function in the step modules creates the config. Add `verbose` parameter to these functions and pass it through to the config.

**Step 3: Streamlit default**

Streamlit should default to `verbose=False` (compact output in the UI). The Streamlit runner already passes settings; add verbose to settings if needed, or just hardcode `verbose=False`.

**Step 4: Run full test suite**

Run: `make test-fast`
Expected: All pass

**Step 5: Commit**

```bash
git add run_pipeline.py src/pipeline/steps/validation.py src/pipeline/steps/appraisal.py \
    src/pipeline/steps/report.py src/pipeline/orchestrator.py tests/
git commit -m "feat: wire verbose flag through CLI and Streamlit"
```

---

### Task 8: Suppress initial validation detail block when `verbose=False`

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py:292-350` (initial validation section)
- Modify: `src/pipeline/validation_runner.py:93-170` (validation detail block)

The initial validation (iteration 0) currently prints a full `═══ VALIDATION ═══` block from `validation_runner.py`. When `verbose=False`, this should be replaced by a single compact line from `loop_runner.py`:

```
Validating extraction...
  Schema: 84.9% | Completeness: 83.0% | Accuracy: 99.0% → Quality: 89.8%
  ⚠ Below 95% threshold — running correction
```

This is handled by:
1. Passing quiet console to `validate_fn` (done in Task 4)
2. The loop runner printing the compact line after validation returns (using `_display_quality_scores` or a new `_display_initial_quality` method)

**Step 1: Add `_display_initial_quality` method**

```python
def _display_initial_quality(self, metrics: QualityMetrics) -> None:
    """Display compact initial validation quality."""
    parts = []
    if metrics.schema_compliance_score is not None:
        parts.append(f"Schema: {metrics.schema_compliance_score:.1%}")
    if metrics.completeness_score is not None:
        parts.append(f"Completeness: {metrics.completeness_score:.1%}")
    if metrics.accuracy_score is not None:
        parts.append(f"Accuracy: {metrics.accuracy_score:.1%}")

    metrics_line = " | ".join(parts)
    self.console.print(f"  {metrics_line} → Quality: {metrics.quality_score:.1%}")

    meets = is_quality_sufficient_from_metrics(metrics, self.thresholds)
    if meets:
        # Will proceed to success path
        pass
    else:
        threshold_pct = f"{self.thresholds.min_quality:.0%}" if self.thresholds.min_quality else "threshold"
        self.console.print(f"  ⚠ Below {threshold_pct} — running correction")
```

**Step 2: Wire into `run()` after initial validation**

After `validation_result = self.validate_fn(current_result)` succeeds:

```python
if not self.config.verbose:
    self.console.print(f"\nValidating {self.config.step_name.lower().split()[0]}...")
    initial_metrics = extract_metrics(validation_result, self.config.metric_type)
    self._display_initial_quality(initial_metrics)
```

**Step 3: Run tests**

Run: `make test-fast`
Expected: All pass

**Step 4: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py tests/unit/test_loop_runner.py
git commit -m "feat: add compact initial validation display"
```

---

### Task 9: Update existing tests for new output format

**Files:**
- Modify: `tests/unit/test_loop_runner.py` (update any tests that assert on console output text)
- Modify: `tests/unit/test_iterative_validation_correction.py` (if it checks output)
- Modify: `tests/integration/test_appraisal_full_loop.py` (if it checks output)

**Step 1: Search for tests that assert on console output**

Look for tests that capture `capsys` or check for strings like "Iteration", "Reusing", "Running correction", etc.

**Step 2: Update assertions**

Update any affected tests to match the new output format. Tests that don't check console output should be unaffected.

**Step 3: Run full suite**

Run: `make ci`
Expected: All 542+ tests pass

**Step 4: Commit**

```bash
git add tests/
git commit -m "test: update test assertions for new readable output format"
```

---

### Task 10: Update CHANGELOG and documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/plans/2026-02-18-readable-loop-output.md` (mark status complete)

**Step 1: Update CHANGELOG**

Under `[Unreleased] > Changed`:
```markdown
- Iterative correction loop console output redesigned for readability: "Correction N of M" format with compact before→after quality deltas, plain-language failure messages, and `--verbose` flag for detailed debugging output
```

**Step 2: Commit**

```bash
git add CHANGELOG.md docs/plans/2026-02-18-readable-loop-output.md
git commit -m "docs: add readable loop output changelog entry"
```
