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


class ValidateFunc(Protocol):
    """Protocol for validation function."""

    def __call__(self, result: dict) -> dict:
        """Validate a result and return validation dict."""
        ...


class CorrectFunc(Protocol):
    """Protocol for correction function."""

    def __call__(self, result: dict, validation: dict) -> dict:
        """Correct a result based on validation feedback."""
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

        # Display header
        if self.config.show_banner:
            self._display_header()

        while iteration_num <= self.config.max_iterations:
            # Display iteration header
            self.console.print(f"\n[bold cyan]─── Iteration {iteration_num} ───[/bold cyan]")

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
                                self.console.print(
                                    f"[red]Initial result failed schema validation "
                                    f"(quality: {schema_quality:.2f})[/red]"
                                )

                                # Can we retry?
                                if (
                                    initial_retry_count > self.config.max_initial_retries
                                    or self.regenerate_initial_fn is None
                                ):
                                    if initial_retry_count >= self.config.max_initial_retries:
                                        self.console.print(
                                            f"[red]Max initial retries "
                                            f"({self.config.max_initial_retries}) reached[/red]"
                                        )
                                    # Save failed result for debugging
                                    if self.save_failed_fn:
                                        self.save_failed_fn(current_result, validation_result)
                                        self.console.print(
                                            "[dim]Saved failed result for debugging[/dim]"
                                        )
                                    return self._create_schema_failure_result(
                                        validation_result, iteration_num, schema_quality
                                    )

                                # Retry: regenerate initial result
                                self.console.print(
                                    f"[yellow]Retrying initial generation "
                                    f"(attempt {initial_retry_count + 1}/"
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
                        if validation_path:
                            self.console.print(f"[dim]Saved validation: {validation_path}[/dim]")
                else:
                    validation_result = current_validation
                    self.console.print(
                        f"[dim]Reusing post-correction validation for iteration {iteration_num}[/dim]"
                    )

                # Extract and store metrics
                metrics = extract_metrics(validation_result, self.config.metric_type)
                self.tracker.add_iteration(
                    result=current_result,
                    validation=validation_result,
                    metrics=metrics,
                )

                # Display quality scores
                self._display_quality_scores(metrics, iteration_num)

                # STEP 2: Check if quality is sufficient
                if is_quality_sufficient(
                    validation_result, self.config.metric_type, self.thresholds
                ):
                    return self._create_success_result(
                        current_result, validation_result, iteration_num
                    )

                # STEP 3: Check for quality degradation (early stopping)
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
                self.console.print(
                    f"\n[yellow]Running correction (iteration {iteration_num})...[/yellow]"
                )

                corrected_result = self.correct_fn(current_result, validation_result)

                # Validate corrected result immediately
                corrected_validation = self.validate_fn(corrected_result)

                # Check schema quality of correction
                if self.check_schema_quality:
                    schema_quality = self._get_schema_quality(corrected_validation)
                    if schema_quality < self.schema_quality_threshold:
                        correction_retry_count += 1
                        self.console.print(
                            f"[red]Correction failed schema validation "
                            f"(quality: {schema_quality:.2f})[/red]"
                        )

                        if correction_retry_count > self.config.max_correction_retries:
                            self.console.print(
                                f"[red]Max correction retries "
                                f"({self.config.max_correction_retries}) reached[/red]"
                            )
                            # Always save failed result for debugging
                            if self.save_failed_fn:
                                self.save_failed_fn(corrected_result, corrected_validation)
                                self.console.print("[dim]Saved failed result for debugging[/dim]")
                            # Return best result we have so far, or fail
                            if self.tracker.iteration_count > 0:
                                return self._create_max_iterations_result()
                            return self._create_schema_failure_result(
                                corrected_validation, iteration_num, schema_quality
                            )

                        # Retry: reset to last good and try again
                        self.console.print(
                            f"[yellow]Retrying correction from last good iteration "
                            f"(attempt {correction_retry_count + 1}/"
                            f"{self.config.max_correction_retries})...[/yellow]"
                        )
                        current_result = last_good_result
                        current_validation = last_good_validation
                        iteration_num += 1
                        continue  # Retry the loop

                # Correction succeeded - update last good state
                last_good_result = corrected_result
                last_good_validation = corrected_validation

                # Save corrected iteration
                if self.save_iteration_fn:
                    self.save_iteration_fn(
                        iteration_num + 1, corrected_result, corrected_validation
                    )

                # Update for next iteration
                current_result = corrected_result
                current_validation = corrected_validation
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
        """Display quality scores for current iteration."""
        self.console.print(f"\n[bold]Quality Scores (Iteration {iteration_num}):[/bold]")
        self.console.print(f"  Completeness:      {metrics.completeness_score:.1%}")
        self.console.print(f"  Accuracy:          {metrics.accuracy_score:.1%}")
        self.console.print(f"  Schema Compliance: {metrics.schema_compliance_score:.1%}")
        self.console.print(
            f"  [bold]Quality Score:     {metrics.quality_score:.1%}[/bold] (weighted)"
        )
        self.console.print(f"  Status:            {metrics.overall_status.title()}")

        # Show improvement tracking
        if self.tracker.iteration_count > 1:
            prev_metrics = self.tracker.get_iteration(iteration_num - 1)
            if prev_metrics:
                prev_score = prev_metrics.metrics.quality_score
                delta = metrics.quality_score - prev_score
                if delta > 0:
                    symbol, color = "↑", "green"
                elif delta < 0:
                    symbol, color = "↓", "red"
                else:
                    symbol, color = "→", "yellow"
                self.console.print(
                    f"  [{color}]Improvement: {symbol} {delta:+.3f} (prev: {prev_score:.1%})[/{color}]"
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
        self.console.print(f"\n[green]✅ Quality sufficient at iteration {iteration_num}[/green]")

        # Save best files
        if self.save_best_fn:
            result_path, validation_path = self.save_best_fn(result, validation)
            if result_path:
                self.console.print(f"[green]✅ Best result saved: {result_path}[/green]")
            if validation_path:
                self.console.print(f"[green]✅ Best validation saved: {validation_path}[/green]")

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
        self.console.print(
            f"\n[yellow]⚠️ Quality degradation detected after {self.tracker.iteration_count} iterations[/yellow]"
        )
        self.console.print("[yellow]Selecting best iteration from history...[/yellow]")

        # Select best iteration
        best = select_best_iteration(self.tracker.to_legacy_list(), self.config.metric_type)

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
        )

    def _create_max_iterations_result(self) -> IterativeLoopResult:
        """Create result for max iterations reached."""
        self.console.print(
            f"\n[yellow]⚠️ Max iterations ({self.config.max_iterations}) reached[/yellow]"
        )
        self.console.print("[yellow]Selecting best iteration from history...[/yellow]")

        # Select best iteration
        best = select_best_iteration(self.tracker.to_legacy_list(), self.config.metric_type)

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
        )

    def _create_schema_failure_result(
        self, validation: dict, iteration_num: int, schema_quality: float
    ) -> IterativeLoopResult:
        """Create result for schema validation failure."""
        self.console.print(
            f"\n[red]❌ Schema validation failed (quality: {schema_quality:.2f})[/red]"
        )

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
