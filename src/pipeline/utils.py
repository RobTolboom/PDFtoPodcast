# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Utility functions for pipeline operations.

This module provides helper functions for DOI handling, step navigation,
and breakpoint management used throughout the pipeline.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

from rich.console import Console

# Type alias for progress callback function signature
# Usage: progress_callback: ProgressCallback | None = None
ProgressCallback: TypeAlias = Callable[[str, str, dict[str, Any]], None]

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
        >>> get_next_step("podcast_generation")
        'None'
    """
    # All pipeline steps in execution order
    steps = [
        "classification",
        "extraction",
        "validation_correction",
        "appraisal",
        "report_generation",
        "podcast_generation",
    ]
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


def _call_progress_callback(
    callback: Any, step_name: str, status: str, data: dict[str, Any]
) -> None:
    """
    Helper to safely call progress callback if it exists.

    Args:
        callback: Callback function or None
        step_name: Name of current step
        status: Status string (starting, completed, failed, etc.)
        data: Data dictionary
    """
    if callback:
        try:
            callback(step_name, status, data)
        except Exception as e:
            console.print(f"[yellow]⚠️ Progress callback failed: {e}[/yellow]")


def _remove_null_values(obj: Any) -> Any:
    """
    Recursively remove null values from dicts and lists.

    LLMs sometimes emit null for absent optional fields despite prompt instructions
    to omit them (e.g., "Never emit null"). This causes schema validation failures
    since null is not a valid type for most fields.

    Args:
        obj: Any JSON-compatible object (dict, list, or primitive)

    Returns:
        Object with all null values removed from dicts and lists
    """
    if isinstance(obj, dict):
        return {k: _remove_null_values(v) for k, v in obj.items() if v is not None}
    elif isinstance(obj, list):
        return [_remove_null_values(item) for item in obj if item is not None]
    return obj


def _strip_metadata_for_pipeline(data: dict[str, Any]) -> dict[str, Any]:
    """
    Remove EXTRA metadata fields added by code before schema validation.

    After each pipeline step, the code adds EXTRA tracking/debugging metadata to the
    result JSON and saves it to file. When loading this JSON for the next step,
    these EXTRA fields must be stripped before schema validation, otherwise it fails
    with "Additional properties are not allowed".

    Strips EXTRA fields that are NOT part of the schema:
    - usage: Token consumption statistics (added by LLM providers)
    - _metadata: LLM response metadata (response_id, model, etc.)
    - _pipeline_metadata: Pipeline execution metadata (step, timestamp, etc.)
    - correction_notes: Debugging notes from correction step

    IMPORTANT: Does NOT remove the schema "metadata" field (title, authors, DOI, etc.)
    which is a required part of the extraction/report/podcast schema.

    Args:
        data: Input dictionary loaded from JSON file

    Returns:
        Copy of dictionary with EXTRA metadata removed, ready for schema validation
    """
    data_copy = data.copy()

    # Remove EXTRA LLM metadata fields (added by providers after generation)
    data_copy.pop("usage", None)
    data_copy.pop("_metadata", None)

    # Remove EXTRA pipeline metadata (added by orchestrator after each step)
    data_copy.pop("_pipeline_metadata", None)

    # Remove EXTRA debugging fields (added during correction)
    data_copy.pop("correction_notes", None)

    # KEEP schema "metadata" field - it's part of the schema!
    # Do NOT remove it

    # Remove null values that LLM incorrectly included (should be omitted per prompt)
    data_copy = _remove_null_values(data_copy)

    return data_copy
