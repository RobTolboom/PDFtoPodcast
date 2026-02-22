# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Validation step module.

Handles dual validation (schema + LLM semantic) and iterative correction
of extracted data until quality thresholds are met.
"""

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from ...llm import LLMError, get_llm_provider
from ...prompts import PromptLoadError, load_correction_prompt
from ...schemas_loader import SchemaLoadError, load_schema
from ..file_manager import PipelineFileManager
from ..iterative import IterativeLoopConfig, IterativeLoopRunner
from ..iterative import detect_quality_degradation as _detect_quality_degradation_new
from ..iterative import select_best_iteration as _select_best_iteration_new
from ..quality import MetricType, extract_extraction_metrics_as_dict
from ..quality.thresholds import EXTRACTION_THRESHOLDS, QualityThresholds
from ..utils import _call_progress_callback, _get_provider_name, _strip_metadata_for_pipeline
from ..validation_runner import run_dual_validation
from .extraction import run_extraction_step

_console = Console()

# Step name constants
STEP_VALIDATION = "validation"
STEP_CORRECTION = "correction"
STEP_VALIDATION_CORRECTION = "validation_correction"

# Default quality thresholds - derived from centralized EXTRACTION_THRESHOLDS
DEFAULT_QUALITY_THRESHOLDS = {
    "completeness_score": EXTRACTION_THRESHOLDS.completeness_score,
    "accuracy_score": EXTRACTION_THRESHOLDS.accuracy_score,
    "schema_compliance_score": EXTRACTION_THRESHOLDS.schema_compliance_score,
    "critical_issues": EXTRACTION_THRESHOLDS.critical_issues,
}


def is_quality_sufficient(validation_result: dict | None, thresholds: dict | None = None) -> bool:
    """
    Check if validation quality meets thresholds for stopping iteration.

    Args:
        validation_result: Validation JSON with verification_summary (can be None)
        thresholds: Quality thresholds to check against (defaults to DEFAULT_QUALITY_THRESHOLDS)

    Returns:
        bool: True if ALL thresholds are met, False otherwise
    """
    if thresholds is None:
        thresholds = DEFAULT_QUALITY_THRESHOLDS

    if validation_result is None:
        return False

    summary = validation_result.get("verification_summary", {})
    if not summary:
        return False

    def safe_score(key: str, default: float = 0.0) -> float:
        val = summary.get(key, default)
        return val if isinstance(val, int | float) else default

    return (
        safe_score("completeness_score") >= thresholds["completeness_score"]
        and safe_score("accuracy_score") >= thresholds["accuracy_score"]
        and safe_score("schema_compliance_score") >= thresholds["schema_compliance_score"]
        and safe_score("critical_issues", 999) <= thresholds["critical_issues"]
    )


# Alias for backward compatibility - delegate to quality module
_extract_metrics = extract_extraction_metrics_as_dict


def _detect_quality_degradation(iterations: list[dict], window: int = 2) -> bool:
    """Detect if quality has been degrading for the last N iterations."""
    return _detect_quality_degradation_new(iterations, window)


def _select_best_iteration(iterations: list[dict]) -> dict:
    """Select the iteration with the highest overall quality score."""
    return _select_best_iteration_new(iterations, MetricType.EXTRACTION)


def _print_iteration_summary(
    file_manager: PipelineFileManager, iterations: list[dict], best_iteration: int
) -> None:
    """Print summary of all saved iterations with best selection."""
    _console.print("\n[bold]Saved Extraction Iterations:[/bold]")
    for it_data in iterations:
        it_num = it_data["iteration_num"]
        extraction_file = file_manager.get_filename("extraction", iteration_number=it_num)
        status_symbol = "+" if extraction_file.exists() else "!"
        _console.print(f"  {status_symbol} Iteration {it_num}: {extraction_file.name}")

    best_file = file_manager.get_filename("extraction", status="best")
    if best_file.exists():
        _console.print(f"  * Best: {best_file.name} (iteration {best_iteration})")


def _with_llm_retry(
    fn: Callable[[], Any], max_retries: int = 3, console_instance: Console | None = None
) -> Any:
    """
    Execute a function with exponential backoff retry on LLMError.

    Args:
        fn: Function to execute (should be a lambda or callable with no arguments)
        max_retries: Maximum number of retry attempts (default: 3)
        console_instance: Console for output (uses module console if None)

    Returns:
        Result of the function call

    Raises:
        LLMError: If all retries are exhausted
    """
    retry_console = console_instance or _console
    for retry in range(max_retries + 1):
        try:
            return fn()
        except LLMError:
            if retry == max_retries:
                raise
            wait_time = 2**retry  # 1s, 2s, 4s
            retry_console.print(
                f"[yellow]! LLM call failed, retrying in {wait_time}s... "
                f"(attempt {retry + 1}/{max_retries})[/yellow]"
            )
            time.sleep(wait_time)


def run_validation_step(
    extraction_result: dict[str, Any],
    pdf_path: Path,
    max_pages: int | None,
    classification_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
    banner_label: str | None = None,
    save_to_disk: bool = True,
    console: Console | None = None,
) -> dict[str, Any]:
    """
    Run validation step of the pipeline.

    Performs dual validation (schema + conditional LLM semantic) on the
    extracted data to identify quality issues and errors.

    Args:
        extraction_result: Result from extraction step to validate
        pdf_path: Path to original PDF file for LLM validation
        max_pages: Maximum number of pages to process (None = all pages)
        classification_result: Result from classification step containing publication_type
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates
        banner_label: Optional custom label for console banner

    Returns:
        Dictionary containing validation results with verification_summary

    Raises:
        LLMError: If LLM API call fails during semantic validation
    """
    if console is None:
        console = _console

    start_time = time.time()
    _call_progress_callback(progress_callback, STEP_VALIDATION, "starting", {})

    # Strip metadata from dependencies before using
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)
    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")

    # Run dual validation (schema + conditional LLM) with clean data
    label = banner_label or "VALIDATION"
    validation_result = run_dual_validation(
        extraction_result=extraction_clean,
        pdf_path=pdf_path,
        max_pages=max_pages,
        publication_type=publication_type,
        llm=llm,
        console=console,
        banner_label=label,
    )

    # Add pipeline metadata
    elapsed = time.time() - start_time
    validation_result["_pipeline_metadata"] = {
        "step": "validation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": elapsed,
        "llm_provider": _get_provider_name(llm),
        "model_used": validation_result.get("_metadata", {}).get("model"),
        "max_pages": max_pages,
        "pdf_filename": pdf_path.name,
        "execution_mode": "streamlit" if progress_callback else "cli",
        "status": "success",
        "validation_passed": validation_result.get("is_valid", False),
    }

    validation_file = None
    if save_to_disk:
        validation_file = file_manager.save_json(
            validation_result, "validation", iteration_number=0
        )
        console.print(f"[green]+ Validation saved: {validation_file}[/green]")

    # Validation completed
    elapsed = time.time() - start_time
    _call_progress_callback(
        progress_callback,
        "validation",
        "completed",
        {
            "result": validation_result,
            "elapsed_seconds": elapsed,
            "file_path": str(validation_file) if validation_file else None,
            "validation_status": validation_result.get("verification_summary", {}).get(
                "overall_status"
            ),
        },
    )

    return validation_result


def run_correction_step(
    extraction_result: dict[str, Any],
    validation_result: dict[str, Any],
    pdf_path: Path,
    max_pages: int | None,
    publication_type: str,
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
    banner_label: str | None = None,
    console: Console | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run correction step of the pipeline.

    Applies LLM-based corrections to extraction results based on validation
    feedback, then re-validates the corrected extraction.

    Args:
        extraction_result: Original extraction result to correct
        validation_result: Validation result containing issues to fix
        pdf_path: Path to original PDF file for LLM correction
        max_pages: Maximum number of pages to process (None = all pages)
        publication_type: Publication type from classification (for schema)
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates
        banner_label: Optional custom label for console banner

    Returns:
        Tuple of (corrected_extraction, final_validation)

    Raises:
        PromptLoadError: If correction prompt cannot be loaded
        SchemaLoadError: If extraction schema cannot be loaded
        LLMError: If LLM API call fails
    """
    if console is None:
        console = _console

    title = banner_label or "CORRECTION"
    console.print(f"\n[bold magenta]=== {title} ===[/bold magenta]\n")

    start_time = time.time()

    # Display pre-correction quality
    pre_summary = validation_result.get("verification_summary", {})
    console.print("[bold]Pre-Correction Quality:[/bold]")
    console.print(f"  Completeness:      {pre_summary.get('completeness_score', 0):.1%}")
    console.print(f"  Accuracy:          {pre_summary.get('accuracy_score', 0):.1%}")
    console.print(f"  Schema Compliance: {pre_summary.get('schema_compliance_score', 0):.1%}")
    console.print(f"  Critical Issues:   {pre_summary.get('critical_issues', 0)}")
    console.print(f"  Total Issues:      {pre_summary.get('total_issues', 0)}\n")

    validation_status = pre_summary.get("overall_status")

    _call_progress_callback(
        progress_callback,
        "correction",
        "starting",
        {"validation_status": validation_status},
    )

    try:
        # Strip metadata from dependencies before using in prompts
        extraction_clean = _strip_metadata_for_pipeline(extraction_result)
        validation_clean = _strip_metadata_for_pipeline(validation_result)

        # Load correction prompt and extraction schema
        correction_prompt = load_correction_prompt()
        extraction_schema = load_schema(publication_type)

        # Prepare correction context with focused extraction and actionable issues only.
        # Full validation report is too large and causes the LLM to simplify structures.
        schema_errors = validation_clean.get("schema_validation", {}).get("validation_errors", [])
        semantic_issues = validation_clean.get("issues", [])
        verification_summary = validation_clean.get("verification_summary", {})

        correction_issues = {
            "schema_errors": schema_errors,
            "semantic_issues": semantic_issues,
            "verification_summary": verification_summary,
        }

        correction_context = f"""
ORIGINAL_EXTRACTION: {json.dumps(extraction_clean)}

VALIDATION_REPORT: {json.dumps(correction_issues)}

Systematically address all identified issues and produce corrected, complete,\
 schema-compliant JSON extraction.
"""

        # Inject previous failure hints if available
        correction_hints = validation_clean.get("_correction_hints", "")
        if correction_hints:
            correction_context += f"\n\nPREVIOUS_CORRECTION_FAILURES: {correction_hints}\n"

        # Run correction with PDF upload for direct reference
        console.print("[dim]Running correction with PDF upload...[/dim]")
        from ...config import llm_settings

        corrected_extraction = llm.generate_json_with_pdf(
            pdf_path=pdf_path,
            schema=extraction_schema,
            system_prompt=correction_prompt + "\n\n" + correction_context,
            max_pages=max_pages,
            schema_name=f"{publication_type}_extraction_corrected",
            reasoning_effort=llm_settings.reasoning_effort_correction,
        )

        # Apply deterministic schema repairs before validation.
        # Fixes common LLM issues: array items as strings instead of objects,
        # disallowed properties where additionalProperties=false.
        from ..schema_repair import repair_schema_violations

        corrected_extraction = repair_schema_violations(
            data=corrected_extraction,
            schema=extraction_schema,
            original=extraction_clean,
        )

        # Ensure correction metadata
        if "correction_notes" not in corrected_extraction:
            corrected_extraction["correction_notes"] = (
                "Corrections applied based on validation feedback"
            )

        # Add pipeline metadata to corrected extraction
        elapsed_extraction = time.time() - start_time
        corrected_extraction["_pipeline_metadata"] = {
            "step": "correction",
            "sub_step": "extraction",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed_extraction,
            "llm_provider": _get_provider_name(llm),
            "model_used": corrected_extraction.get("_metadata", {}).get("model"),
            "max_pages": max_pages,
            "pdf_filename": pdf_path.name,
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
        }

        # Final validation of corrected extraction
        console.print("[dim]Running final validation on corrected extraction...[/dim]")

        # Strip metadata from corrected extraction before validation
        corrected_extraction_clean = _strip_metadata_for_pipeline(corrected_extraction)

        # Re-run dual validation on clean corrected extraction
        final_validation = run_dual_validation(
            extraction_result=corrected_extraction_clean,
            pdf_path=pdf_path,
            max_pages=max_pages,
            publication_type=publication_type,
            llm=llm,
            console=console,
        )

        # Add pipeline metadata to final validation
        elapsed_validation = time.time() - start_time
        final_validation["_pipeline_metadata"] = {
            "step": "correction",
            "sub_step": "validation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed_validation - elapsed_extraction,
            "llm_provider": _get_provider_name(llm),
            "model_used": final_validation.get("_metadata", {}).get("model"),
            "max_pages": max_pages,
            "pdf_filename": pdf_path.name,
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
        }

        # Display post-correction quality and improvement
        post_summary = final_validation.get("verification_summary", {})
        console.print("\n[bold]Post-Correction Quality:[/bold]")

        # Calculate and display deltas for each metric
        for metric_key, metric_name in [
            ("completeness_score", "Completeness"),
            ("accuracy_score", "Accuracy"),
            ("schema_compliance_score", "Schema Compliance"),
        ]:
            pre_val = pre_summary.get(metric_key, 0)
            post_val = post_summary.get(metric_key, 0)
            delta = post_val - pre_val

            # Color code the delta
            if delta > 0:
                color = "green"
            elif delta < 0:
                color = "red"
            else:
                color = "yellow"

            console.print(f"  {metric_name:18} {post_val:.1%} [{color}]({delta:+.1%})[/{color}]")

        # Display issue counts with deltas
        pre_critical = pre_summary.get("critical_issues", 0)
        post_critical = post_summary.get("critical_issues", 0)
        delta_critical = post_critical - pre_critical
        console.print(f"  Critical Issues:   {post_critical} ({delta_critical:+d})")

        pre_total = pre_summary.get("total_issues", 0)
        post_total = post_summary.get("total_issues", 0)
        delta_total = post_total - pre_total
        console.print(f"  Total Issues:      {post_total} ({delta_total:+d})")

        # Overall improvement message
        pre_metrics = _extract_metrics(validation_result)
        post_metrics = _extract_metrics(final_validation)
        delta_overall = post_metrics["overall_quality"] - pre_metrics["overall_quality"]

        if delta_overall > 0:
            console.print(f"\n[green]+ Correction improved quality by {delta_overall:+.1%}[/green]")
        elif delta_overall < 0:
            console.print(f"\n[yellow]! Quality degraded by {delta_overall:.1%}[/yellow]")
        else:
            console.print("\n[yellow]-> No significant quality change[/yellow]")

        # Correction completed successfully
        elapsed = time.time() - start_time
        _call_progress_callback(
            progress_callback,
            "correction",
            "completed",
            {
                "result": corrected_extraction,
                "elapsed_seconds": elapsed,
                "extraction_file_path": None,
                "validation_file_path": None,
                "final_validation_status": final_validation.get("verification_summary", {}).get(
                    "overall_status"
                ),
            },
        )

        return corrected_extraction, final_validation

    except (PromptLoadError, LLMError, SchemaLoadError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]X Correction error: {e}[/red]")

        # Save error metadata (best effort)
        error_data = {
            "_pipeline_metadata": {
                "step": "correction",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": elapsed,
                "llm_provider": _get_provider_name(llm),
                "model_used": None,
                "max_pages": max_pages,
                "pdf_filename": pdf_path.name,
                "execution_mode": "streamlit" if progress_callback else "cli",
                "status": "failed",
                "error_message": str(e),
                "error_type": type(e).__name__,
            }
        }
        try:
            file_manager.save_json(error_data, "correction", "failed")
        except Exception as save_err:
            console.print(f"[yellow]! Failed to save error metadata: {save_err}[/yellow]")

        _call_progress_callback(
            progress_callback,
            "correction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def run_validation_with_correction(
    pdf_path: Path,
    extraction_result: dict,
    classification_result: dict,
    llm_provider: str,
    file_manager: PipelineFileManager,
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    progress_callback: Callable | None = None,
    verbose: bool = False,
) -> dict:
    """
    Run validation with automatic iterative correction until quality is sufficient.

    Workflow:
        1. Validate extraction (schema + LLM)
        2. If quality insufficient and iterations < max:
           - Run correction
           - Validate corrected output
           - Repeat until quality OK or max iterations reached
        3. Select best iteration based on quality metrics
        4. Return best extraction + validation + iteration history

    Args:
        pdf_path: Path to source PDF
        extraction_result: Initial extraction JSON
        classification_result: Classification result (for publication type)
        llm_provider: LLM provider name ("openai" | "claude")
        file_manager: File manager for saving iterations
        max_iterations: Maximum correction attempts (default: 3)
        quality_thresholds: Custom thresholds
        progress_callback: Optional callback for progress updates

    Returns:
        dict: {
            'best_extraction': dict,
            'best_validation': dict,
            'iterations': list[dict],
            'final_status': str,
            'iteration_count': int,
            'improvement_trajectory': list[float],
        }
    """
    # Extract publication_type for correction step
    publication_type = classification_result.get("publication_type", "unknown")

    # Display header (verbose only — compact mode uses loop_runner headers)
    if verbose:
        _console.print(
            "\n[bold magenta]=== STEP 3: ITERATIVE VALIDATION & CORRECTION ===[/bold magenta]\n"
        )
        _console.print(f"[blue]Publication type: {publication_type}[/blue]")

    # Get LLM instance
    llm = get_llm_provider(llm_provider)

    # Create quiet console to suppress step-level output in compact mode
    quiet_console = None if verbose else Console(quiet=True)

    # Define callback functions for IterativeLoopRunner
    def validate_fn(extraction: dict) -> dict:
        """Validate extraction with LLM retry."""
        return _with_llm_retry(
            lambda: run_validation_step(
                extraction_result=extraction,
                pdf_path=pdf_path,
                max_pages=None,
                classification_result=classification_result,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
                banner_label="VALIDATION",
                save_to_disk=False,
                console=quiet_console,
            ),
        )

    def correct_fn(extraction: dict, validation: dict) -> tuple[dict, dict]:
        """Correct extraction with LLM retry, return corrected extraction + validation."""
        corrected, post_validation = _with_llm_retry(
            lambda: run_correction_step(
                extraction_result=extraction,
                validation_result=validation,
                pdf_path=pdf_path,
                max_pages=None,
                publication_type=publication_type,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
                banner_label="CORRECTION",
                console=quiet_console,
            ),
        )
        return _strip_metadata_for_pipeline(corrected), post_validation

    def save_iteration_fn(
        iteration_num: int, result: dict, validation: dict
    ) -> tuple[Path | None, Path | None]:
        """Save iteration files."""
        extraction_file = file_manager.save_json(
            result, "extraction", iteration_number=iteration_num
        )
        validation_file = file_manager.save_json(
            validation, "validation", iteration_number=iteration_num
        )
        return extraction_file, validation_file

    def save_best_fn(result: dict, validation: dict) -> tuple[Path | None, Path | None]:
        """Save best extraction and validation files."""
        extraction_file = file_manager.save_json(result, "extraction", status="best")
        validation_file = file_manager.save_json(validation, "validation", status="best")
        return extraction_file, validation_file

    def regenerate_initial_fn() -> dict:
        """Regenerate the initial extraction if it fails schema validation."""
        return run_extraction_step(
            pdf_path=pdf_path,
            max_pages=None,
            classification_result=classification_result,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )

    def save_failed_fn(
        extraction_result_failed: dict, validation_result_failed: dict
    ) -> tuple[Path | None, Path | None]:
        """Save failed extraction and validation for debugging."""
        extraction_path = file_manager.save_json(
            extraction_result_failed, "extraction", status="failed"
        )
        validation_path = file_manager.save_json(
            validation_result_failed, "validation", status="failed"
        )
        return extraction_path, validation_path

    # Configure and run iterative loop
    config = IterativeLoopConfig(
        metric_type=MetricType.EXTRACTION,
        max_iterations=max_iterations,
        quality_thresholds=(
            QualityThresholds(**quality_thresholds)
            if isinstance(quality_thresholds, dict)
            else (quality_thresholds or EXTRACTION_THRESHOLDS)
        ),
        degradation_window=2,
        step_name="ITERATIVE VALIDATION & CORRECTION",
        step_number=3,
        show_banner=False,  # We already printed banner above
        verbose=verbose,
    )

    runner = IterativeLoopRunner(
        config=config,
        initial_result=extraction_result,
        validate_fn=validate_fn,
        correct_fn=correct_fn,
        save_iteration_fn=save_iteration_fn,
        save_best_fn=save_best_fn,
        regenerate_initial_fn=regenerate_initial_fn,
        save_failed_fn=save_failed_fn,
        progress_callback=progress_callback,
        console_instance=_console,
        check_schema_quality=True,
        schema_quality_threshold=0.5,
    )

    loop_result = runner.run()
    return loop_result.to_dict(result_key="best_extraction")


# Backward compatibility aliases
_run_validation_step = run_validation_step
_run_correction_step = run_correction_step
