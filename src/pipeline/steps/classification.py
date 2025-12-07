# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Classification step module.

Handles publication type identification and metadata extraction from PDF documents.
"""

import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from ...llm import LLMError, get_llm_provider
from ...prompts import PromptLoadError, load_classification_prompt
from ...schemas_loader import SchemaLoadError, load_schema
from ..file_manager import PipelineFileManager
from ..utils import _call_progress_callback

console = Console()


def run_classification_step(
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
        >>> result = run_classification_step(
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
    console.print("\n[bold magenta]═══ STEP 1: CLASSIFICATION ═══[/bold magenta]\n")

    if not have_llm_support:
        console.print("[red]❌ LLM support not available[/red]")
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
        from ...config import llm_settings

        classification_result = llm.generate_json_with_pdf(
            pdf_path=pdf_path,
            schema=classification_schema,
            system_prompt=classification_prompt,
            max_pages=max_pages,
            schema_name="classification",
            reasoning_effort=llm_settings.reasoning_effort_classification,
        )

        publication_type = classification_result.get("publication_type", "unknown")
        confidence = classification_result.get("classification_confidence")
        if confidence is not None:
            console.print(
                f"[cyan]🔎 Predicted type: {publication_type} "
                f"({confidence:.1%} confidence)[/cyan]"
            )
        else:
            console.print(f"[cyan]🔎 Predicted type: {publication_type}[/cyan]")

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

        # Display classification result summary
        publication_type = classification_result.get("publication_type", "unknown")
        model_used = classification_result.get("_metadata", {}).get("model", llm_provider)

        console.print("\n[bold]Classification Result:[/bold]")
        console.print(f"  Publication Type: [cyan]{publication_type}[/cyan]")
        console.print(f"  Model: [dim]{model_used}[/dim]")
        console.print(f"  Duration: [dim]{elapsed:.1f}s[/dim]\n")

        # Save classification result
        classification_file = file_manager.save_json(classification_result, "classification")
        console.print(f"[dim]Saved: {classification_file.name}[/dim]")
        console.print("[green]✅ Classification complete[/green]")

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
        console.print(f"[red]❌ Classification error: {e}[/red]")

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


# Backward compatibility alias
_run_classification_step = run_classification_step
