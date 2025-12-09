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
from ..iterative import detect_quality_degradation as _detect_quality_degradation_new
from ..iterative import select_best_iteration as _select_best_iteration_new
from ..quality import MetricType, extract_extraction_metrics_as_dict
from ..utils import _call_progress_callback, _get_provider_name, _strip_metadata_for_pipeline
from ..validation_runner import run_dual_validation

console = Console()

# Step name constants
STEP_VALIDATION = "validation"
STEP_CORRECTION = "correction"
STEP_VALIDATION_CORRECTION = "validation_correction"

# Default quality thresholds for iterative correction loop (extraction)
DEFAULT_QUALITY_THRESHOLDS = {
    "completeness_score": 0.90,  # >=90% of PDF data extracted
    "accuracy_score": 0.95,  # >=95% correct data (max 5% errors)
    "schema_compliance_score": 0.95,  # >=95% schema compliant
    "critical_issues": 0,  # Absolutely no critical errors
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
    return _detect_quality_degradation_new(iterations, window, MetricType.EXTRACTION)


def _select_best_iteration(iterations: list[dict]) -> dict:
    """Select the iteration with the highest overall quality score."""
    return _select_best_iteration_new(iterations, MetricType.EXTRACTION)


def _print_iteration_summary(
    file_manager: PipelineFileManager, iterations: list[dict], best_iteration: int
) -> None:
    """Print summary of all saved iterations with best selection."""
    console.print("\n[bold]Saved Extraction Iterations:[/bold]")
    for it_data in iterations:
        it_num = it_data["iteration_num"]
        extraction_file = file_manager.get_filename("extraction", iteration_number=it_num)
        status_symbol = "+" if extraction_file.exists() else "!"
        console.print(f"  {status_symbol} Iteration {it_num}: {extraction_file.name}")

    best_file = file_manager.get_filename("extraction", status="best")
    if best_file.exists():
        console.print(f"  * Best: {best_file.name} (iteration {best_iteration})")


def run_validation_step(
    extraction_result: dict[str, Any],
    pdf_path: Path,
    max_pages: int | None,
    classification_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
    banner_label: str | None = None,
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

    validation_file = file_manager.save_json(validation_result, "validation", iteration_number=0)
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
            "file_path": str(validation_file),
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

        # Prepare correction context with clean extraction and validation feedback
        correction_context = f"""
ORIGINAL_EXTRACTION: {json.dumps(extraction_clean, indent=2)}

VALIDATION_REPORT: {json.dumps(validation_clean, indent=2)}

Systematically address all identified issues and produce corrected, complete,\
 schema-compliant JSON extraction.
"""

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
    # Initialize
    iterations = []
    current_extraction = extraction_result
    current_validation = None
    iteration_num = 0

    # Default thresholds
    if quality_thresholds is None:
        quality_thresholds = DEFAULT_QUALITY_THRESHOLDS

    # Extract publication_type for correction step
    publication_type = classification_result.get("publication_type", "unknown")

    # Display header and configuration
    console.print(
        "\n[bold magenta]=== STEP 3: ITERATIVE VALIDATION & CORRECTION ===[/bold magenta]\n"
    )
    console.print(f"[blue]Publication type: {publication_type}[/blue]")
    console.print(f"[blue]Max iterations: {max_iterations}[/blue]")
    console.print(
        f"[blue]Quality thresholds: Completeness >={quality_thresholds['completeness_score']:.0%}, "
        f"Accuracy >={quality_thresholds['accuracy_score']:.0%}, "
        f"Schema >={quality_thresholds['schema_compliance_score']:.0%}, "
        f"Critical issues = {quality_thresholds['critical_issues']}[/blue]\n"
    )

    # Get LLM instance
    llm = get_llm_provider(llm_provider)

    while iteration_num <= max_iterations:
        # Display iteration header
        console.print(f"\n[bold cyan]--- Iteration {iteration_num} ---[/bold cyan]")

        try:
            # Progress callback
            _call_progress_callback(
                progress_callback,
                STEP_VALIDATION_CORRECTION,
                "starting",
                {"iteration": iteration_num, "step": "validation"},
            )

            # STEP 1: Validate current extraction
            if current_validation is None:
                validation_result = run_validation_step(
                    extraction_result=current_extraction,
                    pdf_path=pdf_path,
                    max_pages=None,
                    classification_result=classification_result,
                    llm=llm,
                    file_manager=file_manager,
                    progress_callback=progress_callback,
                    banner_label=f"Iter {iteration_num} - VALIDATION",
                )

                # Check schema validation failure
                schema_validation = validation_result.get("schema_validation", {})
                quality_score = schema_validation.get("quality_score", 0)

                if quality_score < 0.5:
                    return {
                        "best_extraction": None,
                        "best_validation": validation_result,
                        "iterations": iterations,
                        "final_status": "failed_schema_validation",
                        "iteration_count": iteration_num + 1,
                        "error": f"Schema validation failed (quality: {quality_score:.2f}).",
                        "failed_at_iteration": iteration_num,
                    }

                # Save validation with iteration number
                validation_file = file_manager.save_json(
                    validation_result, "validation", iteration_number=iteration_num
                )
                console.print(f"[dim]Saved validation: {validation_file}[/dim]")
            else:
                validation_result = current_validation
                console.print(
                    f"[dim]Reusing post-correction validation for iteration {iteration_num}[/dim]"
                )

            # Store iteration data
            metrics = _extract_metrics(validation_result)
            iteration_data = {
                "iteration_num": iteration_num,
                "extraction": current_extraction,
                "validation": validation_result,
                "metrics": metrics,
                "timestamp": datetime.now().isoformat(),
            }
            iterations.append(iteration_data)

            # Display quality scores
            console.print(f"\n[bold]Quality Scores (Iteration {iteration_num}):[/bold]")
            console.print(f"  [bold]Overall Quality:   {metrics['overall_quality']:.1%}[/bold]")
            status = validation_result.get("verification_summary", {}).get(
                "overall_status", "unknown"
            )
            console.print(f"  Validation Status: {status.title() if status else '-'}")

            # Display improvement tracking
            if len(iterations) > 1:
                prev_quality = iterations[-2]["metrics"]["overall_quality"]
                delta = metrics["overall_quality"] - prev_quality
                if delta > 0:
                    symbol, color = "^", "green"
                elif delta < 0:
                    symbol, color = "v", "red"
                else:
                    symbol, color = "->", "yellow"
                console.print(
                    f"  [{color}]Improvement: {symbol} {delta:+.3f} (prev: {prev_quality:.1%})[/{color}]"
                )

            # STEP 2: Check quality
            if is_quality_sufficient(validation_result, quality_thresholds):
                # SUCCESS: Quality is sufficient
                best_extraction_file = file_manager.save_json(
                    current_extraction, "extraction", status="best"
                )
                console.print(f"[green]+ Best extraction saved: {best_extraction_file}[/green]")

                best_validation_file = file_manager.save_json(
                    validation_result, "validation", status="best"
                )
                console.print(f"[green]+ Best validation saved: {best_validation_file}[/green]")

                # Save metadata
                selection_metadata = {
                    "best_iteration_num": iteration_num,
                    "overall_quality": metrics["overall_quality"],
                    "completeness_score": metrics.get("completeness_score", 0),
                    "accuracy_score": metrics.get("accuracy_score", 0),
                    "schema_compliance_score": metrics.get("schema_compliance_score", 0),
                    "selection_reason": "passed",
                    "total_iterations": iteration_num + 1,
                    "timestamp": datetime.now().isoformat(),
                }
                file_manager.save_json(selection_metadata, "extraction", status="best-metadata")

                console.print(
                    f"\n[green]+ Quality sufficient at iteration {iteration_num}! Stopping.[/green]"
                )
                _print_iteration_summary(file_manager, iterations, iteration_num)

                _call_progress_callback(
                    progress_callback,
                    STEP_VALIDATION_CORRECTION,
                    "completed",
                    {
                        "final_status": "passed",
                        "iterations": iteration_num + 1,
                        "reason": "quality_sufficient",
                    },
                )

                return {
                    "best_extraction": current_extraction,
                    "best_validation": validation_result,
                    "iterations": iterations,
                    "final_status": "passed",
                    "iteration_count": iteration_num + 1,
                    "best_iteration": iteration_num,
                    "improvement_trajectory": [
                        it["metrics"]["overall_quality"] for it in iterations
                    ],
                }

            # STEP 3A: Check for quality degradation
            if iteration_num >= 2:
                if _detect_quality_degradation(iterations, window=2):
                    best = _select_best_iteration(iterations)

                    best_extraction_file = file_manager.save_json(
                        best["extraction"], "extraction", status="best"
                    )
                    console.print(f"[green]+ Best extraction saved: {best_extraction_file}[/green]")

                    best_validation_file = file_manager.save_json(
                        best["validation"], "validation", status="best"
                    )
                    console.print(f"[green]+ Best validation saved: {best_validation_file}[/green]")

                    selection_metadata = {
                        "best_iteration_num": best["iteration_num"],
                        "overall_quality": best["metrics"]["overall_quality"],
                        "selection_reason": "early_stopped_degradation",
                        "total_iterations": len(iterations),
                        "timestamp": datetime.now().isoformat(),
                    }
                    file_manager.save_json(selection_metadata, "extraction", status="best-metadata")

                    console.print(
                        "\n[yellow]! Quality degrading - stopping early and selecting best[/yellow]"
                    )
                    _print_iteration_summary(file_manager, iterations, best["iteration_num"])

                    _call_progress_callback(
                        progress_callback,
                        STEP_VALIDATION_CORRECTION,
                        "completed",
                        {
                            "final_status": "early_stopped_degradation",
                            "iterations": len(iterations),
                            "best_iteration": best["iteration_num"],
                        },
                    )

                    return {
                        "best_extraction": best["extraction"],
                        "best_validation": best["validation"],
                        "iterations": iterations,
                        "final_status": "early_stopped_degradation",
                        "iteration_count": len(iterations),
                        "best_iteration": best["iteration_num"],
                        "improvement_trajectory": [
                            it["metrics"]["overall_quality"] for it in iterations
                        ],
                    }

            # STEP 3B: Check if we can do another correction
            if iteration_num >= max_iterations:
                best = _select_best_iteration(iterations)

                best_extraction_file = file_manager.save_json(
                    best["extraction"], "extraction", status="best"
                )
                console.print(f"[green]+ Best extraction saved: {best_extraction_file}[/green]")

                best_validation_file = file_manager.save_json(
                    best["validation"], "validation", status="best"
                )
                console.print(f"[green]+ Best validation saved: {best_validation_file}[/green]")

                selection_metadata = {
                    "best_iteration_num": best["iteration_num"],
                    "overall_quality": best["metrics"]["overall_quality"],
                    "selection_reason": "max_iterations_reached",
                    "total_iterations": len(iterations),
                    "timestamp": datetime.now().isoformat(),
                }
                file_manager.save_json(selection_metadata, "extraction", status="best-metadata")

                console.print(
                    f"\n[yellow]! Max iterations ({max_iterations}) reached - selecting best[/yellow]"
                )
                _print_iteration_summary(file_manager, iterations, best["iteration_num"])

                _call_progress_callback(
                    progress_callback,
                    STEP_VALIDATION_CORRECTION,
                    "completed",
                    {
                        "final_status": "max_iterations_reached",
                        "iterations": len(iterations),
                        "best_iteration": best["iteration_num"],
                    },
                )

                return {
                    "best_extraction": best["extraction"],
                    "best_validation": best["validation"],
                    "iterations": iterations,
                    "final_status": "max_iterations_reached",
                    "iteration_count": len(iterations),
                    "best_iteration": best["iteration_num"],
                    "improvement_trajectory": [
                        it["metrics"]["overall_quality"] for it in iterations
                    ],
                }

            # STEP 4: Run correction for next iteration
            console.print(
                f"\n[yellow]Quality insufficient (iteration {iteration_num}). Running correction...[/yellow]"
            )
            iteration_num += 1

            _call_progress_callback(
                progress_callback,
                STEP_VALIDATION_CORRECTION,
                "starting",
                {"iteration": iteration_num, "step": "correction"},
            )

            corrected_extraction, final_validation = run_correction_step(
                extraction_result=current_extraction,
                validation_result=validation_result,
                pdf_path=pdf_path,
                max_pages=None,
                publication_type=publication_type,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
                banner_label=f"Iter {iteration_num} - CORRECTION",
            )

            # Save corrected extraction with iteration number
            corrected_file = file_manager.save_json(
                corrected_extraction, "extraction", iteration_number=iteration_num
            )
            console.print(f"[dim]Saved corrected extraction: {corrected_file}[/dim]")

            # Save post-correction validation with iteration number
            validation_file = file_manager.save_json(
                final_validation, "validation", iteration_number=iteration_num
            )
            console.print(f"[dim]Saved post-correction validation: {validation_file}[/dim]")

            # Update current extraction and validation for next iteration
            current_extraction = _strip_metadata_for_pipeline(corrected_extraction)
            current_validation = final_validation

        except LLMError as e:
            # LLM API failure - retry with exponential backoff
            max_retries = 3
            retry_successful = False

            for retry in range(max_retries):
                wait_time = 2**retry
                console.print(
                    f"[yellow]! LLM call failed, retrying in {wait_time}s... "
                    f"(attempt {retry+1}/{max_retries})[/yellow]"
                )
                time.sleep(wait_time)

                try:
                    if iteration_num == len(iterations):
                        validation_result = run_validation_step(
                            extraction_result=current_extraction,
                            pdf_path=pdf_path,
                            max_pages=None,
                            classification_result=classification_result,
                            llm=llm,
                            file_manager=file_manager,
                            progress_callback=progress_callback,
                            banner_label=f"Iter {iteration_num} - VALIDATION",
                        )
                        retry_successful = True
                        break
                    else:
                        corrected_extraction, final_validation = run_correction_step(
                            extraction_result=current_extraction,
                            validation_result=validation_result,
                            pdf_path=pdf_path,
                            max_pages=None,
                            publication_type=publication_type,
                            llm=llm,
                            file_manager=file_manager,
                            progress_callback=progress_callback,
                            banner_label=f"Iter {iteration_num} - CORRECTION (retry)",
                        )

                        corrected_file = file_manager.save_json(
                            corrected_extraction, "extraction", iteration_number=iteration_num
                        )
                        validation_file = file_manager.save_json(
                            final_validation, "validation", iteration_number=iteration_num
                        )

                        current_extraction = _strip_metadata_for_pipeline(corrected_extraction)
                        current_validation = final_validation
                        retry_successful = True
                        break
                except LLMError:
                    continue

            if not retry_successful:
                best = _select_best_iteration(iterations) if iterations else None

                if best:
                    file_manager.save_json(best["extraction"], "extraction", status="best")
                    file_manager.save_json(best["validation"], "validation", status="best")

                return {
                    "best_extraction": best["extraction"] if best else current_extraction,
                    "best_validation": best["validation"] if best else None,
                    "iterations": iterations,
                    "final_status": "failed_llm_error",
                    "iteration_count": len(iterations),
                    "best_iteration": best["iteration_num"] if best else 0,
                    "error": f"LLM provider error after {max_retries} retries: {e!s}",
                    "failed_at_iteration": iteration_num,
                }

        except json.JSONDecodeError as e:
            console.print(
                f"[red]X Correction returned invalid JSON at iteration {iteration_num}[/red]"
            )
            best = _select_best_iteration(iterations) if iterations else None

            if best:
                file_manager.save_json(best["extraction"], "extraction", status="best")
                file_manager.save_json(best["validation"], "validation", status="best")

            return {
                "best_extraction": best["extraction"] if best else current_extraction,
                "best_validation": best["validation"] if best else None,
                "iterations": iterations,
                "final_status": "failed_invalid_json",
                "iteration_count": len(iterations),
                "best_iteration": best["iteration_num"] if best else 0,
                "error": f"Correction produced invalid JSON: {e!s}",
                "failed_at_iteration": iteration_num,
            }

        except Exception as e:
            console.print(f"[red]X Unexpected error at iteration {iteration_num}: {e!s}[/red]")
            best = _select_best_iteration(iterations) if len(iterations) > 0 else None

            if best:
                file_manager.save_json(best["extraction"], "extraction", status="best")
                file_manager.save_json(best["validation"], "validation", status="best")

            return {
                "best_extraction": best["extraction"] if best else current_extraction,
                "best_validation": best["validation"] if best else None,
                "iterations": iterations,
                "final_status": "failed_unexpected_error",
                "iteration_count": len(iterations),
                "best_iteration": best["iteration_num"] if best else 0,
                "error": f"Unexpected error: {e!s}",
                "failed_at_iteration": iteration_num,
            }

    # Should never reach here
    raise RuntimeError("Validation loop exited unexpectedly")


# Backward compatibility aliases
_run_validation_step = run_validation_step
_run_correction_step = run_correction_step
