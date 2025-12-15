# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
UI display functions for pipeline execution screen.

This module provides step status display, verbose logging, and error rendering
for the Streamlit pipeline interface.

Public API:
    - display_step_status(): Render step progress UI with result details
    - display_verbose_info(): Show verbose logging details
    - display_error_with_guidance(): Show error with troubleshooting

Re-exported from submodules (for backward compatibility):
    - display_report_artifacts(): From execution_artifacts
    - display_podcast_artifacts(): From execution_artifacts
    - display_*_result(): From execution_results
"""

import streamlit as st

from src.pipeline.orchestrator import (
    STEP_APPRAISAL,
    STEP_CLASSIFICATION,
    STEP_CORRECTION,
    STEP_EXTRACTION,
    STEP_REPORT_GENERATION,
    STEP_VALIDATION,
    STEP_VALIDATION_CORRECTION,
)

# Re-export artifact functions for backward compatibility
from .execution_artifacts import (  # noqa: F401
    display_podcast_artifacts,
    display_report_artifacts,
)
from .execution_callbacks import (
    classify_error_type,
    extract_token_usage,
    get_error_guidance,
)

# Re-export result display functions for backward compatibility
from .execution_results import (  # noqa: F401
    display_appraisal_result,
    display_classification_result,
    display_correction_result,
    display_extraction_result,
    display_report_result,
    display_validation_correction_result,
    display_validation_result,
    trigger_appraisal_rerun,
    trigger_report_rerun,
)


def display_verbose_info(step_name: str, verbose_data: dict, result: dict | None):
    """
    Display verbose logging information for a pipeline step.

    Shows detailed information when verbose logging is enabled, including:
    - Starting data (PDF path, publication type, etc.)
    - Completion data (file path, token usage)
    - Timing details

    Args:
        step_name: Step identifier ("classification", "extraction", "validation", "correction")
        verbose_data: Dict of callback data by status {starting: {...}, completed: {...}}
        result: Step result dictionary (may contain token usage)

    Example:
        >>> display_verbose_info("classification", {...}, {...})
        # Renders verbose details in Streamlit UI
    """
    st.markdown("#### Verbose Details")

    # Display starting data
    starting_data = verbose_data.get("starting", {})
    if starting_data:
        st.markdown("**Starting parameters:**")

        if step_name == STEP_CLASSIFICATION:
            if "pdf_path" in starting_data:
                st.write(f"- PDF: `{starting_data['pdf_path']}`")
            if "max_pages" in starting_data:
                max_pages = starting_data["max_pages"] or "All"
                st.write(f"- Max pages: {max_pages}")

        elif step_name == STEP_EXTRACTION:
            if "publication_type" in starting_data:
                st.write(f"- Publication type: `{starting_data['publication_type']}`")

        elif step_name == STEP_CORRECTION:
            if "validation_status" in starting_data:
                st.write(f"- Validation status: {starting_data['validation_status']}")

    # Display token usage if available
    if result:
        token_usage = extract_token_usage(result)
        if token_usage:
            st.markdown("**Token usage:**")
            if "input" in token_usage:
                st.write(f"- Input tokens: {token_usage['input']:,}")
            if "output" in token_usage:
                st.write(f"- Output tokens: {token_usage['output']:,}")
            if "total" in token_usage:
                st.write(f"- Total tokens: {token_usage['total']:,}")

        # Display cached tokens if available (cost optimization)
        usage = result.get("usage", {})
        cached_tokens = usage.get("cached_tokens")
        if cached_tokens:
            st.markdown("**Cache efficiency:**")
            input_tokens = usage.get("input_tokens", 0)
            if input_tokens > 0:
                cache_hit_pct = (cached_tokens / input_tokens) * 100
                st.write(f"- Cached tokens: {cached_tokens:,} ({cache_hit_pct:.1f}% cache hit)")
            else:
                st.write(f"- Cached tokens: {cached_tokens:,}")

        # Display reasoning tokens if significant
        reasoning_tokens = usage.get("reasoning_tokens")
        if reasoning_tokens:
            st.markdown("**Reasoning tokens:**")
            output_tokens = usage.get("output_tokens", 0)
            if output_tokens > 0:
                reasoning_pct = (reasoning_tokens / output_tokens) * 100
                st.write(f"- Reasoning: {reasoning_tokens:,} ({reasoning_pct:.1f}% of output)")
            else:
                st.write(f"- Reasoning: {reasoning_tokens:,}")

        # Display response metadata
        metadata = result.get("_metadata", {})
        if metadata:
            st.markdown("**Response metadata:**")
            if "model" in metadata:
                st.write(f"- Model: `{metadata['model']}`")
            if "response_id" in metadata:
                st.write(f"- Response ID: `{metadata['response_id']}`")
            if "status" in metadata:
                st.write(f"- Status: {metadata['status']}")
            if "stop_reason" in metadata:
                st.write(f"- Stop reason: {metadata['stop_reason']}")

            # Expandable reasoning summary for GPT-5/o-series
            reasoning = metadata.get("reasoning", {})
            if reasoning and "summary" in reasoning:
                with st.expander("Reasoning Summary"):
                    st.write(reasoning["summary"])
                    if "effort" in reasoning:
                        st.caption(f"Effort level: {reasoning['effort']}")

    # Display completion data
    completed_data = verbose_data.get("completed", {})
    if completed_data:
        # File path is already shown in main display, but can show size here
        if "file_path" in completed_data:
            file_path = completed_data["file_path"]
            st.caption(f"Output: `{file_path}`")


def display_error_with_guidance(error_msg: str, step_name: str, step: dict):
    """
    Display error with actionable guidance and troubleshooting steps.

    Shows:
    - Error title and user-friendly message
    - Numbered action steps
    - Expandable technical details section

    Args:
        error_msg: Error message from exception
        step_name: Step where error occurred
        step: Step status dict (may contain additional error info)

    Example:
        >>> display_error_with_guidance("401 Unauthorized", "classification", {...})
        # Renders error with guidance in Streamlit UI
    """
    # Classify error and get guidance
    error_type = classify_error_type(error_msg, step_name)
    guidance = get_error_guidance(error_type, error_msg)

    # Display error title and message
    st.error(f"**{guidance['title']}**")
    st.markdown(guidance["message"])

    # Display action steps
    st.markdown("**Troubleshooting steps:**")
    for i, action in enumerate(guidance["actions"], 1):
        st.markdown(f"{i}. {action}")

    # Expandable technical details
    with st.expander("Technical Details"):
        st.code(guidance["technical_details"], language="text")

        # Show additional context if available
        if "error_type" in step.get("verbose_data", {}).get("failed", {}):
            error_type_name = step["verbose_data"]["failed"]["error_type"]
            st.caption(f"**Exception type:** `{error_type_name}`")


def check_validation_warnings(validation_result: dict) -> list[str]:
    """
    Check validation result for non-critical warnings.

    Args:
        validation_result: Validation result dictionary

    Returns:
        List of warning messages (empty if no warnings)

    Example:
        >>> result = {"is_valid": True, "quality_score": 6}
        >>> check_validation_warnings(result)
        ['Quality score is 6/10 (below recommended 8)']
    """
    warnings = []

    # Check quality score
    quality_score = validation_result.get("quality_score")
    if quality_score is not None and quality_score < 8:
        warnings.append(f"Quality score is {quality_score}/10 (below recommended 8)")

    # Check for minor schema errors (errors exist but validation passed)
    is_valid = validation_result.get("is_valid", False)
    errors = validation_result.get("errors", [])
    if is_valid and errors:
        error_count = len(errors)
        warnings.append(f"{error_count} minor schema issue(s) found but validation passed")

    return warnings


def display_step_status(step_name: str, step_label: str, step_number: int):
    """
    Display status UI for a single pipeline step.

    Renders a Streamlit status container with:
    - Status icon (Pending / Running / Success / Failed / Skipped)
    - Elapsed time (for running/completed steps)
    - Error message (for failed steps)
    - Result summary (for successful steps)
    - Expandable details section (collapsed by default for success)

    Args:
        step_name: Step identifier ("classification", "extraction", "validation", "correction")
        step_label: Human-readable label ("Classification", "Extraction", etc.)
        step_number: Step number (1-6) for display

    Status Icons:
        - pending: (not yet started)
        - running: (currently executing)
        - success: (completed successfully)
        - failed: (critical error, pipeline stopped)
        - skipped: (step not selected or not needed)

    Container Expansion:
        - pending/skipped: Not expandable
        - running/failed: Auto-expanded to show progress/error
        - success: Collapsed by default, user can expand for details

    Example:
        >>> display_step_status("classification", "Classification", 1)
        # Renders: "Step 1: Classification  Completed in 8.3s"
        # Expandable content shows: Publication Type, DOI

    Note:
        Reads step status from st.session_state.step_status[step_name].
        Must call init_execution_state() before using this function.
    """
    step = st.session_state.step_status[step_name]
    status = step["status"]

    # Status icon mapping (emoji icons work in all contexts)
    icons = {
        "pending": "⏳",
        "running": "🔄",
        "success": "✅",
        "failed": "❌",
        "skipped": "⏭️",
    }

    icon = icons.get(status, "❓")
    label = f"Step {step_number}: {step_label}"

    # Calculate elapsed time (only for completed/failed steps)
    elapsed_text = ""
    if step["elapsed_seconds"] is not None:
        elapsed = step["elapsed_seconds"]
        elapsed_text = f" - {elapsed:.1f}s"

    # Status container configuration
    if status == "pending":
        # Not expandable for pending
        st.markdown(f"{icon} **{label}** - Not yet started")

    elif status == "running":
        # Auto-expanded for running (no elapsed time - it's static during execution)
        with st.status(f"{icon} {label} - Running", expanded=True):
            st.write(f"**Started:** {step['start_time'].strftime('%H:%M:%S')}")
            st.write("Executing pipeline step...")

    elif status == "success":
        # Collapsed by default for success, with result summary
        with st.status(f"{icon} {label} - Completed{elapsed_text}", expanded=False):
            # Show timing
            st.write(f"**Completed:** {step['end_time'].strftime('%H:%M:%S')}")

            # Show step-specific result summary
            result = step.get("result")
            if result:
                st.markdown("---")
                if step_name == STEP_CLASSIFICATION:
                    display_classification_result(result)
                elif step_name == STEP_EXTRACTION:
                    display_extraction_result(result)
                elif step_name == STEP_VALIDATION:
                    display_validation_result(result)
                elif step_name == STEP_CORRECTION:
                    display_correction_result(result)
                elif step_name == STEP_VALIDATION_CORRECTION:
                    display_validation_correction_result(result)
                elif step_name == STEP_APPRAISAL:
                    display_appraisal_result(result)
                elif step_name == STEP_REPORT_GENERATION:
                    display_report_result(result)

            # Show file path if available (non-verbose always shows this)
            file_path = step.get("file_path")
            if file_path:
                st.caption(f"**Saved:** `{file_path}`")

            # Show verbose logging details if enabled
            verbose_enabled = st.session_state.settings.get("verbose_logging", False)
            if verbose_enabled:
                verbose_data = step.get("verbose_data", {})
                if verbose_data or result:
                    st.markdown("---")
                    display_verbose_info(step_name, verbose_data, result)

    elif status == "failed":
        # Auto-expanded for errors with actionable guidance
        with st.status(f"{icon} {label} - Failed{elapsed_text}", expanded=True, state="error"):
            # Display error with guidance and troubleshooting steps
            display_error_with_guidance(step["error"], step_name, step)

            # Show timing
            st.markdown("---")
            if step["start_time"]:
                st.write(f"**Started:** {step['start_time'].strftime('%H:%M:%S')}")
            if step["end_time"]:
                st.write(f"**Failed:** {step['end_time'].strftime('%H:%M:%S')}")

    elif status == "skipped":
        # Simple text for skipped
        st.markdown(f"{icon} **{label}** - Skipped")
