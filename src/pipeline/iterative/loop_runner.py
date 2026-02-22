"""
Generic iterative correction loop runner.

This module provides the IterativeLoopRunner class that consolidates the
three nearly-identical iterative correction loops in orchestrator.py:
- run_validation_with_correction (extraction)
- run_appraisal_with_correction
- run_report_with_correction

The runner uses callback functions to customize behavior for each loop type
while sharing the common iteration logic.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from rich.console import Console

from ..quality.metrics import MetricType, QualityMetrics, extract_metrics
from ..quality.scoring import select_best_iteration
from ..quality.thresholds import (
    QualityThresholds,
    get_thresholds_for_type,
    is_quality_sufficient,
    is_quality_sufficient_from_metrics,
)
from .iteration_tracker import IterationTracker

# Default console for output
console = Console()


# Final status codes (matching orchestrator.py)
FINAL_STATUS_PASSED = "passed"
FINAL_STATUS_MAX_ITERATIONS = "max_iterations_reached"
FINAL_STATUS_EARLY_STOPPED = "early_stopped_degradation"
FINAL_STATUS_FAILED = "failed"
FINAL_STATUS_FAILED_SCHEMA = "failed_schema_validation"

# Maximum consecutive rollbacks before early exit (stuck loop detection)
MAX_CONSECUTIVE_ROLLBACKS = 2


class ValidateFunc(Protocol):
    """Protocol for validation function."""

    def __call__(self, result: dict) -> dict:
        """Validate a result and return validation dict."""
        ...


class CorrectFunc(Protocol):
    """Protocol for correction function."""

    def __call__(self, result: dict, validation: dict) -> dict | tuple[dict, dict]:
        """Correct a result based on validation feedback.

        Returns either:
        - dict: corrected result only (loop will re-validate)
        - tuple[dict, dict]: (corrected result, validation) to skip re-validation
        """
        ...


class SaveIterationFunc(Protocol):
    """Protocol for saving iteration files."""

    def __call__(
        self, iteration_num: int, result: dict, validation: dict
    ) -> tuple[Path | None, Path | None]:
        """Save iteration files, return (result_path, validation_path)."""
        ...


class SaveBestFunc(Protocol):
    """Protocol for saving best result files."""

    def __call__(self, result: dict, validation: dict) -> tuple[Path | None, Path | None]:
        """Save best result files, return (result_path, validation_path)."""
        ...


class RegenerateInitialFunc(Protocol):
    """Protocol for regenerating the initial result when it fails schema validation."""

    def __call__(self) -> dict:
        """Regenerate the initial result."""
        ...


class SaveFailedFunc(Protocol):
    """Protocol for saving failed result files for debugging."""

    def __call__(self, result: dict, validation: dict) -> tuple[Path | None, Path | None]:
        """Save failed result files for debugging, return (result_path, validation_path)."""
        ...


@dataclass
class IterativeLoopConfig:
    """
    Configuration for an iterative correction loop.

    Attributes:
        metric_type: Type of metrics (EXTRACTION, APPRAISAL, REPORT)
        max_iterations: Maximum correction attempts (default: 3)
        quality_thresholds: Custom thresholds (uses defaults if None)
        degradation_window: Consecutive degrading iterations for early stop
        step_name: Display name for the step (e.g., "VALIDATION & CORRECTION")
        result_key: Key name for result in output (e.g., "best_extraction")
        quality_score_key: Key for quality score display (e.g., "overall_quality")
        max_correction_retries: Max retries when correction fails schema validation
        max_initial_retries: Max retries when initial result fails schema validation
    """

    metric_type: MetricType
    max_iterations: int = 3
    quality_thresholds: QualityThresholds | None = None
    degradation_window: int = 2
    step_name: str = "ITERATIVE LOOP"
    result_key: str = "best_result"
    quality_score_key: str = "quality_score"
    show_banner: bool = True
    step_number: int = 3  # For display purposes
    max_correction_retries: int = 2  # Max retries per correction when schema fails
    max_initial_retries: int = 2  # Max retries for initial result schema failure
    verbose: bool = False  # Show detailed validation/correction output (debugging)


@dataclass
class IterativeLoopResult:
    """
    Result from an iterative correction loop.

    This structure matches the return format of the existing
    run_*_with_correction functions for backward compatibility.
    """

    best_result: dict | None
    best_validation: dict | None
    iterations: list[dict]
    final_status: str
    iteration_count: int
    improvement_trajectory: list[float] = field(default_factory=list)
    best_iteration_num: int = 0
    selection_reason: str = ""
    error: str | None = None
    warning: str | None = None
    failed_at_iteration: int | None = None

    def to_dict(self, result_key: str = "best_result") -> dict:
        """
        Convert to dict for backward compatibility.

        Args:
            result_key: Key name for the best result (e.g., "best_extraction")
        """
        result = {
            result_key: self.best_result,
            "best_validation": self.best_validation,
            "iterations": self.iterations,
            "final_status": self.final_status,
            "iteration_count": self.iteration_count,
            "improvement_trajectory": self.improvement_trajectory,
        }

        if self.error:
            result["error"] = self.error
        if self.failed_at_iteration is not None:
            result["failed_at_iteration"] = self.failed_at_iteration
        if self.best_iteration_num is not None:
            result["best_iteration"] = self.best_iteration_num
        if self.warning:
            result["warning"] = self.warning

        return result


class IterativeLoopRunner:
    """
    Generic runner for iterative validation/correction loops.

    This class encapsulates the common loop logic shared by extraction,
    appraisal, and report correction loops. It uses callback functions
    to customize the validate, correct, and save operations for each type.

    Example:
        >>> config = IterativeLoopConfig(
        ...     metric_type=MetricType.EXTRACTION,
        ...     max_iterations=3,
        ...     step_name="VALIDATION & CORRECTION",
        ... )
        >>> runner = IterativeLoopRunner(
        ...     config=config,
        ...     initial_result=extraction_result,
        ...     validate_fn=lambda r: validate_extraction(r, pdf_path, llm),
        ...     correct_fn=lambda r, v: correct_extraction(r, v, pdf_path, llm),
        ...     save_iteration_fn=lambda i, r, v: file_manager.save_iteration(i, r, v),
        ...     save_best_fn=lambda r, v: file_manager.save_best(r, v),
        ... )
        >>> result = runner.run()
        >>> result.final_status
        'passed'
    """

    def __init__(
        self,
        config: IterativeLoopConfig,
        initial_result: dict,
        validate_fn: ValidateFunc,
        correct_fn: CorrectFunc,
        save_iteration_fn: SaveIterationFunc | None = None,
        save_best_fn: SaveBestFunc | None = None,
        regenerate_initial_fn: RegenerateInitialFunc | None = None,
        save_failed_fn: SaveFailedFunc | None = None,
        progress_callback: Callable | None = None,
        console_instance: Console | None = None,
        check_schema_quality: bool = True,
        schema_quality_threshold: float = 0.5,
    ):
        """
        Initialize the loop runner.

        Args:
            config: Loop configuration
            initial_result: Initial result to validate/correct
            validate_fn: Function to validate a result
            correct_fn: Function to correct a result based on validation
            save_iteration_fn: Optional function to save iteration files
            save_best_fn: Optional function to save best result files
            regenerate_initial_fn: Optional function to regenerate initial result on schema failure
            save_failed_fn: Optional function to save failed results for debugging
            progress_callback: Optional callback for progress updates
            console_instance: Console for output (uses default if None)
            check_schema_quality: Whether to check schema quality threshold
            schema_quality_threshold: Minimum schema quality to continue
        """
        self.config = config
        self.initial_result = initial_result
        self.validate_fn = validate_fn
        self.correct_fn = correct_fn
        self.save_iteration_fn = save_iteration_fn
        self.save_best_fn = save_best_fn
        self.regenerate_initial_fn = regenerate_initial_fn
        self.save_failed_fn = save_failed_fn
        self.progress_callback = progress_callback
        self.console = console_instance or console
        self.check_schema_quality = check_schema_quality
        self.schema_quality_threshold = schema_quality_threshold

        # Get thresholds
        self.thresholds = config.quality_thresholds or get_thresholds_for_type(config.metric_type)

        # Initialize tracker
        self.tracker = IterationTracker(
            metric_type=config.metric_type,
            degradation_window=config.degradation_window,
        )

    def run(self) -> IterativeLoopResult:
        """
        Execute the iterative correction loop.

        Returns:
            IterativeLoopResult with best result, validation, and history
        """
        current_result = self.initial_result
        current_validation = None
        iteration_num = 0

        # Track last good result/validation for retry on schema failure
        last_good_result = self.initial_result
        last_good_validation: dict | None = None
        correction_retry_count = 0
        previous_failure_hints: str | None = None
        consecutive_rollbacks = 0

        # Display header
        if self.config.show_banner:
            self._display_header()

        while iteration_num <= self.config.max_iterations:
            # Display iteration header
            if self.config.verbose:
                self.console.print(f"\n[bold cyan]─── Iteration {iteration_num} ───[/bold cyan]")
            elif iteration_num == 0:
                self.console.print("\n[bold cyan]─── Initial Validation ───[/bold cyan]")
            else:
                self.console.print(
                    f"\n[bold cyan]─── Correction {iteration_num} of "
                    f"{self.config.max_iterations} ───[/bold cyan]"
                )

            try:
                # Call progress callback
                self._call_progress("starting", iteration_num, "validation")

                # STEP 1: Validate current result
                if current_validation is None:
                    # Initial validation with retry support for schema failures
                    initial_retry_count = 0
                    while True:
                        validation_result = self.validate_fn(current_result)

                        # Check schema quality (critical failure)
                        if self.check_schema_quality:
                            schema_quality = self._get_schema_quality(validation_result)
                            if schema_quality < self.schema_quality_threshold:
                                initial_retry_count += 1
                                if self.config.verbose:
                                    self.console.print(
                                        f"[red]Initial result failed schema validation "
                                        f"(quality: {schema_quality:.2f})[/red]"
                                    )
                                else:
                                    self.console.print(
                                        "  [red]✗ Initial result invalid — retrying[/red]"
                                    )

                                # Can we retry?
                                if (
                                    initial_retry_count > self.config.max_initial_retries
                                    or self.regenerate_initial_fn is None
                                ):
                                    if initial_retry_count >= self.config.max_initial_retries:
                                        if self.config.verbose:
                                            self.console.print(
                                                f"[red]Max initial retries "
                                                f"({self.config.max_initial_retries}) reached[/red]"
                                            )
                                        else:
                                            self.console.print(
                                                "  [red]✗ Could not produce valid initial result[/red]"
                                            )
                                    # Save failed result for debugging
                                    if self.save_failed_fn:
                                        self.save_failed_fn(current_result, validation_result)
                                        if self.config.verbose:
                                            self.console.print(
                                                "[dim]Saved failed result for debugging[/dim]"
                                            )
                                    return self._create_schema_failure_result(
                                        validation_result, iteration_num, schema_quality
                                    )

                                # Retry: regenerate initial result
                                if self.config.verbose:
                                    self.console.print(
                                        f"[yellow]Retrying initial generation "
                                        f"(retry {initial_retry_count}/"
                                        f"{self.config.max_initial_retries})...[/yellow]"
                                    )
                                current_result = self.regenerate_initial_fn()
                                continue  # Retry validation

                        # Schema check passed, exit retry loop
                        break

                    # Update last good after successful schema validation
                    last_good_result = current_result
                    last_good_validation = validation_result

                    # Save iteration files
                    if self.save_iteration_fn:
                        result_path, validation_path = self.save_iteration_fn(
                            iteration_num, current_result, validation_result
                        )
                        if validation_path and self.config.verbose:
                            self.console.print(f"[dim]Saved validation: {validation_path}[/dim]")
                else:
                    validation_result = current_validation
                    if self.config.verbose:
                        self.console.print(
                            f"[dim]Reusing post-correction validation for iteration "
                            f"{iteration_num}[/dim]"
                        )

                # Extract and store metrics
                metrics = extract_metrics(validation_result, self.config.metric_type)
                self.tracker.add_iteration(
                    result=current_result,
                    validation=validation_result,
                    metrics=metrics,
                )

                # Display quality scores
                if not self.config.verbose and iteration_num == 0:
                    self._display_initial_quality(metrics)
                else:
                    self._display_quality_scores(metrics, iteration_num)

                # STEP 2: Check if quality is sufficient
                if is_quality_sufficient(
                    validation_result, self.config.metric_type, self.thresholds
                ):
                    return self._create_success_result(
                        current_result, validation_result, iteration_num
                    )

                # STEP 3: Check for quality degradation (early stopping)
                # NOTE: With best-so-far rollback active, accepted iterations have
                # monotonically non-decreasing quality, so degradation detection
                # rarely fires. Kept as a safety net for edge cases.
                if self.tracker.detect_degradation():
                    return self._create_early_stop_result()

                # STEP 4: Check max iterations
                if iteration_num >= self.config.max_iterations:
                    return self._create_max_iterations_result()

                # STEP 5: Run correction
                # Reset correction retry count only for NEW corrections (not retries)
                # We detect a retry by checking if we reused the validation (current_validation was not None)
                is_retry = current_validation is not None
                if not is_retry:
                    correction_retry_count = 0
                self._call_progress("starting", iteration_num, "correction")
                if self.config.verbose:
                    self.console.print(
                        f"\n[yellow]Running correction (iteration {iteration_num})...[/yellow]"
                    )

                # Inject correction hints if available from previous failure
                correction_validation = validation_result
                if previous_failure_hints:
                    correction_validation = {
                        **validation_result,
                        "_correction_hints": previous_failure_hints,
                    }

                correction_output = self.correct_fn(current_result, correction_validation)

                # Support both return styles: dict or (dict, dict) tuple
                if isinstance(correction_output, tuple):
                    corrected_result, corrected_validation = correction_output
                    if corrected_validation is None:
                        corrected_validation = self.validate_fn(corrected_result)
                else:
                    corrected_result = correction_output
                    corrected_validation = self.validate_fn(corrected_result)

                # Check schema quality of correction
                if self.check_schema_quality:
                    schema_quality = self._get_schema_quality(corrected_validation)
                    if schema_quality < self.schema_quality_threshold:
                        correction_retry_count += 1
                        if self.config.verbose:
                            self.console.print(
                                f"[red]Correction failed schema validation "
                                f"(quality: {schema_quality:.2f})[/red]"
                            )
                        else:
                            self.console.print("  [red]✗ Produced invalid output — retrying[/red]")

                        if correction_retry_count > self.config.max_correction_retries:
                            if self.config.verbose:
                                self.console.print(
                                    f"[red]Max correction retries "
                                    f"({self.config.max_correction_retries}) reached[/red]"
                                )
                            else:
                                self.console.print(
                                    "  [red]✗ Could not produce valid correction[/red]"
                                )
                            # Always save failed result for debugging
                            if self.save_failed_fn:
                                self.save_failed_fn(corrected_result, corrected_validation)
                                if self.config.verbose:
                                    self.console.print(
                                        "[dim]Saved failed result for debugging[/dim]"
                                    )
                            # Return best result we have so far, or fail
                            if self.tracker.iteration_count > 0:
                                return self._create_max_iterations_result()
                            return self._create_schema_failure_result(
                                corrected_validation, iteration_num, schema_quality
                            )

                        # Retry: reset to last good and try again
                        if self.config.verbose:
                            self.console.print(
                                f"[yellow]Retrying correction from last good iteration "
                                f"(retry {correction_retry_count}/"
                                f"{self.config.max_correction_retries})...[/yellow]"
                            )
                        current_result = last_good_result
                        current_validation = last_good_validation
                        iteration_num += 1
                        continue  # Retry the loop

                # Compare corrected quality against best-so-far
                corrected_metrics = extract_metrics(corrected_validation, self.config.metric_type)
                best_so_far_metrics = extract_metrics(last_good_validation, self.config.metric_type)

                if corrected_metrics.quality_score >= best_so_far_metrics.quality_score:
                    # Correction improved or maintained quality — accept it
                    if not self.config.verbose:
                        self._display_before_after_quality(best_so_far_metrics, corrected_metrics)
                    last_good_result = corrected_result
                    last_good_validation = corrected_validation
                    correction_retry_count = 0
                    previous_failure_hints = None  # Reset hints on success
                    consecutive_rollbacks = 0  # Reset on successful correction

                    # Update for next iteration
                    current_result = corrected_result
                    current_validation = corrected_validation
                else:
                    # Correction degraded quality — revert to best-so-far
                    if self.config.verbose:
                        self.console.print(
                            f"[yellow]⚠ Correction degraded quality "
                            f"({corrected_metrics.quality_score:.1%} < "
                            f"{best_so_far_metrics.quality_score:.1%}), "
                            f"reverting to best iteration for next attempt[/yellow]"
                        )
                    else:
                        q_delta = (
                            corrected_metrics.quality_score - best_so_far_metrics.quality_score
                        )
                        self.console.print(
                            f"  Quality: {best_so_far_metrics.quality_score:.1%} → "
                            f"{corrected_metrics.quality_score:.1%} "
                            f"[red]({q_delta:+.1%})[/red]"
                            f" — reverting to best"
                        )
                    # Reset retry count: next correction starts fresh from best-so-far,
                    # so previous schema-failure retries are no longer relevant.
                    correction_retry_count = 0

                    # Track the degraded iteration in history (for trajectory diagnostics)
                    self.tracker.add_iteration(
                        result=corrected_result,
                        validation=corrected_validation,
                        metrics=corrected_metrics,
                    )

                    # Build failure hints from the degraded correction's schema errors
                    degraded_errors = corrected_validation.get("schema_validation", {}).get(
                        "validation_errors", []
                    )
                    if degraded_errors:
                        error_summary = "; ".join(degraded_errors[:5])
                        previous_failure_hints = (
                            f"PREVIOUS CORRECTION FAILED. It introduced these schema errors: "
                            f"{error_summary}. Do NOT repeat these mistakes. "
                            f"Omit optional fields if you don't have valid values."
                        )

                    consecutive_rollbacks += 1
                    if consecutive_rollbacks >= MAX_CONSECUTIVE_ROLLBACKS:
                        if self.config.verbose:
                            self.console.print(
                                f"\n[yellow]⚠️ {consecutive_rollbacks} consecutive corrections "
                                f"degraded quality. Stopping early.[/yellow]"
                            )
                        else:
                            self.console.print(
                                f"  [yellow]⚠ {consecutive_rollbacks} consecutive corrections "
                                f"degraded quality — stopping early[/yellow]"
                            )
                        return self._create_early_stop_result()

                    # Revert to best-so-far for next correction attempt
                    current_result = last_good_result
                    current_validation = last_good_validation

                # Save corrected iteration (whether accepted or degraded)
                if self.save_iteration_fn:
                    self.save_iteration_fn(
                        iteration_num + 1, corrected_result, corrected_validation
                    )

                iteration_num += 1

            except Exception as e:
                self.console.print(f"[red]Error in iteration {iteration_num}: {e}[/red]")
                return self._create_error_result(str(e), iteration_num)

        # Should not reach here, but handle gracefully
        return self._create_max_iterations_result()

    def _display_header(self) -> None:
        """Display loop header with configuration."""
        self.console.print(
            f"\n[bold magenta]═══ STEP {self.config.step_number}: {self.config.step_name} ═══[/bold magenta]\n"
        )
        self.console.print(f"[blue]Max iterations: {self.config.max_iterations}[/blue]")

    def _display_quality_scores(self, metrics: QualityMetrics, iteration_num: int) -> None:
        """Display compact quality summary for current iteration."""
        # Show threshold-aware status instead of raw validation status
        meets_thresholds = is_quality_sufficient_from_metrics(metrics, self.thresholds)
        if meets_thresholds:
            status_str = "[green]Thresholds met[/green]"
        else:
            status_str = "[yellow]Below threshold[/yellow]"

        # Calculate improvement delta if not first iteration
        delta_str = ""
        if self.tracker.iteration_count > 1:
            prev_metrics = self.tracker.get_iteration(iteration_num - 1)
            if prev_metrics:
                prev_score = prev_metrics.metrics.quality_score
                delta = metrics.quality_score - prev_score
                if delta > 0:
                    delta_str = f" [green]↑{delta:+.1%}[/green]"
                elif delta < 0:
                    delta_str = f" [red]↓{delta:+.1%}[/red]"

        # Build prefix based on verbose mode
        if self.config.verbose:
            prefix = f"[cyan]Iteration {iteration_num}:[/cyan] "
        else:
            # Compact mode: header already shows "Correction N of M", no prefix needed
            prefix = "  "

        # Single-line output
        self.console.print(
            f"{prefix}"
            f"Quality {metrics.quality_score:.1%}{delta_str} | "
            f"Schema {metrics.schema_compliance_score:.1%} | "
            f"Complete {metrics.completeness_score:.1%} | "
            f"{status_str}"
        )

    def _display_initial_quality(self, metrics: QualityMetrics) -> None:
        """Display compact initial validation quality with threshold warning."""
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
        if not meets:
            self.console.print("  [yellow]⚠ Below threshold — running correction[/yellow]")

    def _display_before_after_quality(
        self,
        before_metrics: QualityMetrics,
        after_metrics: QualityMetrics,
    ) -> None:
        """Display compact before→after quality comparison after correction."""
        metrics_to_show = [
            (
                "Schema",
                before_metrics.schema_compliance_score,
                after_metrics.schema_compliance_score,
            ),
            ("Completeness", before_metrics.completeness_score, after_metrics.completeness_score),
            ("Accuracy", before_metrics.accuracy_score, after_metrics.accuracy_score),
        ]

        for name, before, after in metrics_to_show:
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

    def _get_schema_quality(self, validation_result: dict) -> float:
        """Get schema quality score from validation result.

        Supports both extraction (verification_summary) and appraisal (validation_summary)
        validation structures. Defaults to 0.0 if score is missing (fail-safe behavior).
        """
        # Try appraisal structure first (validation_summary)
        if "validation_summary" in validation_result:
            return validation_result["validation_summary"].get("schema_compliance_score", 0.0)

        # Fall back to extraction structure (verification_summary)
        if "verification_summary" in validation_result:
            return validation_result["verification_summary"].get("schema_compliance_score", 0.0)

        # No known structure found - fail-safe
        return 0.0

    def _call_progress(self, status: str, iteration: int, step: str) -> None:
        """Call progress callback if available."""
        if self.progress_callback:
            try:
                self.progress_callback(
                    self.config.step_name,
                    status,
                    {"iteration": iteration, "step": step},
                )
            except Exception:
                pass  # Ignore callback errors

    def _create_success_result(
        self, result: dict, validation: dict, iteration_num: int
    ) -> IterativeLoopResult:
        """Create result for successful quality pass."""
        if self.config.verbose:
            self.console.print(
                f"\n[green]✅ Quality sufficient at iteration {iteration_num}[/green]"
            )
        else:
            corrections = iteration_num
            if corrections == 0:
                self.console.print("\n[green]✅ Passed on initial validation[/green]")
            else:
                s = "s" if corrections > 1 else ""
                self.console.print(f"\n[green]✅ Passed after {corrections} correction{s}[/green]")

        # Save best files
        if self.save_best_fn:
            result_path, validation_path = self.save_best_fn(result, validation)
            if self.config.verbose:
                if result_path:
                    self.console.print(f"[green]✅ Best result saved: {result_path}[/green]")
                if validation_path:
                    self.console.print(
                        f"[green]✅ Best validation saved: {validation_path}[/green]"
                    )

        return IterativeLoopResult(
            best_result=result,
            best_validation=validation,
            iterations=self.tracker.to_legacy_list(),
            final_status=FINAL_STATUS_PASSED,
            iteration_count=iteration_num + 1,
            improvement_trajectory=self.tracker.get_quality_scores(),
            best_iteration_num=iteration_num,
            selection_reason="quality_sufficient",
        )

    def _create_early_stop_result(self) -> IterativeLoopResult:
        """Create result for early stopping due to quality degradation."""
        # Select best iteration
        best = select_best_iteration(self.tracker.to_legacy_list(), self.config.metric_type)
        best_quality = best.get("metrics", {}).get("quality_score", 0)

        if self.config.verbose:
            self.console.print(
                f"\n[yellow]⚠️ Quality degradation detected after "
                f"{self.tracker.iteration_count} iterations[/yellow]"
            )
            self.console.print("[yellow]Selecting best iteration from history...[/yellow]")
        else:
            label = f"iteration {best['iteration_num']}" if best["iteration_num"] > 0 else "initial"
            self.console.print(f"\n[yellow]✅ Best result: {label} ({best_quality:.1%})[/yellow]")

        # Save best files
        if self.save_best_fn:
            self.save_best_fn(best["result"], best["validation"])

        return IterativeLoopResult(
            best_result=best["result"],
            best_validation=best["validation"],
            iterations=self.tracker.to_legacy_list(),
            final_status=FINAL_STATUS_EARLY_STOPPED,
            iteration_count=self.tracker.iteration_count,
            improvement_trajectory=self.tracker.get_quality_scores(),
            best_iteration_num=best["iteration_num"],
            selection_reason=best.get("selection_reason", "early_stopped"),
            warning=f"Early stopping: quality degradation detected after {self.tracker.iteration_count} iterations",
        )

    def _create_max_iterations_result(self) -> IterativeLoopResult:
        """Create result for max iterations reached."""
        # Select best iteration
        best = select_best_iteration(self.tracker.to_legacy_list(), self.config.metric_type)

        if self.config.verbose:
            self.console.print(
                f"\n[yellow]⚠️ Max iterations ({self.config.max_iterations}) reached[/yellow]"
            )
            self.console.print("[yellow]Selecting best iteration from history...[/yellow]")
        else:
            self.console.print(
                f"\n[yellow]⚠ Reached max corrections ({self.config.max_iterations}) "
                f"— using best result[/yellow]"
            )

        # Save best files
        if self.save_best_fn:
            self.save_best_fn(best["result"], best["validation"])

        return IterativeLoopResult(
            best_result=best["result"],
            best_validation=best["validation"],
            iterations=self.tracker.to_legacy_list(),
            final_status=FINAL_STATUS_MAX_ITERATIONS,
            iteration_count=self.tracker.iteration_count,
            improvement_trajectory=self.tracker.get_quality_scores(),
            best_iteration_num=best["iteration_num"],
            selection_reason=best.get("selection_reason", "max_iterations"),
            warning=f"Max iterations ({self.config.max_iterations}) reached without meeting quality threshold",
        )

    def _create_schema_failure_result(
        self, validation: dict, iteration_num: int, schema_quality: float
    ) -> IterativeLoopResult:
        """Create result for schema validation failure."""
        if self.config.verbose:
            self.console.print(
                f"\n[red]❌ Schema validation failed (quality: {schema_quality:.2f})[/red]"
            )
        else:
            self.console.print("\n[red]❌ Failed — could not produce valid output[/red]")

        return IterativeLoopResult(
            best_result=None,
            best_validation=validation,
            iterations=self.tracker.to_legacy_list(),
            final_status=FINAL_STATUS_FAILED_SCHEMA,
            iteration_count=iteration_num + 1,
            error=f"Schema validation failed (quality: {schema_quality:.2f}). Cannot proceed.",
            failed_at_iteration=iteration_num,
        )

    def _create_error_result(self, error: str, iteration_num: int) -> IterativeLoopResult:
        """Create result for unexpected error."""
        # Try to select best from what we have
        if self.tracker.iteration_count > 0:
            best = select_best_iteration(self.tracker.to_legacy_list(), self.config.metric_type)
            return IterativeLoopResult(
                best_result=best["result"],
                best_validation=best["validation"],
                iterations=self.tracker.to_legacy_list(),
                final_status=FINAL_STATUS_FAILED,
                iteration_count=self.tracker.iteration_count,
                error=error,
                failed_at_iteration=iteration_num,
            )

        return IterativeLoopResult(
            best_result=None,
            best_validation=None,
            iterations=[],
            final_status=FINAL_STATUS_FAILED,
            iteration_count=0,
            error=error,
            failed_at_iteration=iteration_num,
        )
