# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Four-step PDF extraction pipeline orchestration.

This module contains the main pipeline orchestration logic that coordinates
the four extraction steps: Classification → Extraction → Validation → Correction.

Pipeline Steps:
    1. Classification - Identify publication type and extract metadata
    2. Extraction - Schema-based structured data extraction
    3. Validation - Dual validation (schema + conditional LLM semantic)
    4. Correction - Fix issues identified during validation

Public APIs:
    - run_single_step(): Execute individual pipeline steps with dependency validation
      Enables step-by-step execution with UI updates between steps.

    - run_four_step_pipeline(): Execute all four steps sequentially (legacy API)
      Runs the complete pipeline in one call without intermediate updates.

Step-by-Step Execution Example:
    >>> from pathlib import Path
    >>> from src.pipeline.orchestrator import run_single_step
    >>> from src.pipeline.file_manager import PipelineFileManager
    >>>
    >>> pdf_path = Path("paper.pdf")
    >>> fm = PipelineFileManager(pdf_path)
    >>>
    >>> # Step 1: Classification
    >>> result1 = run_single_step("classification", pdf_path, None, "openai", fm)
    >>>
    >>> # Step 2: Extraction (requires classification)
    >>> result2 = run_single_step(
    ...     "extraction", pdf_path, None, "openai", fm,
    ...     previous_results={"classification": result1}
    ... )
    >>>
    >>> # Step 3: Validation (requires classification + extraction)
    >>> result3 = run_single_step(
    ...     "validation", pdf_path, None, "openai", fm,
    ...     previous_results={"classification": result1, "extraction": result2}
    ... )

PDF Upload Strategy:
    All LLM steps use direct PDF upload (no text extraction) to preserve:
    - Tables and figures (critical for medical research data)
    - Images and charts (visual data representation)
    - Complex formatting and layout information
    - Complete document structure and context

    Cost: ~1,500-3,000 tokens per page (3-6x more than text extraction)
    Benefit: Complete data fidelity - no loss of tables, images, or formatting
