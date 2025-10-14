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

PDF Upload Strategy:
    All LLM steps use direct PDF upload (no text extraction) to preserve:
    - Tables and figures (critical for medical research data)
    - Images and charts (visual data representation)
    - Complex formatting and layout information
    - Complete document structure and context

    Cost: ~1,500-3,000 tokens per page (3-6x more than text extraction)
    Benefit: Complete data fidelity - no loss of tables, images, or formatting
"""

import json
import time
from collections.abc import Callable
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
    if "validation" in steps_to_run and "extraction" not in steps_to_run:
        raise ValueError("Validation step requires extraction step")

    if "correction" in steps_to_run and "validation" not in steps_to_run:
        raise ValueError("Correction step requires validation step")

    if "extraction" in steps_to_run and "classification" not in steps_to_run:
        raise ValueError("Extraction step requires classification step")


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

    # STEP 1: CLASSIFICATION
    console.print("[bold cyan]📋 Stap 1: Classificatie[/bold cyan]")

    # Check if classification should be skipped
    if not _should_run_step("classification", steps_to_run):
        _call_progress_callback(progress_callback, "classification", "skipped", {})
        console.print("[yellow]⏭️  Classification skipped (not in steps_to_run)[/yellow]")
        # Classification is required for all other steps - cannot skip
        raise RuntimeError("Classification cannot be skipped - required for all other steps")

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

        # Save classification result
        classification_file = file_manager.save_json(classification_result, "classification")
        console.print(f"[green]✅ Classificatie opgeslagen: {classification_file}[/green]")
        results["classification"] = classification_result

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

    except (PromptLoadError, LLMError, SchemaLoadError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Classificatie fout: {e}[/red]")
        _call_progress_callback(
            progress_callback,
            "classification",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise

    # Check for breakpoint after classification
    if check_breakpoint("classification", results, file_manager, breakpoint_after_step):
        return results

    if classification_result["publication_type"] == "overig":
        console.print(
            "[yellow]⚠️ Publicatietype 'overig' - "
            "geen gespecialiseerde extractie beschikbaar[/yellow]"
        )
        return results

    # STEP 2: EXTRACTION
    console.print("[bold cyan]📊 Stap 2: Data Extractie (Schema-based)[/bold cyan]")

    # Check if extraction should be skipped
    if not _should_run_step("extraction", steps_to_run):
        _call_progress_callback(progress_callback, "extraction", "skipped", {})
        console.print("[yellow]⏭️  Extraction skipped (not in steps_to_run)[/yellow]")
        return results

    # Start extraction with callback
    start_time = time.time()
    _call_progress_callback(
        progress_callback,
        "extraction",
        "starting",
        {"publication_type": classification_result.get("publication_type")},
    )

    try:
        publication_type = classification_result.get("publication_type")

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

        # Save extraction result
        extraction_file = file_manager.save_json(extraction_result, "extraction")
        console.print(f"[green]✅ Extractie opgeslagen: {extraction_file}[/green]")
        results["extraction"] = extraction_result

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

    except (SchemaLoadError, PromptLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Extractie fout: {e}[/red]")
        _call_progress_callback(
            progress_callback,
            "extraction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise

    # Check for breakpoint after extraction
    if check_breakpoint("extraction", results, file_manager, breakpoint_after_step):
        return results

    # STEP 3: VALIDATION
    console.print("[bold cyan]🔍 Stap 3: Validatie (Schema + LLM)[/bold cyan]")

    # Check if validation should be skipped
    if not _should_run_step("validation", steps_to_run):
        _call_progress_callback(progress_callback, "validation", "skipped", {})
        console.print("[yellow]⏭️  Validation skipped (not in steps_to_run)[/yellow]")
        return results

    # Start validation with callback
    start_time = time.time()
    _call_progress_callback(progress_callback, "validation", "starting", {})

    # Run dual validation (schema + conditional LLM)
    publication_type = classification_result.get("publication_type")
    validation_result = run_dual_validation(
        extraction_result=extraction_result,
        pdf_path=pdf_path,
        max_pages=max_pages,
        publication_type=publication_type,
        llm=llm,
        console=console,
    )

    validation_file = file_manager.save_json(validation_result, "validation")
    console.print(f"[green]✅ Validatie opgeslagen: {validation_file}[/green]")
    results["validation"] = validation_result

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

    # Check for breakpoint after validation
    if check_breakpoint("validation", results, file_manager, breakpoint_after_step):
        return results

    # STEP 4: CORRECTION (conditional)
    validation_status = validation_result.get("verification_summary", {}).get("overall_status")

    # Check if correction should be skipped
    if not _should_run_step("correction", steps_to_run):
        _call_progress_callback(progress_callback, "correction", "skipped", {})
        console.print("[yellow]⏭️  Correction skipped (not in steps_to_run)[/yellow]")
        return results

    # Skip correction if validation passed
    if validation_status == "passed":
        _call_progress_callback(
            progress_callback,
            "correction",
            "skipped",
            {"reason": "validation_passed", "validation_status": validation_status},
        )
        console.print("[green]✅ Correction not needed - validation passed[/green]")
        return results

    # Correction needed - validation did not pass
    console.print("[bold cyan]🔧 Stap 4: Correctie[/bold cyan]")

    # Start correction with callback
    start_time = time.time()
    _call_progress_callback(
        progress_callback,
        "correction",
        "starting",
        {"validation_status": validation_status},
    )

    try:
        # Load correction prompt and extraction schema
        correction_prompt = load_correction_prompt()
        extraction_schema = load_schema(publication_type)

        # Prepare correction context with original extraction and validation feedback
        correction_context = f"""
ORIGINAL_EXTRACTION: {json.dumps(extraction_result, indent=2)}

VALIDATION_REPORT: {json.dumps(validation_result, indent=2)}

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

        corrected_file = file_manager.save_json(corrected_extraction, "extraction", "corrected")
        console.print(f"[green]✅ Correctie opgeslagen: {corrected_file}[/green]")

        # Final validation of corrected extraction - use same dual validation approach
        console.print("[dim]Running final validation on corrected extraction...[/dim]")

        # Re-run dual validation on corrected extraction
        final_validation = run_dual_validation(
            extraction_result=corrected_extraction,
            pdf_path=pdf_path,
            max_pages=max_pages,
            publication_type=publication_type,
            llm=llm,
            console=console,
        )

        final_validation_file = file_manager.save_json(final_validation, "validation", "corrected")
        console.print(f"[green]✅ Finale validatie opgeslagen: {final_validation_file}[/green]")

        results["extraction_corrected"] = corrected_extraction
        results["validation_corrected"] = final_validation

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

        # Check for breakpoint after correction
        if check_breakpoint("correction", results, file_manager, breakpoint_after_step):
            return results

    except (PromptLoadError, LLMError, SchemaLoadError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Correctie fout: {e}[/red]")
        _call_progress_callback(
            progress_callback,
            "correction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise

    return results
