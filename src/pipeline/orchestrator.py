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


def run_four_step_pipeline(
    pdf_path: Path,
    max_pages: int | None = None,
    llm_provider: str = "openai",
    breakpoint_after_step: str | None = None,
    have_llm_support: bool = True,
) -> dict[str, Any]:
    """
    Four-step extraction pipeline with filename-based file management.

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
        LLMError: If LLM API calls fail
        SchemaLoadError: If schemas cannot be loaded
        PromptLoadError: If prompts cannot be loaded

    Example:
        >>> from pathlib import Path
        >>> results = run_four_step_pipeline(
        ...     pdf_path=Path("paper.pdf"),
        ...     max_pages=20,
        ...     llm_provider="openai"
        ... )
        >>> results["classification"]["publication_type"]
        'interventional_trial'
    """
    file_manager = PipelineFileManager(pdf_path)
    results = {}

    console.print("[bold cyan]📋 Stap 1: Classificatie[/bold cyan]")

    if not have_llm_support:
        console.print("[red]❌ LLM support niet beschikbaar[/red]")
        raise RuntimeError(
            "LLM support is required for pipeline execution. "
            "Please install required dependencies: pip install openai anthropic"
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

    except (PromptLoadError, LLMError, SchemaLoadError) as e:
        console.print(f"[red]❌ Classificatie fout: {e}[/red]")
        raise

    # Save classification result
    classification_file = file_manager.save_json(classification_result, "classification")
    console.print(f"[green]✅ Classificatie opgeslagen: {classification_file}[/green]")
    results["classification"] = classification_result

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

        console.print(
            f"[dim]Running schema-based {publication_type} extraction with PDF upload..."
        )
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

    except (SchemaLoadError, PromptLoadError, LLMError) as e:
        console.print(f"[red]❌ Extractie fout: {e}[/red]")
        raise

    extraction_file = file_manager.save_json(extraction_result, "extraction")
    console.print(f"[green]✅ Extractie opgeslagen: {extraction_file}[/green]")
    results["extraction"] = extraction_result

    # Check for breakpoint after extraction
    if check_breakpoint("extraction", results, file_manager, breakpoint_after_step):
        return results

    # STEP 3: VALIDATION
    console.print("[bold cyan]🔍 Stap 3: Validatie (Schema + LLM)[/bold cyan]")

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

    # Check for breakpoint after validation
    if check_breakpoint("validation", results, file_manager, breakpoint_after_step):
        return results

    # STEP 4: CORRECTION (conditional)
    validation_status = validation_result.get("verification_summary", {}).get("overall_status")
    if validation_status != "passed":
        console.print("[bold cyan]🔧 Stap 4: Correctie[/bold cyan]")

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

        except (PromptLoadError, LLMError, SchemaLoadError) as e:
            console.print(f"[red]❌ Correctie fout: {e}[/red]")
            raise

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

        # Check for breakpoint after correction
        if check_breakpoint("correction", results, file_manager, breakpoint_after_step):
            return results

    return results