"""

import copy
import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from ..llm import LLMError, get_llm_provider
from ..prompts import (
    PromptLoadError,
    load_classification_prompt,
    load_correction_prompt,
    load_extraction_prompt,
)
from ..schemas_loader import SchemaLoadError, load_schema, validate_schema_compatibility
from .file_manager import PipelineFileManager
from .utils import check_breakpoint
from .validation_runner import run_dual_validation

# Pipeline step name constants
STEP_CLASSIFICATION = "classification"
STEP_EXTRACTION = "extraction"
STEP_VALIDATION = "validation"
STEP_CORRECTION = "correction"

ALL_PIPELINE_STEPS = [
    STEP_CLASSIFICATION,
    STEP_EXTRACTION,
    STEP_VALIDATION,
    STEP_CORRECTION,
]

# New step: combined validation with iterative correction
STEP_VALIDATION_CORRECTION = "validation_correction"

# Default quality thresholds for iterative correction loop
DEFAULT_QUALITY_THRESHOLDS = {
    "completeness_score": 0.90,  # ≥90% of PDF data extracted
    "accuracy_score": 0.95,  # ≥95% correct data (max 5% errors)
    "schema_compliance_score": 0.95,  # ≥95% schema compliant
    "critical_issues": 0,  # Absolutely no critical errors
}

# Final status codes for iterative loop results
FINAL_STATUS_CODES = {
    "passed": "Quality thresholds met",
    "max_iterations_reached": "Maximum iterations reached, using best result",
    "early_stopped_degradation": "Stopped due to quality degradation",
    "failed_schema_validation": "Schema validation failed",
    "failed_llm_error": "LLM API error after retries",
    "failed_invalid_json": "Correction produced invalid JSON",
    "failed_unexpected_error": "Unexpected error occurred",
}

console = Console()


def _call_progress_callback(
    callback: Callable[[str, str, dict], None] | None,
    step_name: str,
    status: str,
    data: dict,
) -> None:
    """
    Safely call progress callback if provided.

    Wraps callback in try/except to prevent callback errors from breaking pipeline.
    Logs callback errors but does not propagate them.

    Args:
        callback: Optional callback function (None = no callback)
        step_name: Step identifier ("classification", "extraction", "validation", "correction")
        status: Step status ("starting", "running", "completed", "failed", "skipped")
        data: Dictionary with step-specific information (results, errors, timing, etc.)

    Example:
        >>> _call_progress_callback(my_callback, "classification", "starting", {"pdf_path": "..."})
    """
    if callback is None:
        return

    try:
        callback(step_name, status, data)
    except Exception as e:
        # Log but don't propagate - callback errors shouldn't break pipeline
        console.print(f"[yellow]⚠️  Progress callback error in {step_name}: {e}[/yellow]")


def _strip_metadata_for_pipeline(data: dict) -> dict:
    """
    Remove metadata fields before passing data to next pipeline step.

    Strips fields that contain execution metadata but are not part of
    the schema-defined data structure:

    - usage: LLM token usage (input/output/cached tokens)
    - _metadata: LLM API response metadata (response_id, model, etc.)
    - _pipeline_metadata: Pipeline execution metadata (timestamp, duration, etc.)

    This ensures:
    1. Schema validation doesn't fail on unexpected fields
    2. LLM prompts don't receive metadata clutter
    3. Step dependencies only see clean, schema-valid data

    Args:
        data: Dictionary containing step results with potential metadata

    Returns:
        Deep copy of data with metadata fields removed. Deep copy ensures
        modifications to nested objects don't affect the original data.

    Example:
        >>> result = {
        ...     "publication_type": "interventional_trial",
        ...     "usage": {"input_tokens": 1000},
        ...     "_metadata": {"response_id": "resp_123"}
        ... }
        >>> clean = _strip_metadata_for_pipeline(result)
        >>> clean
        {'publication_type': 'interventional_trial'}
    """
    clean_data = copy.deepcopy(data)
    clean_data.pop("usage", None)
    clean_data.pop("_metadata", None)
    clean_data.pop("_pipeline_metadata", None)
    return clean_data


def _get_provider_name(llm: Any) -> str:
    """
    Get provider name from LLM instance class name.

    Determines which LLM provider is being used by inspecting the
    class name of the LLM instance. Used for pipeline metadata tracking.

    Args:
        llm: LLM provider instance (OpenAIProvider or ClaudeProvider)

    Returns:
        Provider name: "openai", "claude", or "unknown"

    Example:
        >>> from src.llm import get_llm_provider
        >>> llm = get_llm_provider("openai")
        >>> _get_provider_name(llm)
        'openai'
    """
    class_name = llm.__class__.__name__
    if "OpenAI" in class_name:
        return "openai"
    elif "Claude" in class_name:
        return "claude"
    return "unknown"


def is_quality_sufficient(validation_result: dict | None, thresholds: dict | None = None) -> bool:
    """
    Check if validation quality meets thresholds for stopping iteration.

    Args:
        validation_result: Validation JSON with verification_summary (can be None)
        thresholds: Quality thresholds to check against (defaults to DEFAULT_QUALITY_THRESHOLDS)

    Returns:
        bool: True if ALL thresholds are met, False otherwise

    Edge Cases:
        - validation_result is None → False
        - verification_summary missing → False
        - Any score is None → treated as 0 (fails threshold)
        - Empty dict → False (all scores default to 0)

    Example:
        >>> validation = {
        ...     'verification_summary': {
        ...         'completeness_score': 0.92,
        ...         'accuracy_score': 0.98,
        ...         'schema_compliance_score': 0.97,
        ...         'critical_issues': 0
        ...     }
        ... }
        >>> is_quality_sufficient(validation)  # True
        >>> is_quality_sufficient(None)  # False
        >>> is_quality_sufficient({})  # False
    """
    # Use default thresholds if not provided
    if thresholds is None:
        thresholds = DEFAULT_QUALITY_THRESHOLDS

    # Handle None validation_result
    if validation_result is None:
        return False

    summary = validation_result.get("verification_summary", {})

    # Handle missing or empty summary
    if not summary:
        return False

    # Helper to safely extract numeric scores (handle None values)
    def safe_score(key: str, default: float = 0.0) -> float:
        val = summary.get(key, default)
        return val if isinstance(val, int | float) else default

    # Check all thresholds
    return (
        safe_score("completeness_score") >= thresholds["completeness_score"]
        and safe_score("accuracy_score") >= thresholds["accuracy_score"]
        and safe_score("schema_compliance_score") >= thresholds["schema_compliance_score"]
        and safe_score("critical_issues", 999) <= thresholds["critical_issues"]
    )


def _extract_metrics(validation_result: dict) -> dict:
    """
    Extract key metrics from validation result for comparison.

    Used for:
    - Best iteration selection (_select_best_iteration)
    - Quality degradation detection (_detect_quality_degradation)
    - Progress tracking and UI display

    Returns dict with individual scores + computed 'overall_quality':
        - 40% completeness (coverage of PDF data)
        - 40% accuracy (correctness, no hallucinations)
        - 20% schema compliance (structural correctness)
    """
    summary = validation_result.get("verification_summary", {})

    return {
        "completeness_score": summary.get("completeness_score", 0),
        "accuracy_score": summary.get("accuracy_score", 0),
        "schema_compliance_score": summary.get("schema_compliance_score", 0),
        "critical_issues": summary.get("critical_issues", 0),
        "total_issues": summary.get("total_issues", 0),
        "overall_status": summary.get("overall_status", "unknown"),
        # Derived composite score (used by ranking and degradation detection)
        "overall_quality": (
            summary.get("completeness_score", 0) * 0.4
            + summary.get("accuracy_score", 0) * 0.4
            + summary.get("schema_compliance_score", 0) * 0.2
        ),
    }


def _detect_quality_degradation(iterations: list[dict], window: int = 2) -> bool:
    """
    Detect if quality has been degrading for the last N iterations.

    Early stopping prevents wasted LLM calls when corrections are making things worse.

    Args:
        iterations: List of all iteration data (each with 'metrics' dict)
        window: Number of consecutive degrading iterations to trigger stop (default: 2)

    Returns:
        True if quality degraded for 'window' consecutive iterations

    Logic:
        - Need at least (window + 1) iterations to detect trend
        - Compare last 'window' iterations against the OVERALL best score seen so far
        - Degradation = all iterations in window are worse than the peak quality
        - This catches systematic degradation, not transient noise

    Example:
        iterations = [
            {'metrics': {'overall_quality': 0.85}},  # iter 0
            {'metrics': {'overall_quality': 0.88}},  # iter 1 (BEST - peak quality)
            {'metrics': {'overall_quality': 0.86}},  # iter 2 (degraded from 0.88)
            {'metrics': {'overall_quality': 0.84}}   # iter 3 (degraded again)
        ]
        _detect_quality_degradation(iterations, window=2) → True
        # Last 2 iterations (0.86, 0.84) are BOTH worse than peak (0.88)
        # This indicates systematic degradation → stop and use iteration 1
    """
    if len(iterations) < window + 1:
        return False

    # Get quality scores
    scores = [it["metrics"].get("overall_quality", 0) for it in iterations]

    # Find OVERALL peak quality (not just before window)
    # This is the best score we've achieved across all iterations
    peak_quality = max(scores)

    # Check if last 'window' iterations are ALL worse than peak
    # This indicates systematic degradation, not just a single bad iteration
    window_scores = scores[-window:]
    all_degraded = all(score < peak_quality for score in window_scores)

    return all_degraded


def _run_extraction_step(
    pdf_path: Path,
    max_pages: int | None,
    classification_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """
    Run extraction step of the pipeline.

    Performs schema-based structured data extraction from PDF based on
    the publication type identified in classification step.

    Args:
        pdf_path: Path to the PDF file to extract from
        max_pages: Maximum number of pages to process (None = all pages)
        classification_result: Result from classification step containing publication_type
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates

    Returns:
        Dictionary containing extracted structured data

    Raises:
        SchemaLoadError: If schema file cannot be loaded
        PromptLoadError: If prompt file cannot be loaded
        LLMError: If LLM API call fails
    """
    console.print("[bold cyan]📊 Stap 2: Data Extractie (Schema-based)[/bold cyan]")

    start_time = time.time()

    # Strip metadata from classification before using
    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")

    _call_progress_callback(
        progress_callback,
        "extraction",
        "starting",
        {"publication_type": publication_type},
    )

    try:
        # Load appropriate extraction prompt and schema
        extraction_prompt = load_extraction_prompt(publication_type)
        extraction_schema = load_schema(publication_type)

        # Check schema compatibility with OpenAI
        compatibility = validate_schema_compatibility(extraction_schema)
        if compatibility["warnings"]:
            console.print("[yellow]⚠️  Schema compatibility warnings:[/yellow]")
            for warning in compatibility["warnings"][:3]:
                console.print(f"[dim]  • {warning}[/dim]")

        console.print(f"[dim]Running schema-based {publication_type} extraction with PDF upload...")
        console.print(f"[dim]Schema: ~{compatibility['estimated_tokens']} tokens[/dim]")

        # Run schema-based extraction with direct PDF upload
        extraction_result = llm.generate_json_with_pdf(
            pdf_path=pdf_path,
            schema=extraction_schema,
            system_prompt=extraction_prompt,
            max_pages=max_pages,
            schema_name=f"{publication_type}_extraction",
        )

        console.print("[green]✅ Schema-conforming extraction completed[/green]")

        # Add pipeline metadata
        elapsed = time.time() - start_time
        extraction_result["_pipeline_metadata"] = {
            "step": "extraction",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed,
            "llm_provider": _get_provider_name(llm),
            "model_used": extraction_result.get("_metadata", {}).get("model"),
            "max_pages": max_pages,
            "pdf_filename": pdf_path.name,
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
            "publication_type": publication_type,
        }

        # Save extraction result
        extraction_file = file_manager.save_json(extraction_result, "extraction")
        console.print(f"[green]✅ Extractie opgeslagen: {extraction_file}[/green]")

        # Extraction completed successfully
        elapsed = time.time() - start_time
        _call_progress_callback(
            progress_callback,
            "extraction",
            "completed",
            {
                "result": extraction_result,
                "elapsed_seconds": elapsed,
                "file_path": str(extraction_file),
                "publication_type": publication_type,
            },
        )

        return extraction_result

    except (SchemaLoadError, PromptLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Extractie fout: {e}[/red]")

        # Save error metadata (best effort)
        error_data = {
            "_pipeline_metadata": {
                "step": "extraction",
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
                "publication_type": publication_type,
            }
        }
        try:
            file_manager.save_json(error_data, "extraction", "failed")
        except Exception:
            pass  # Don't fail the error handling

        _call_progress_callback(
            progress_callback,
            "extraction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def _run_validation_step(
    extraction_result: dict[str, Any],
    pdf_path: Path,
    max_pages: int | None,
    classification_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
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

    Returns:
        Dictionary containing validation results with verification_summary

    Raises:
        LLMError: If LLM API call fails during semantic validation
    """
    console.print("[bold cyan]🔍 Stap 3: Validatie (Schema + LLM)[/bold cyan]")

    start_time = time.time()
    _call_progress_callback(progress_callback, STEP_VALIDATION, "starting", {})

    # Strip metadata from dependencies before using
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)
    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")

    # Run dual validation (schema + conditional LLM) with clean data
    validation_result = run_dual_validation(
        extraction_result=extraction_clean,
        pdf_path=pdf_path,
        max_pages=max_pages,
        publication_type=publication_type,
        llm=llm,
        console=console,
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

    validation_file = file_manager.save_json(validation_result, "validation")
    console.print(f"[green]✅ Validatie opgeslagen: {validation_file}[/green]")

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


def _run_correction_step(
    extraction_result: dict[str, Any],
    validation_result: dict[str, Any],
    pdf_path: Path,
    max_pages: int | None,
    publication_type: str,
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
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

    Returns:
        Tuple of (corrected_extraction, final_validation)

    Raises:
        PromptLoadError: If correction prompt cannot be loaded
        SchemaLoadError: If extraction schema cannot be loaded
        LLMError: If LLM API call fails
    """
    console.print("[bold cyan]🔧 Stap 4: Correctie[/bold cyan]")

    start_time = time.time()
    validation_status = validation_result.get("verification_summary", {}).get("overall_status")

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
        corrected_extraction = llm.generate_json_with_pdf(
            pdf_path=pdf_path,
            schema=extraction_schema,
            system_prompt=correction_prompt + "\n\n" + correction_context,
            max_pages=max_pages,
            schema_name=f"{publication_type}_extraction_corrected",
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

        corrected_file = file_manager.save_json(corrected_extraction, "extraction", "corrected")
        console.print(f"[green]✅ Correctie opgeslagen: {corrected_file}[/green]")

        # Final validation of corrected extraction - use same dual validation approach
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

        final_validation_file = file_manager.save_json(final_validation, "validation", "corrected")
        console.print(f"[green]✅ Finale validatie opgeslagen: {final_validation_file}[/green]")

        # Correction completed successfully
        elapsed = time.time() - start_time
        _call_progress_callback(
            progress_callback,
            "correction",
            "completed",
            {
                "result": corrected_extraction,
                "elapsed_seconds": elapsed,
                "extraction_file_path": str(corrected_file),
                "validation_file_path": str(final_validation_file),
                "final_validation_status": final_validation.get("verification_summary", {}).get(
                    "overall_status"
                ),
            },
        )

        return corrected_extraction, final_validation

    except (PromptLoadError, LLMError, SchemaLoadError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Correctie fout: {e}[/red]")

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
        except Exception:
            pass  # Don't fail the error handling

        _call_progress_callback(
            progress_callback,
            "correction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def _should_run_step(step_name: str, steps_to_run: list[str] | None) -> bool:
    """
    Check if step should be executed based on steps_to_run filter.

    Args:
        step_name: Step to check ("classification", "extraction", "validation", "correction")
        steps_to_run: Optional list of steps to execute (None = run all steps)

    Returns:
        True if step should run, False if step should be skipped

    Example:
        >>> _should_run_step("validation", ["classification", "extraction"])
        False
        >>> _should_run_step("extraction", None)
        True
    """
    if steps_to_run is None:
        return True  # Backwards compatible: run all steps
    return step_name in steps_to_run


def _validate_step_dependencies(steps_to_run: list[str]) -> None:
    """
    Validate step dependencies to ensure required steps are included.

    Pipeline dependencies:
    - Validation requires extraction (cannot validate without data)
    - Correction requires validation (cannot correct without validation report)
    - Extraction requires classification (cannot extract without knowing type)

    Args:
        steps_to_run: List of steps to execute

    Raises:
        ValueError: If step dependencies are violated

    Example:
        >>> _validate_step_dependencies(["validation"])  # Missing extraction
        Traceback (most recent call last):
        ...
        ValueError: Validation step requires extraction step
    """
    if STEP_VALIDATION in steps_to_run and STEP_EXTRACTION not in steps_to_run:
        raise ValueError("Validation step requires extraction step")

    if STEP_CORRECTION in steps_to_run and STEP_VALIDATION not in steps_to_run:
        raise ValueError("Correction step requires validation step")

    if STEP_EXTRACTION in steps_to_run and STEP_CLASSIFICATION not in steps_to_run:
        raise ValueError("Extraction step requires classification step")


def _run_classification_step(
    pdf_path: Path,
    max_pages: int | None,
    llm_provider: str,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
    have_llm_support: bool,
) -> dict[str, Any]:
    """
    Run classification step of the pipeline.

    Identifies publication type and extracts metadata from PDF using LLM.

    Args:
        pdf_path: Path to PDF file to process
        max_pages: Maximum pages to process (None = all pages)
        llm_provider: LLM provider name ("openai" or "claude")
        file_manager: File manager for saving results
        progress_callback: Optional callback for progress updates
        have_llm_support: Whether LLM modules are available

    Returns:
        Classification result dictionary with keys:
        - publication_type: str
        - metadata: dict

    Raises:
        RuntimeError: If LLM support not available
        LLMError: If LLM API call fails
        SchemaLoadError: If classification schema cannot be loaded
        PromptLoadError: If classification prompt cannot be loaded

    Example:
        >>> file_mgr = PipelineFileManager(Path("paper.pdf"))
        >>> result = _run_classification_step(
        ...     pdf_path=Path("paper.pdf"),
        ...     max_pages=20,
        ...     llm_provider="openai",
        ...     file_manager=file_mgr,
        ...     progress_callback=None,
        ...     have_llm_support=True
        ... )
        >>> result["publication_type"]
        'interventional_trial'
    """
    console.print("[bold cyan]📋 Stap 1: Classificatie[/bold cyan]")

    if not have_llm_support:
        console.print("[red]❌ LLM support niet beschikbaar[/red]")
        raise RuntimeError(
            "LLM support is required for pipeline execution. "
            "Please install required dependencies: pip install openai anthropic"
        )

    # Start classification with callback
    start_time = time.time()
    _call_progress_callback(
        progress_callback,
        "classification",
        "starting",
        {"pdf_path": str(pdf_path), "max_pages": max_pages},
    )

    try:
        # Load classification prompt and schema
        classification_prompt = load_classification_prompt()
        classification_schema = load_schema("classification")

        # Get LLM provider
        llm = get_llm_provider(llm_provider)

        # Run classification with direct PDF upload
        console.print("[dim]Uploading PDF for classification...[/dim]")
        classification_result = llm.generate_json_with_pdf(
            pdf_path=pdf_path,
            schema=classification_schema,
            system_prompt=classification_prompt,
            max_pages=max_pages,
            schema_name="classification",
        )

        # Add pipeline metadata
        elapsed = time.time() - start_time
        classification_result["_pipeline_metadata"] = {
            "step": "classification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed,
            "llm_provider": llm_provider,
            "model_used": classification_result.get("_metadata", {}).get("model"),
            "max_pages": max_pages,
            "pdf_filename": pdf_path.name,
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
        }

        # Save classification result
        classification_file = file_manager.save_json(classification_result, "classification")
        console.print(f"[green]✅ Classificatie opgeslagen: {classification_file}[/green]")

        # Classification completed successfully
        elapsed = time.time() - start_time
        _call_progress_callback(
            progress_callback,
            "classification",
            "completed",
            {
                "result": classification_result,
                "elapsed_seconds": elapsed,
                "file_path": str(classification_file),
            },
        )

        return classification_result

    except (PromptLoadError, LLMError, SchemaLoadError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Classificatie fout: {e}[/red]")

        # Save error metadata (best effort)
        error_data = {
            "_pipeline_metadata": {
                "step": "classification",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": elapsed,
                "llm_provider": llm_provider,
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
            file_manager.save_json(error_data, "classification", "failed")
        except Exception:
            pass  # Don't fail the error handling

        _call_progress_callback(
            progress_callback,
            "classification",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def run_single_step(
    step_name: str,
    pdf_path: Path,
    max_pages: int | None,
    llm_provider: str,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None = None,
    previous_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute a single pipeline step with dependency validation.

    This is the public API for step-by-step pipeline execution. It enables
    running individual steps independently with UI updates between steps,
    supporting iterative workflows and better user feedback.

    Args:
        step_name: Step to execute ("classification", "extraction", "validation", "correction")
        pdf_path: Path to PDF file to process
        max_pages: Maximum pages to process (None = all pages)
        llm_provider: LLM provider name ("openai" or "claude")
        file_manager: File manager for saving step results
        progress_callback: Optional callback for progress updates (step_name, status, data)
        previous_results: Results from previous steps (required for dependent steps)

    Returns:
        Dictionary containing step result. Key depends on step:
        - classification: {"publication_type": str, "metadata": dict, ...}
        - extraction: {"data": dict, ...}
        - validation: {"verification_summary": dict, ...}
        - correction: {"corrected_extraction": dict, "final_validation": dict}

    Raises:
        ValueError: If step_name is invalid
        ValueError: If required dependencies are missing from previous_results
        PromptLoadError: If prompt file cannot be loaded
        SchemaLoadError: If schema file cannot be loaded
        LLMError: If LLM API call fails
        RuntimeError: If LLM support is not available

    Example:
        >>> # Step 1: Classification (no dependencies)
        >>> fm = PipelineFileManager(pdf_path)
        >>> result1 = run_single_step(
        ...     "classification",
        ...     pdf_path,
        ...     max_pages=10,
        ...     llm_provider="openai",
        ...     file_manager=fm,
        ... )
        >>> # Step 2: Extraction (requires classification)
        >>> result2 = run_single_step(
        ...     "extraction",
        ...     pdf_path,
        ...     max_pages=10,
        ...     llm_provider="openai",
        ...     file_manager=fm,
        ...     previous_results={"classification": result1},
        ... )
    """
    # Validate step name
    if step_name not in ALL_PIPELINE_STEPS:
        raise ValueError(
            f"Invalid step_name '{step_name}'. Must be one of: {', '.join(ALL_PIPELINE_STEPS)}"
        )

    # Initialize previous_results if not provided
    if previous_results is None:
        previous_results = {}

    # Helper function to get result (from previous_results or load from disk)
    def _get_or_load_result(dep_step: str) -> dict[str, Any]:
        """
        Try to get step result from previous_results first, then load from disk.

        Args:
            dep_step: Dependency step name to load

        Returns:
            Result dictionary from step

        Raises:
            ValueError: If result not found in memory or on disk
        """
        # Check if result already in previous_results (current run)
        if dep_step in previous_results:
            return previous_results[dep_step]

        # Try loading from disk (previous run)
        result = file_manager.load_json(dep_step)
        if result is None:
            raise ValueError(
                f"{dep_step.title()} step result not found. "
                f"Please run {dep_step} step first or ensure "
                f"tmp/{file_manager.identifier}-{dep_step}.json exists."
            )

        console.print(f"[yellow]📂 Loaded {dep_step} result from disk[/yellow]")
        return result

    # Validate dependencies based on step and load if needed
    if step_name == STEP_EXTRACTION:
        classification_result = _get_or_load_result("classification")
        previous_results[STEP_CLASSIFICATION] = classification_result  # Cache in memory

    elif step_name == STEP_VALIDATION:
        classification_result = _get_or_load_result("classification")
        extraction_result = _get_or_load_result("extraction")
        previous_results[STEP_CLASSIFICATION] = classification_result
        previous_results[STEP_EXTRACTION] = extraction_result

    elif step_name == STEP_CORRECTION:
        classification_result = _get_or_load_result("classification")
        extraction_result = _get_or_load_result("extraction")
        validation_result = _get_or_load_result("validation")
        previous_results[STEP_CLASSIFICATION] = classification_result
        previous_results[STEP_EXTRACTION] = extraction_result
        previous_results[STEP_VALIDATION] = validation_result

        # Check if correction is actually needed
        validation_status = validation_result.get("verification_summary", {}).get("overall_status")
        if validation_status == "passed":
            raise ValueError(
                "Correction step not needed - validation passed. "
                "Only run correction when validation status is not 'passed'."
            )

    # Check LLM support availability
    try:
        from ..llm import get_llm_provider

        have_llm_support = True
    except ImportError:
        have_llm_support = False

    # Dispatch to appropriate step function
    if step_name == STEP_CLASSIFICATION:
        return _run_classification_step(
            pdf_path=pdf_path,
            max_pages=max_pages,
            llm_provider=llm_provider,
            file_manager=file_manager,
            progress_callback=progress_callback,
            have_llm_support=have_llm_support,
        )

    elif step_name == STEP_EXTRACTION:
        classification_result = previous_results[STEP_CLASSIFICATION]
        llm = get_llm_provider(llm_provider)

        return _run_extraction_step(
            pdf_path=pdf_path,
            max_pages=max_pages,
            classification_result=classification_result,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )

    elif step_name == STEP_VALIDATION:
        classification_result = previous_results[STEP_CLASSIFICATION]
        extraction_result = previous_results[STEP_EXTRACTION]
        llm = get_llm_provider(llm_provider)

        return _run_validation_step(
            extraction_result=extraction_result,
            pdf_path=pdf_path,
            max_pages=max_pages,
            classification_result=classification_result,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )

    elif step_name == STEP_CORRECTION:
        classification_result = previous_results[STEP_CLASSIFICATION]
        extraction_result = previous_results[STEP_EXTRACTION]
        validation_result = previous_results[STEP_VALIDATION]
        publication_type = classification_result.get("publication_type")
        llm = get_llm_provider(llm_provider)

        corrected_extraction, final_validation = _run_correction_step(
            extraction_result=extraction_result,
            validation_result=validation_result,
            pdf_path=pdf_path,
            max_pages=max_pages,
            publication_type=publication_type,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )

        # Return both corrected extraction and final validation
        return {
            "extraction_corrected": corrected_extraction,
            "validation_corrected": final_validation,
        }


def run_four_step_pipeline(
    pdf_path: Path,
    max_pages: int | None = None,
    llm_provider: str = "openai",
    breakpoint_after_step: str | None = None,
    have_llm_support: bool = True,
    steps_to_run: list[str] | None = None,
    progress_callback: Callable[[str, str, dict], None] | None = None,
) -> dict[str, Any]:
    """
    Four-step extraction pipeline with optional step filtering and progress callbacks.

    Coordinates the full extraction pipeline from PDF to validated structured data:
    1. Classification - Identify publication type + extract metadata
    2. Extraction - Detailed data extraction based on classified type
    3. Validation - Quality control with dual validation strategy
    4. Correction - Fix issues if validation indicates problems

    Args:
        pdf_path: Path to PDF file to process
        max_pages: Maximum pages to process (None = all pages, max 100)
        llm_provider: LLM provider to use ("openai" or "claude")
        breakpoint_after_step: Step name to pause after (for testing)
        have_llm_support: Whether LLM modules are available
        steps_to_run: Optional list of steps to execute. Valid steps:
            ["classification", "extraction", "validation", "correction"]
            None = run all steps (default, backwards compatible)
            Dependencies are validated automatically.
        progress_callback: Optional callback for progress updates.
            Signature: callback(step_name: str, status: str, data: dict)
            - step_name: "classification" | "extraction" | "validation" | "correction"
            - status: "starting" | "completed" | "failed" | "skipped"
            - data: dict with step-specific info (results, errors, timing, file_path)

    Returns:
        Dictionary with results from each completed step:
        {
            "classification": {...},
            "extraction": {...},
            "validation": {...},
            "extraction_corrected": {...},  # Only if correction ran
            "validation_corrected": {...}   # Only if correction ran
        }

    Raises:
        RuntimeError: If LLM support not available
        ValueError: If step dependencies are violated in steps_to_run
        LLMError: If LLM API calls fail
        SchemaLoadError: If schemas cannot be loaded
        PromptLoadError: If prompts cannot be loaded

    Example:
        >>> from pathlib import Path
        >>> # Basic usage (backwards compatible)
        >>> results = run_four_step_pipeline(
        ...     pdf_path=Path("paper.pdf"),
        ...     max_pages=20,
        ...     llm_provider="openai"
        ... )
        >>> results["classification"]["publication_type"]
        'interventional_trial'
        >>>
        >>> # With step filtering
        >>> results = run_four_step_pipeline(
        ...     pdf_path=Path("paper.pdf"),
        ...     steps_to_run=["classification", "extraction"]
        ... )
        >>>
        >>> # With progress callback
        >>> def my_callback(step, status, data):
        ...     print(f"{step}: {status}")
        >>> results = run_four_step_pipeline(
        ...     pdf_path=Path("paper.pdf"),
        ...     progress_callback=my_callback
        ... )
    """
    file_manager = PipelineFileManager(pdf_path)
    results = {}

    # Validate step dependencies if step filtering is enabled
    if steps_to_run is not None:
        _validate_step_dependencies(steps_to_run)

    # Define all steps in order
    all_steps = ALL_PIPELINE_STEPS

    # Execute each step using run_single_step()
    for step_name in all_steps:
        # Check if step should run
        if not _should_run_step(step_name, steps_to_run):
            _call_progress_callback(progress_callback, step_name, "skipped", {})
            console.print(f"[yellow]⏭️  {step_name.title()} skipped (not in steps_to_run)[/yellow]")

            # Classification cannot be skipped - it's required for all other steps
            if step_name == STEP_CLASSIFICATION:
                raise RuntimeError(
                    "Classification cannot be skipped - required for all other steps"
                )

            continue

        # Special handling for correction - skip if validation passed
        if step_name == STEP_CORRECTION:
            validation_result = results.get(STEP_VALIDATION)
            if validation_result:
                validation_status = validation_result.get("verification_summary", {}).get(
                    "overall_status"
                )
                if validation_status == "passed":
                    _call_progress_callback(
                        progress_callback,
                        STEP_CORRECTION,
                        "skipped",
                        {"reason": "validation_passed", "validation_status": validation_status},
                    )
                    console.print("[green]✅ Correction not needed - validation passed[/green]")
                    continue

        try:
            # Run single step with previous results
            step_result = run_single_step(
                step_name=step_name,
                pdf_path=pdf_path,
                max_pages=max_pages,
                llm_provider=llm_provider,
                file_manager=file_manager,
                progress_callback=progress_callback,
                previous_results=results,
            )

            # Store result
            if step_name == STEP_CORRECTION:
                # Correction returns dict with extraction_corrected and validation_corrected
                results["extraction_corrected"] = step_result["extraction_corrected"]
                results["validation_corrected"] = step_result["validation_corrected"]
            else:
                results[step_name] = step_result

        except Exception:
            # Error already handled in run_single_step() via progress callback
            raise

        # Check for breakpoint after this step
        if check_breakpoint(step_name, results, file_manager, breakpoint_after_step):
            return results

        # Check for publication_type == "overig" after classification
        if step_name == STEP_CLASSIFICATION:
            if step_result.get("publication_type") == "overig":
                console.print(
                    "[yellow]⚠️ Publicatietype 'overig' - "
                    "geen gespecialiseerde extractie beschikbaar[/yellow]"
                )
                return results

    return results
