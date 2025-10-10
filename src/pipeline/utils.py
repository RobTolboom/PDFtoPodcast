# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Utility functions for pipeline operations.

This module provides helper functions for DOI handling, step navigation,
and breakpoint management used throughout the pipeline.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console

if TYPE_CHECKING:
    from .file_manager import PipelineFileManager

console = Console()


def doi_to_safe_filename(doi: str) -> str:
    """
    Convert DOI to filesystem-safe string.

    Args:
        doi: DOI string (may include 'doi:' prefix)

    Returns:
        Filesystem-safe version of DOI with slashes and colons replaced

    Example:
        >>> doi_to_safe_filename("10.1234/example.2025")
        '10-1234-example-2025'
        >>> doi_to_safe_filename("doi:10.1234/test")
        '10-1234-test'
    """
    # Remove 'doi:' prefix if present
    if doi.lower().startswith("doi:"):
        doi = doi[4:]

    # Replace problematic characters with hyphens
    safe_doi = doi.replace("/", "-").replace(":", "-").replace(".", "-")
    return safe_doi


def get_file_identifier(classification_result: dict[str, Any], pdf_path: Path) -> str:
    """
    Get identifier for filenames, preferring DOI over fallback.

    Args:
        classification_result: Classification result dict with metadata
        pdf_path: Path to original PDF file

    Returns:
        File identifier string (safe DOI or PDF stem with timestamp)

    Example:
        >>> from pathlib import Path
        >>> result = {"metadata": {"doi": "10.1234/test"}}
        >>> get_file_identifier(result, Path("paper.pdf"))
        '10-1234-test'
        >>> result = {"metadata": {}}  # No DOI
        >>> get_file_identifier(result, Path("paper.pdf"))
        'paper_20250109_143022'  # timestamp will vary
    """
    doi = classification_result.get("metadata", {}).get("doi")

    if doi:
        return doi_to_safe_filename(doi)
    else:
        # Fallback: PDF name + timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{pdf_path.stem}_{timestamp}"


def get_next_step(current_step: str) -> str:
    """
    Get the name of the next pipeline step.

    Args:
        current_step: Current step name

    Returns:
        Next step name, or "None" if current step is last or invalid

    Example:
        >>> get_next_step("classification")
        'extraction'
        >>> get_next_step("correction")
        'None'
    """
    steps = ["classification", "extraction", "validation", "correction"]
    try:
        idx = steps.index(current_step)
        return steps[idx + 1] if idx + 1 < len(steps) else "None"
    except ValueError:
        return "None"


def check_breakpoint(
    step_name: str,
    results: dict[str, Any],
    file_manager: "PipelineFileManager",
    breakpoint_after_step: str | None = None,
) -> bool:
    """
    Check if pipeline should stop at this step for testing.

    Args:
        step_name: Name of current step
        results: Pipeline results dict
        file_manager: File manager instance
        breakpoint_after_step: Step name to break after (None = no breakpoint)

    Returns:
        True if breakpoint triggered (stop pipeline), False otherwise

    Example:
        >>> check_breakpoint("extraction", {}, manager, "extraction")
        True  # Will print breakpoint message
        >>> check_breakpoint("extraction", {}, manager, "validation")
        False  # Continue to next step
    """
    if breakpoint_after_step == step_name:
        console.print(
            f"\n[bold yellow]⏸️  BREAKPOINT: Stopped after '{step_name}' step[/bold yellow]"
        )
        console.print("[dim]Pipeline paused for step-by-step testing.[/dim]")
        console.print(f"[dim]Results saved to: tmp/{file_manager.identifier}-*[/dim]")
        console.print(
            f"\n[dim]💡 To continue: Set BREAKPOINT_AFTER_STEP = '{get_next_step(step_name)}' or None[/dim]"
        )
        return True
    return False
