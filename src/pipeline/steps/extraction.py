# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Extraction step module.

Handles schema-based structured data extraction from PDF documents.
"""

import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from ...llm import LLMError
from ...prompts import PromptLoadError, load_extraction_prompt
from ...schemas_loader import SchemaLoadError, load_schema, validate_schema_compatibility
from ..file_manager import PipelineFileManager
from ..utils import _call_progress_callback, _get_provider_name, _strip_metadata_for_pipeline

console = Console()


def run_extraction_step(
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

    Example:
        >>> from src.llm import get_llm_provider
        >>> file_mgr = PipelineFileManager(Path("paper.pdf"))
        >>> llm = get_llm_provider("openai")
        >>> result = run_extraction_step(
        ...     pdf_path=Path("paper.pdf"),
        ...     max_pages=20,
        ...     classification_result={"publication_type": "interventional_trial"},
        ...     llm=llm,
        ...     file_manager=file_mgr,
        ...     progress_callback=None
        ... )
    """
    console.print("\n[bold magenta]═══ STEP 2: DATA EXTRACTION (SCHEMA-BASED) ═══[/bold magenta]\n")

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

        console.print(
            f"[cyan]⚙️  Extraction prompt: {publication_type} schema (~{compatibility['estimated_tokens']} tokens)[/cyan]"
        )
        console.print("[dim]Uploading PDF for extraction...[/dim]")

        # Run schema-based extraction with direct PDF upload
        from ...config import llm_settings

        extraction_result = llm.generate_json_with_pdf(
            pdf_path=pdf_path,
            schema=extraction_schema,
            system_prompt=extraction_prompt,
            max_pages=max_pages,
            schema_name=f"{publication_type}_extraction",
            reasoning_effort=llm_settings.reasoning_effort_extraction,
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

        # Display extraction summary
        model_used = extraction_result.get("_metadata", {}).get("model", _get_provider_name(llm))

        console.print("\n[bold]Extraction Summary:[/bold]")
        console.print(f"  Publication Type: [cyan]{publication_type}[/cyan]")
        console.print(f"  Model: [dim]{model_used}[/dim]")
        console.print(f"  Duration: [dim]{elapsed:.1f}s[/dim]\n")

        # Save extraction result (iteration 0)
        extraction_file = file_manager.save_json(
            extraction_result, "extraction", iteration_number=0
        )
        console.print(f"[dim]Saved: {extraction_file.name}[/dim]")
        console.print("[green]✅ Extraction complete[/green]")

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
        console.print(f"[red]❌ Extraction error: {e}[/red]")

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
        except Exception as save_err:
            console.print(f"[yellow]⚠️ Failed to save error metadata: {save_err}[/yellow]")

        _call_progress_callback(
            progress_callback,
            "extraction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


# Backward compatibility alias
_run_extraction_step = run_extraction_step
