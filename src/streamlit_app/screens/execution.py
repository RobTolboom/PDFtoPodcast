# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Pipeline execution screen for Streamlit interface.

Provides real-time pipeline execution UI with progress tracking, intelligent error
handling, and session state management. Implements rerun prevention to avoid pipeline
restart on UI interactions.

Components:
    - init_execution_state(): Initialize execution and step_status session state
    - reset_execution_state(): Reset state for retry/navigation
    - display_step_status(): Render step progress UI with status indicators
    - show_execution_screen(): Main screen function with state machine logic

Session State Schema:
    st.session_state.execution = {
        "status": "idle" | "running" | "completed" | "failed",
        "start_time": datetime | None,
        "end_time": datetime | None,
        "error": str | None,
        "results": dict | None,
    }

    st.session_state.step_status = {
        "classification": {
            "status": "pending" | "running" | "success" | "failed" | "skipped",
            "start_time": datetime | None,
            "end_time": datetime | None,
            "result": dict | None,
            "error": str | None,
            "elapsed_seconds": float | None,
        },
        # ... same structure for extraction, validation, correction
    }

Usage Example:
    >>> import streamlit as st
    >>> from src.streamlit_app import init_session_state
    >>> from src.streamlit_app.screens import show_execution_screen
    >>>
    >>> # Initialize session state (in app.py)
    >>> init_session_state()
    >>>
    >>> # Navigate to execution phase (from settings screen)
    >>> st.session_state.current_phase = "execution"
    >>> st.rerun()
    >>>
    >>> # Execution screen renders with state machine
    >>> show_execution_screen()

Rerun Prevention Strategy:
    Streamlit reruns the entire script on every user interaction. To prevent pipeline
    restart, we use a state machine with session state flags:

    1. idle → running: Set status, trigger rerun
    2. running → completed/failed: Execute pipeline ONCE, update status, trigger rerun
    3. completed/failed: Display results, no pipeline execution

    Key insight: Pipeline execution only happens when status == "running", and status
    is immediately changed to completed/failed after execution, preventing reruns.
"""

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src.pipeline.file_manager import PipelineFileManager
from src.pipeline.orchestrator import (
    ALL_PIPELINE_STEPS,
    STEP_APPRAISAL,
    STEP_CLASSIFICATION,
    STEP_CORRECTION,
    STEP_EXTRACTION,
    STEP_PODCAST_GENERATION,
    STEP_REPORT_GENERATION,
    STEP_VALIDATION,
    STEP_VALIDATION_CORRECTION,
    run_single_step,
)


def init_execution_state():
    """
    Initialize execution state in session state.

    Creates two session state dictionaries:
    1. execution: Overall pipeline status and metadata
    2. step_status: Per-step tracking with status, timing, results, errors

    This function is idempotent - safe to call multiple times. Only initializes
    keys that don't already exist in session state.

    State Initialization:
        execution["status"] = "idle" (ready to start)
        execution[start_time/end_time/error/results] = None

        For each step in [classification, extraction, validation, correction]:
            step_status[step]["status"] = "pending"
            step_status[step][start_time/end_time/result/error/elapsed_seconds] = None

    Example:
        >>> init_execution_state()
        >>> st.session_state.execution["status"]
        'idle'
        >>> st.session_state.step_status["classification"]["status"]
        'pending'

    Note:
        Must be called before accessing execution or step_status in session state.
        Typically called at the start of show_execution_screen().
    """
    # Initialize overall execution state
    if "execution" not in st.session_state:
        st.session_state.execution = {
            "status": "idle",  # idle | running | completed | failed
            "start_time": None,
            "end_time": None,
            "error": None,
            "results": None,
            "current_step_index": 0,  # Index of current step being executed (0-3)
            "auto_redirect_enabled": False,  # Disable auto-redirect after completion
            "redirect_cancelled": False,  # User cancelled auto-redirect
            "redirect_countdown": None,  # Countdown value (30, 29, ..., 0)
        }

    # Initialize per-step tracking
    if "step_status" not in st.session_state:
        st.session_state.step_status = {
            step: {
                "status": "pending",  # pending | running | success | failed | skipped
                "start_time": None,
                "end_time": None,
                "result": None,
                "error": None,
                "elapsed_seconds": None,
                "verbose_data": {},  # Store callback data for verbose logging
            }
            for step in ALL_PIPELINE_STEPS
        }


def reset_execution_state():
    """
    Reset execution state to initial idle state.

    Resets both execution and step_status to their initial values, allowing
    the pipeline to be re-run from scratch. Used for:
    - "Back to Settings" navigation
    - Retry after error
    - Clean state after completion

    Resets:
        - execution status → "idle"
        - all timestamps → None
        - all errors → None
        - all results → None
        - all step statuses → "pending"

    Example:
        >>> # After pipeline completion
        >>> st.session_state.execution["status"]
        'completed'
        >>> reset_execution_state()
        >>> st.session_state.execution["status"]
        'idle'

    Note:
        This does NOT delete files in tmp/ directory. Old pipeline outputs
        remain on disk until manually deleted via Settings screen.
    """
    st.session_state.execution = {
        "status": "idle",
        "start_time": None,
        "end_time": None,
        "error": None,
        "results": None,
        "current_step_index": 0,
        "auto_redirect_enabled": False,
        "redirect_cancelled": False,
        "redirect_countdown": None,
    }

    st.session_state.step_status = {
        step: {
            "status": "pending",
            "start_time": None,
            "end_time": None,
            "result": None,
            "error": None,
            "elapsed_seconds": None,
            "verbose_data": {},
        }
        for step in ALL_PIPELINE_STEPS
    }


def _mark_next_step_running(current_step: str):
    """
    Mark the next step in steps_to_run as 'running' after current step completes.

    This provides proactive UI updates for better UX within Streamlit's constraints.
    When a step completes, the next step is immediately marked as running so that
    on the next UI refresh, users see the correct status.

    Args:
        current_step: Name of the step that just completed/failed

    Example:
        >>> # After classification completes:
        >>> _mark_next_step_running("classification")
        >>> # If extraction is next, it's now marked as "running"
    """
    # Get configured steps from settings
    steps_to_run = st.session_state.settings.get("steps_to_run", [])

    # Find current step index in the configured list
    if current_step not in steps_to_run:
        return  # Current step not in list, nothing to do

    current_index = steps_to_run.index(current_step)

    # Find next step in the configured list
    if current_index + 1 < len(steps_to_run):
        next_step = steps_to_run[current_index + 1]

        # Only mark as running if it's still pending (not already processed)
        if st.session_state.step_status[next_step]["status"] == "pending":
            st.session_state.step_status[next_step]["status"] = "running"
            st.session_state.step_status[next_step]["start_time"] = datetime.now()


def create_progress_callback() -> Callable[[str, str, dict], None]:
    """
    Create progress callback that updates Streamlit session state during pipeline execution.

    Returns a callback function that the orchestrator calls to report pipeline progress.
    The callback updates `st.session_state.step_status` in real-time, allowing the UI
    to reflect current execution state.

    Returns:
        Callback function with signature: callback(step_name, status, data)

    Callback Parameters:
        step_name (str): Step identifier - "classification", "extraction", "validation", "correction"
        status (str): Step status - "starting", "completed", "failed", "skipped"
        data (dict): Status-specific data payload (see below)

    Data Payload by Status:
        starting:
            - pdf_path (str): Path to PDF being processed
            - max_pages (int | None): Page limit configuration
            - schema_name (str, optional): Schema being used (for extraction)

        completed:
            - result (dict): Step result data
            - elapsed_seconds (float): Step execution time
            - file_path (str): Path to saved output file

        failed:
            - error (str): Error message
            - error_type (str): Exception class name
            - elapsed_seconds (float): Time until failure

        skipped:
            - (empty dict or reason for skip)

    Callback Behavior:
        - starting: Sets step status="running", records start_time
        - completed: Sets step status="success", records end_time, elapsed_seconds, result
        - failed: Sets step status="failed", records end_time, error message
        - skipped: Sets step status="skipped"

    Example:
        >>> callback = create_progress_callback()
        >>> # Orchestrator calls:
        >>> callback("classification", "starting", {"pdf_path": "paper.pdf"})
        >>> # ... LLM API call happens ...
        >>> callback("classification", "completed", {
        ...     "result": {"publication_type": "interventional_trial"},
        ...     "elapsed_seconds": 12.4,
        ...     "file_path": "tmp/paper-classification.json"
        ... })

    Note:
        - Thread-safe via Streamlit session state
        - Ignores unknown step names (validation check)
        - Does not raise exceptions (safe for orchestrator)
        - Updates are immediately reflected in UI on next rerun
    """

    def callback(step_name: str, status: str, data: dict) -> None:
        # Validate step_name exists in session state
        if step_name not in st.session_state.step_status:
            return  # Silently ignore unknown steps

        step = st.session_state.step_status[step_name]

        # Store all callback data for verbose logging
        step["verbose_data"][status] = data.copy()

        if status == "starting":
            # Step is beginning execution
            step["status"] = "running"
            step["start_time"] = datetime.now()

        elif status == "completed":
            # Step completed successfully
            step["status"] = "success"
            step["end_time"] = datetime.now()
            step["elapsed_seconds"] = data.get("elapsed_seconds")
            step["result"] = data.get("result")
            # Store file path for potential UI display
            if "file_path" in data:
                step["file_path"] = data["file_path"]

            # Proactively mark next step as running for better UX
            _mark_next_step_running(step_name)

        elif status == "failed":
            # Step failed with error
            step["status"] = "failed"
            step["end_time"] = datetime.now()
            step["elapsed_seconds"] = data.get("elapsed_seconds")
            step["error"] = data.get("error", "Unknown error")

            # Proactively mark next step as running if pipeline continues
            # (Note: orchestrator decides if pipeline continues after failure)
            _mark_next_step_running(step_name)

        elif status == "skipped":
            # Step was skipped (not in steps_to_run or not needed)
            step["status"] = "skipped"
            # No timestamps for skipped steps

    return callback


def _extract_token_usage(result: dict) -> dict | None:
    """
    Extract token usage information from LLM result dictionary.

    Searches for common token usage keys in result dict and returns standardized format.

    Args:
        result: LLM result dictionary that may contain usage/token information

    Returns:
        Dict with standardized keys {input, output, total} or None if not found

    Example:
        >>> result = {"usage": {"input_tokens": 1000, "output_tokens": 250}}
        >>> _extract_token_usage(result)
        {'input': 1000, 'output': 250, 'total': 1250}
    """
    if not result or not isinstance(result, dict):
        return None

    # Try different common key patterns
    usage = result.get("usage") or result.get("token_usage") or result.get("tokens")

    if not usage or not isinstance(usage, dict):
        return None

    # Extract input/output tokens with various key names
    input_tokens = (
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("input")
        or usage.get("prompt")
    )

    output_tokens = (
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("output")
        or usage.get("completion")
    )

    if input_tokens is None and output_tokens is None:
        return None

    # Build standardized dict
    token_info = {}
    if input_tokens is not None:
        token_info["input"] = input_tokens
    if output_tokens is not None:
        token_info["output"] = output_tokens
    if input_tokens is not None and output_tokens is not None:
        token_info["total"] = input_tokens + output_tokens

    return token_info


def _display_verbose_info(step_name: str, verbose_data: dict, result: dict | None):
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
        >>> _display_verbose_info("classification", {...}, {...})
        # Renders verbose details in Streamlit UI
    """
    st.markdown("#### 🔍 Verbose Details")

    # Display starting data
    starting_data = verbose_data.get("starting", {})
    if starting_data:
        st.markdown("**Starting parameters:**")

        if step_name == STEP_CLASSIFICATION:
            if "pdf_path" in starting_data:
                st.write(f"• PDF: `{starting_data['pdf_path']}`")
            if "max_pages" in starting_data:
                max_pages = starting_data["max_pages"] or "All"
                st.write(f"• Max pages: {max_pages}")

        elif step_name == STEP_EXTRACTION:
            if "publication_type" in starting_data:
                st.write(f"• Publication type: `{starting_data['publication_type']}`")

        elif step_name == STEP_CORRECTION:
            if "validation_status" in starting_data:
                st.write(f"• Validation status: {starting_data['validation_status']}")

    # Display token usage if available
    if result:
        token_usage = _extract_token_usage(result)
        if token_usage:
            st.markdown("**Token usage:**")
            if "input" in token_usage:
                st.write(f"• Input tokens: {token_usage['input']:,}")
            if "output" in token_usage:
                st.write(f"• Output tokens: {token_usage['output']:,}")
            if "total" in token_usage:
                st.write(f"• Total tokens: {token_usage['total']:,}")

        # Display cached tokens if available (cost optimization)
        usage = result.get("usage", {})
        cached_tokens = usage.get("cached_tokens")
        if cached_tokens:
            st.markdown("**Cache efficiency:**")
            input_tokens = usage.get("input_tokens", 0)
            if input_tokens > 0:
                cache_hit_pct = (cached_tokens / input_tokens) * 100
                st.write(f"• Cached tokens: {cached_tokens:,} ({cache_hit_pct:.1f}% cache hit)")
            else:
                st.write(f"• Cached tokens: {cached_tokens:,}")

        # Display reasoning tokens if significant
        reasoning_tokens = usage.get("reasoning_tokens")
        if reasoning_tokens:
            st.markdown("**Reasoning tokens:**")
            output_tokens = usage.get("output_tokens", 0)
            if output_tokens > 0:
                reasoning_pct = (reasoning_tokens / output_tokens) * 100
                st.write(f"• Reasoning: {reasoning_tokens:,} ({reasoning_pct:.1f}% of output)")
            else:
                st.write(f"• Reasoning: {reasoning_tokens:,}")

        # Display response metadata
        metadata = result.get("_metadata", {})
        if metadata:
            st.markdown("**Response metadata:**")
            if "model" in metadata:
                st.write(f"• Model: `{metadata['model']}`")
            if "response_id" in metadata:
                st.write(f"• Response ID: `{metadata['response_id']}`")
            if "status" in metadata:
                st.write(f"• Status: {metadata['status']}")
            if "stop_reason" in metadata:
                st.write(f"• Stop reason: {metadata['stop_reason']}")

            # Expandable reasoning summary for GPT-5/o-series
            reasoning = metadata.get("reasoning", {})
            if reasoning and "summary" in reasoning:
                with st.expander("🧠 Reasoning Summary"):
                    st.write(reasoning["summary"])
                    if "effort" in reasoning:
                        st.caption(f"Effort level: {reasoning['effort']}")

    # Display completion data
    completed_data = verbose_data.get("completed", {})
    if completed_data:
        # File path is already shown in main display, but can show size here
        if "file_path" in completed_data:
            file_path = completed_data["file_path"]
            # Could add file size here if we read it from disk
            st.caption(f"💾 Output: `{file_path}`")


# Error handling guidance mapping
ERROR_MESSAGES = {
    "api_key": {
        "title": "API Key Error",
        "message": "Authentication failed. Your API key may be invalid or missing.",
        "actions": [
            "Check your .env file for OPENAI_API_KEY or ANTHROPIC_API_KEY",
            "Verify the key is correct (no extra spaces or quotes)",
            "Ensure the API key has sufficient permissions",
            "Try regenerating the key from your provider's dashboard",
        ],
    },
    "network": {
        "title": "Network Error",
        "message": "Could not connect to the LLM API.",
        "actions": [
            "Check your internet connection",
            "Verify the API endpoint is reachable",
            "Try again in a few moments",
            "Check if your firewall allows API calls",
        ],
    },
    "rate_limit": {
        "title": "Rate Limit Exceeded",
        "message": "You have exceeded the API rate limit.",
        "actions": [
            "Wait a few minutes before trying again",
            "Check your API usage quota on the provider's dashboard",
            "Consider upgrading your API plan",
            "Reduce the number of pages being processed (max_pages setting)",
        ],
    },
    "publication_type": {
        "title": "Unsupported Publication Type",
        "message": "The publication type 'overig' or 'unknown' cannot be processed.",
        "actions": [
            "Only specific publication types are supported (interventional trial, observational study, etc.)",
            "Check if the PDF is a research paper",
            "Verify the classification result in Settings screen",
            "Try a different PDF document",
        ],
    },
    "generic": {
        "title": "Pipeline Error",
        "message": "An unexpected error occurred during pipeline execution.",
        "actions": [
            "Check the technical details below for more information",
            "Review your settings and try again",
            "Ensure your PDF is a valid research paper",
            "Contact support if the issue persists",
        ],
    },
}


def _classify_error_type(error_msg: str, step_name: str) -> str:
    """
    Classify error type based on error message and step name.

    Args:
        error_msg: Error message from exception or callback
        step_name: Step where error occurred ("classification", "extraction", etc.)

    Returns:
        Error type: "api_key", "network", "rate_limit", "publication_type", "generic"

    Example:
        >>> _classify_error_type("401 Unauthorized", "classification")
        'api_key'
        >>> _classify_error_type("Rate limit exceeded", "extraction")
        'rate_limit'
    """
    error_lower = error_msg.lower()

    # Check for API key errors
    if any(
        keyword in error_lower
        for keyword in ["api key", "authentication", "401", "unauthorized", "invalid key"]
    ):
        return "api_key"

    # Check for rate limit errors
    if any(keyword in error_lower for keyword in ["rate limit", "429", "too many requests"]):
        return "rate_limit"

    # Check for network errors
    if any(
        keyword in error_lower
        for keyword in ["timeout", "connection", "network", "unreachable", "dns"]
    ):
        return "network"

    # Check for publication type errors
    if any(
        keyword in error_lower
        for keyword in ["overig", "not supported", "unknown publication", "unsupported type"]
    ):
        return "publication_type"

    # Default to generic error
    return "generic"


def _get_error_guidance(error_type: str, error_msg: str) -> dict:
    """
    Get user-friendly error guidance for a given error type.

    Args:
        error_type: Classified error type
        error_msg: Original error message

    Returns:
        Dict with keys: title, message, actions, technical_details

    Example:
        >>> _get_error_guidance("api_key", "401 Unauthorized")
        {'title': 'API Key Error', 'message': '...', 'actions': [...], ...}
    """
    guidance = ERROR_MESSAGES.get(error_type, ERROR_MESSAGES["generic"]).copy()
    guidance["technical_details"] = error_msg
    return guidance


def _display_error_with_guidance(error_msg: str, step_name: str, step: dict):
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
        >>> _display_error_with_guidance("401 Unauthorized", "classification", {...})
        # Renders error with guidance in Streamlit UI
    """
    # Classify error and get guidance
    error_type = _classify_error_type(error_msg, step_name)
    guidance = _get_error_guidance(error_type, error_msg)

    # Display error title and message
    st.error(f"**{guidance['title']}**")
    st.markdown(guidance["message"])

    # Display action steps
    st.markdown("**💡 Troubleshooting steps:**")
    for i, action in enumerate(guidance["actions"], 1):
        st.markdown(f"{i}. {action}")

    # Expandable technical details
    with st.expander("🔧 Technical Details"):
        st.code(guidance["technical_details"], language="text")

        # Show additional context if available
        if "error_type" in step.get("verbose_data", {}).get("failed", {}):
            error_type_name = step["verbose_data"]["failed"]["error_type"]
            st.caption(f"**Exception type:** `{error_type_name}`")


def _check_validation_warnings(validation_result: dict) -> list[str]:
    """
    Check validation result for non-critical warnings.

    Args:
        validation_result: Validation result dictionary

    Returns:
        List of warning messages (empty if no warnings)

    Example:
        >>> result = {"is_valid": True, "quality_score": 6}
        >>> _check_validation_warnings(result)
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


def _display_classification_result(result: dict):
    """Display classification step result summary."""
    if not result:
        return

    pub_type = result.get("publication_type", "Unknown")
    st.write(f"📚 **Publication Type:** `{pub_type}`")

    # Show DOI if available
    metadata = result.get("metadata", {})
    if isinstance(metadata, dict) and "doi" in metadata:
        doi = metadata["doi"]
        st.write(f"🔗 **DOI:** `{doi}`")


def _display_extraction_result(result: dict):
    """Display extraction step result summary."""
    if not result:
        return

    # Count extracted fields (rough estimate)
    field_count = len(result) if isinstance(result, dict) else 0
    if field_count > 0:
        st.write(f"📊 **Extracted fields:** {field_count}")

    # Show title if available
    if isinstance(result, dict):
        title = result.get("title") or result.get("metadata", {}).get("title")
        if title:
            st.write(f"📄 **Title:** {title[:80]}{'...' if len(title) > 80 else ''}")


def _display_validation_result(result: dict):
    """Display validation step result summary."""
    if not result:
        return

    # Show overall validation status
    is_valid = result.get("is_valid", False)
    status_text = "✅ Valid" if is_valid else "⚠️ Issues found"
    st.write(f"**Validation:** {status_text}")

    # Show error count if available
    errors = result.get("errors", [])
    if errors:
        error_count = len(errors)
        st.write(f"🔍 **Issues:** {error_count} schema validation error(s)")

    # Show quality score if available (from LLM validation)
    quality_score = result.get("quality_score")
    if quality_score is not None:
        st.write(f"⭐ **Quality Score:** {quality_score}/10")

    # Check for non-critical warnings
    warnings = _check_validation_warnings(result)
    if warnings:
        for warning in warnings:
            st.warning(f"⚠️ {warning}")


def _display_correction_result(result: dict):
    """Display correction step result summary."""
    if not result:
        return

    # Check if correction was applied or skipped
    correction_applied = result.get("correction_applied", False)
    if correction_applied:
        st.write("🔧 **Correction:** Applied")

        # Show number of corrections if available
        corrections = result.get("corrections", [])
        if corrections:
            st.write(f"📝 **Changes:** {len(corrections)} corrections made")
    else:
        st.write("✨ **Correction:** Not needed (validation passed)")


def _display_validation_correction_result(result: dict):
    """Display validation & correction iterative loop result summary."""
    if not result:
        return

    final_status = result.get("final_status", "unknown")
    iteration_count = result.get("iteration_count", 0)
    iterations = result.get("iterations", [])

    # Display final status with appropriate icon
    status_messages = {
        "passed": "✅ **Quality thresholds met!**",
        "max_iterations_reached": f"⚠️ **Max iterations reached ({iteration_count})**",
        "early_stopped_degradation": "⚠️ **Early stopping: quality degraded**",
    }

    status_msg = status_messages.get(final_status, f"❌ **Failed:** {final_status}")
    st.write(status_msg)

    # Show iteration count and best iteration
    best_iteration = result.get("best_iteration", 0)
    st.write(f"🔄 **Iterations completed:** {iteration_count}")
    st.write(f"⭐ **Best iteration selected:** {best_iteration}")

    # Display iteration history table
    if iterations:
        st.markdown("#### 📊 Iteration History")

        # Build table data
        table_data = []
        for iter_data in iterations:
            metrics = iter_data.get("metrics", {})
            is_best = iter_data.get("iteration_num") == best_iteration

            table_data.append(
                {
                    "Iteration": iter_data.get("iteration_num", 0),
                    "Completeness": f"{metrics.get('completeness_score', 0):.1%}",
                    "Accuracy": f"{metrics.get('accuracy_score', 0):.1%}",
                    "Schema": f"{metrics.get('schema_compliance_score', 0):.1%}",
                    "Critical": metrics.get("critical_issues", 0),
                    "Overall": f"{metrics.get('overall_quality', 0):.1%}",
                    "Status": "✅ BEST" if is_best else "",
                }
            )

        # Display as DataFrame
        df = pd.DataFrame(table_data)
        st.dataframe(df, width="stretch", hide_index=True)

        trajectory = result.get("improvement_trajectory", [])
        if trajectory:
            st.caption("Quality score trajectory per iteration")
            chart_df = pd.DataFrame(
                {"Quality Score": trajectory}, index=[f"Iter {i}" for i in range(len(trajectory))]
            )
            st.line_chart(chart_df)

    # Show metrics from best iteration
    if iterations and best_iteration < len(iterations):
        best_iter_data = iterations[best_iteration]
        best_metrics = best_iter_data.get("metrics", {})

        st.markdown("#### 📈 Best Iteration Metrics")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            comp = best_metrics.get("completeness_score", 0)
            st.metric("Completeness", f"{comp:.1%}")

        with col2:
            acc = best_metrics.get("accuracy_score", 0)
            st.metric("Accuracy", f"{acc:.1%}")

        with col3:
            schema = best_metrics.get("schema_compliance_score", 0)
            st.metric("Schema", f"{schema:.1%}")

        with col4:
            critical = best_metrics.get("critical_issues", 0)
            st.metric("Critical Issues", critical)


def _display_appraisal_result(result: dict):
    """Display appraisal result summary with RoB, GRADE, and iteration history."""
    if not result:
        return

    best_appraisal = result.get("best_appraisal", {})
    final_status = result.get("final_status", "unknown")
    iteration_count = result.get("iteration_count", 0)
    iterations = result.get("iterations", [])

    # Display final status
    status_messages = {
        "passed": "✅ **Appraisal quality thresholds met!**",
        "max_iterations_reached": f"⚠️ **Max iterations reached ({iteration_count})**",
        "early_stopped_degradation": "⚠️ **Early stopping: quality degraded**",
    }

    status_msg = status_messages.get(final_status, f"❌ **Failed:** {final_status}")
    st.write(status_msg)

    # Show iteration count and best iteration
    best_iteration = result.get("best_iteration", 0)
    st.write(f"🔄 **Iterations completed:** {iteration_count}")
    st.write(f"⭐ **Best iteration selected:** {best_iteration}")

    # Display Risk of Bias Summary
    if "risk_of_bias" in best_appraisal:
        st.markdown("#### 🎯 Risk of Bias Assessment")

        rob = best_appraisal["risk_of_bias"]
        tool_info = best_appraisal.get("tool", {})
        tool_name = tool_info.get("name", "Unknown")
        tool_variant = tool_info.get("variant", "")

        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("Tool", tool_name)
        with col2:
            if tool_variant:
                st.metric("Variant", tool_variant)

        # Overall judgement
        overall = rob.get("overall", "—")
        st.write(f"**Overall Risk of Bias:** {overall}")

        # Domain assessments
        domains = rob.get("domains", [])
        if domains:
            st.markdown(f"**Domains Assessed:** {len(domains)}")

            # Show first few domains
            for domain in domains[:5]:
                domain_name = domain.get("domain", "Unknown")
                judgement = domain.get("judgement", "—")
                st.write(f"  • {domain_name}: {judgement}")

            if len(domains) > 5:
                st.caption(f"_...and {len(domains) - 5} more domains (view full JSON for details)_")

    # Display GRADE Certainty
    grade_outcomes = best_appraisal.get("grade_per_outcome", [])
    if grade_outcomes:
        st.markdown("#### 📊 GRADE Certainty of Evidence")
        st.write(f"**Outcomes Rated:** {len(grade_outcomes)}")

        # Show first few outcomes
        for grade in grade_outcomes[:3]:
            outcome_id = grade.get("outcome_id", "Unknown")
            certainty = grade.get("certainty", "—")
            downgrades = grade.get("downgrades", {})

            # Build list of non-zero downgrades with their levels
            downgrade_items = []
            if downgrades:
                downgrade_labels = {
                    "risk_of_bias": "RoB",
                    "inconsistency": "Incons",
                    "indirectness": "Indir",
                    "imprecision": "Imprec",
                    "publication_bias": "PubBias",
                }
                for key, label in downgrade_labels.items():
                    level = downgrades.get(key)
                    if level and level > 0:
                        downgrade_items.append(f"{label}(-{level})")

            downgrade_summary = ", ".join(downgrade_items) if downgrade_items else "None"
            st.write(f"  • {outcome_id}: **{certainty}** (downgrades: {downgrade_summary})")

        if len(grade_outcomes) > 3:
            st.caption(f"_...and {len(grade_outcomes) - 3} more outcomes_")

    # Display Applicability
    applicability = best_appraisal.get("applicability", {})
    if applicability:
        st.markdown("#### 🌍 Applicability")
        population_match = applicability.get("population_match", {}).get("rating", "—")
        st.write(f"**Population Match:** {population_match}")

    # Display iteration history table
    if iterations:
        st.markdown("#### 📊 Iteration History")

        # Build table data
        table_data = []
        for iter_data in iterations:
            metrics = iter_data.get("metrics", {})
            is_best = iter_data.get("iteration_num") == best_iteration

            table_data.append(
                {
                    "Iteration": iter_data.get("iteration_num", 0),
                    "Logical": f"{metrics.get('logical_consistency_score', 0):.1%}",
                    "Complete": f"{metrics.get('completeness_score', 0):.1%}",
                    "Evidence": f"{metrics.get('evidence_support_score', 0):.1%}",
                    "Schema": f"{metrics.get('schema_compliance_score', 0):.1%}",
                    "Critical": metrics.get("critical_issues", 0),
                    "Quality": f"{metrics.get('quality_score', 0):.1%}",
                    "Status": "✅ BEST" if is_best else "",
                }
            )

        # Display as DataFrame
        df = pd.DataFrame(table_data)
        st.dataframe(df, width="stretch", hide_index=True)

    # Show metrics from best iteration
    if iterations and best_iteration < len(iterations):
        best_iter_data = iterations[best_iteration]
        best_metrics = best_iter_data.get("metrics", {})

        st.markdown("#### 📈 Best Iteration Metrics")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            logical = best_metrics.get("logical_consistency_score", 0)
            st.metric("Logical", f"{logical:.1%}")

        with col2:
            comp = best_metrics.get("completeness_score", 0)
            st.metric("Complete", f"{comp:.1%}")

        with col3:
            evidence = best_metrics.get("evidence_support_score", 0)
            st.metric("Evidence", f"{evidence:.1%}")

        with col4:
            schema = best_metrics.get("schema_compliance_score", 0)
            st.metric("Schema", f"{schema:.1%}")

    # Bottom line for podcast
    bottom_line = best_appraisal.get("bottom_line", {})
    if bottom_line:
        st.markdown("#### 🎙️ Bottom Line (for Podcast)")
        for_podcast = bottom_line.get("for_podcast", "—")
        st.info(for_podcast)

    execution_status = st.session_state.execution.get("status", "idle")
    if execution_status in {"completed", "failed"}:
        if st.button("🔁 Re-run appraisal", key="rerun_appraisal"):
            _trigger_appraisal_rerun()


def _trigger_appraisal_rerun():
    """Reset state so appraisal step reruns from the execution screen."""
    exec_state = st.session_state.execution
    exec_state["status"] = "running"
    exec_state["error"] = None
    exec_state["redirect_countdown"] = None
    exec_state["redirect_cancelled"] = False
    exec_state["end_time"] = None
    exec_state["results"].pop(STEP_APPRAISAL, None)

    # Reset appraisal step status
    st.session_state.step_status[STEP_APPRAISAL] = {
        "status": "pending",
        "start_time": None,
        "end_time": None,
        "result": None,
        "error": None,
        "elapsed_seconds": None,
        "verbose_data": {},
        "file_path": None,
    }

    exec_state["current_step_index"] = ALL_PIPELINE_STEPS.index(STEP_APPRAISAL)
    st.rerun()


def _trigger_report_rerun():
    """Reset state so report generation step reruns from the execution screen."""
    exec_state = st.session_state.execution
    exec_state["status"] = "running"
    exec_state["error"] = None
    exec_state["redirect_countdown"] = None
    exec_state["redirect_cancelled"] = False
    exec_state["end_time"] = None
    exec_state["results"].pop(STEP_REPORT_GENERATION, None)

    # Reset report generation step status
    st.session_state.step_status[STEP_REPORT_GENERATION] = {
        "status": "pending",
        "start_time": None,
        "end_time": None,
        "result": None,
        "error": None,
        "elapsed_seconds": None,
        "verbose_data": {},
        "file_path": None,
    }

    exec_state["current_step_index"] = ALL_PIPELINE_STEPS.index(STEP_REPORT_GENERATION)
    st.rerun()


def display_step_status(step_name: str, step_label: str, step_number: int):
    """
    Display status UI for a single pipeline step.

    Renders a Streamlit status container with:
    - Status icon (⏳ Pending / 🔄 Running / ✅ Success / ❌ Failed / ⏭️ Skipped)
    - Elapsed time (for running/completed steps)
    - Error message (for failed steps)
    - Result summary (for successful steps)
    - Expandable details section (collapsed by default for success)

    Args:
        step_name: Step identifier ("classification", "extraction", "validation", "correction")
        step_label: Human-readable label ("Classification", "Extraction", etc.)
        step_number: Step number (1-4) for display

    Status Icons:
        - pending: ⏳ (not yet started)
        - running: 🔄 (currently executing)
        - success: ✅ (completed successfully)
        - failed: ❌ (critical error, pipeline stopped)
        - skipped: ⏭️ (step not selected or not needed)

    Container Expansion:
        - pending/skipped: Not expandable
        - running/failed: Auto-expanded to show progress/error
        - success: Collapsed by default, user can expand for details

    Result Summaries by Step:
        - classification: Publication type, DOI
        - extraction: Field count, title excerpt
        - validation: Valid/invalid status, error count, quality score
        - correction: Applied/skipped status, number of changes

    Example:
        >>> display_step_status("classification", "Classification", 1)
        # Renders: "Step 1: Classification  ✅ Completed in 8.3s"
        # Expandable content shows: Publication Type, DOI

    Note:
        Reads step status from st.session_state.step_status[step_name].
        Must call init_execution_state() before using this function.
    """
    step = st.session_state.step_status[step_name]
    status = step["status"]

    # Status icon mapping
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
        elapsed_text = f" • {elapsed:.1f}s"

    # Status container configuration
    if status == "pending":
        # Not expandable for pending
        st.markdown(f"{icon} **{label}** - Not yet started")

    elif status == "running":
        # Auto-expanded for running (no elapsed time - it's static during execution)
        with st.status(f"{icon} {label} - Running", expanded=True):
            st.write(f"⏰ **Started:** {step['start_time'].strftime('%H:%M:%S')}")
            st.write("⚙️ Executing pipeline step...")

    elif status == "success":
        # Collapsed by default for success, with result summary
        with st.status(f"{icon} {label} - Completed{elapsed_text}", expanded=False):
            # Show timing
            st.write(f"⏰ **Completed:** {step['end_time'].strftime('%H:%M:%S')}")

            # Show step-specific result summary
            result = step.get("result")
            if result:
                st.markdown("---")
                if step_name == STEP_CLASSIFICATION:
                    _display_classification_result(result)
                elif step_name == STEP_EXTRACTION:
                    _display_extraction_result(result)
                elif step_name == STEP_VALIDATION:
                    _display_validation_result(result)
                elif step_name == STEP_CORRECTION:
                    _display_correction_result(result)
                elif step_name == STEP_VALIDATION_CORRECTION:
                    _display_validation_correction_result(result)
                elif step_name == STEP_APPRAISAL:
                    _display_appraisal_result(result)
                elif step_name == STEP_REPORT_GENERATION:
                    _display_report_result(result)

            # Show file path if available (non-verbose always shows this)
            file_path = step.get("file_path")
            if file_path:
                st.caption(f"💾 **Saved:** `{file_path}`")

            # Show verbose logging details if enabled
            verbose_enabled = st.session_state.settings.get("verbose_logging", False)
            if verbose_enabled:
                verbose_data = step.get("verbose_data", {})
                if verbose_data or result:
                    st.markdown("---")
                    _display_verbose_info(step_name, verbose_data, result)

    elif status == "failed":
        # Auto-expanded for errors with actionable guidance
        with st.status(f"{icon} {label} - Failed{elapsed_text}", expanded=True, state="error"):
            # Display error with guidance and troubleshooting steps
            _display_error_with_guidance(step["error"], step_name, step)

            # Show timing
            st.markdown("---")
            if step["start_time"]:
                st.write(f"⏰ **Started:** {step['start_time'].strftime('%H:%M:%S')}")
            if step["end_time"]:
                st.write(f"⏰ **Failed:** {step['end_time'].strftime('%H:%M:%S')}")

    elif status == "skipped":
        # Simple text for skipped
        st.markdown(f"{icon} **{label}** - Skipped")


def show_execution_screen():
    """
    Display pipeline execution screen with real-time progress tracking.

    Main execution screen implementing a state machine for rerun prevention:
    - idle: Initial state, auto-starts pipeline
    - running: Executes pipeline exactly once
    - completed: Shows success UI with results summary
    - failed: Shows error UI with actionable messages

    UI Layout:
        1. Header: Title + PDF filename + Settings summary
        2. Progress: 4 step status indicators (classification → correction)
        3. Navigation: "Back to Settings" button (always available)
        4. Completion: Success message or error display

    State Machine (Rerun Prevention):
        The key insight is that Streamlit reruns the entire script on every user
        interaction. To prevent pipeline restart, we use session state flags:

        if status == "idle":
            status = "running"  # Transition
            st.rerun()          # Rerun to execute

        elif status == "running":
            run_four_step_pipeline()  # Execute ONCE
            status = "completed"       # Prevent re-execution
            st.rerun()                 # Rerun to show results

        elif status == "completed":
            display_results()  # No pipeline execution

        elif status == "failed":
            display_error()    # No pipeline execution

    Session State:
        Reads:
        - st.session_state.pdf_path: PDF file to process
        - st.session_state.settings: Pipeline configuration dict
        - st.session_state.execution: Overall execution status
        - st.session_state.step_status: Per-step tracking

        Writes:
        - st.session_state.execution["status"]: State transitions
        - st.session_state.execution["results"]: Pipeline output
        - st.session_state.step_status[step]: Per-step updates (via callback in Fase 4)

    Navigation:
        - "Back to Settings": Resets state, returns to settings phase
        - Auto-redirect (Fase 8): Automatic return to settings after completion

    Example Workflow:
        1. User clicks "Start Pipeline" in Settings screen
        2. Settings screen sets current_phase = "execution" → st.rerun()
        3. Execution screen loads, status = "idle"
        4. State machine transitions: idle → running → completed
        5. User sees progress updates via step_status
        6. On completion: Shows summary, enables "Back to Settings"

    Note:
        - Pipeline integration via callbacks (Fase 4 - IMPLEMENTED)
        - Verbose logging placeholders (Fase 6 - FUTURE: deferred enhancement, not required for MVP)
        - Advanced error handling (Fase 7 - FUTURE: deferred enhancement, not required for MVP)
        - Auto-redirect (Fase 8 - FUTURE: deferred enhancement, not required for MVP)
    """
    # Initialize state
    init_execution_state()

    # Header with top navigation
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown("## 🚀 Pipeline Execution")
    with col2:
        # Top navigation button (always visible)
        status = st.session_state.execution["status"]
        if status == "running":
            # Show confirmation for navigation during execution
            if st.button("⬅️ Back", key="back_top", width="stretch", type="secondary"):
                # Add confirmation state
                if "confirm_navigation" not in st.session_state:
                    st.session_state.confirm_navigation = False

                if not st.session_state.confirm_navigation:
                    st.session_state.confirm_navigation = True
                    st.rerun()
        else:
            # Direct back for non-running states
            if st.button("⬅️ Back", key="back_top", width="stretch", type="secondary"):
                reset_execution_state()
                st.session_state.current_phase = "settings"
                st.rerun()

    # Show confirmation warning if navigation requested during running
    if status == "running" and st.session_state.get("confirm_navigation", False):
        st.warning(
            "⚠️ **Pipeline is running!** Navigating away will not stop the execution. "
            "Are you sure you want to go back to Settings?"
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes, go back", width="stretch"):
                st.session_state.confirm_navigation = False
                reset_execution_state()
                st.session_state.current_phase = "settings"
                st.rerun()
        with col2:
            if st.button("❌ Cancel", width="stretch"):
                st.session_state.confirm_navigation = False
                st.rerun()
        st.markdown("---")

    # Show PDF and settings info
    if st.session_state.pdf_path:
        file_info = st.session_state.uploaded_file_info
        filename = (
            file_info.get("original_name")
            or file_info.get("filename")
            or Path(st.session_state.pdf_path).name
        )
        st.info(f"📄 **Processing:** {filename}")

        # Settings summary
        settings = st.session_state.settings
        provider = settings["llm_provider"].upper()
        max_pages = settings["max_pages"] or "All"
        report_lang = settings.get("report_language", "en").upper()
        steps = settings["steps_to_run"]
        steps_text = ", ".join([s.title() for s in steps])

        st.caption(
            f"**Settings:** {provider} • Max pages: {max_pages} • Report lang: {report_lang} • Steps: {steps_text}"
        )
    else:
        st.error("⚠️ No PDF selected. Please go back to upload screen.")
        if st.button("⬅️ Back to Upload"):
            st.session_state.current_phase = "upload"
            st.rerun()
        return

    st.markdown("---")

    # State machine for rerun prevention
    status = st.session_state.execution["status"]

    if status == "idle":
        # Transition to running state
        st.info("🔄 Starting pipeline execution...")
        st.session_state.execution["status"] = "running"
        st.session_state.execution["start_time"] = datetime.now()
        st.rerun()

    elif status == "running":
        # STEP-BY-STEP EXECUTION WITH UI UPDATES BETWEEN STEPS
        st.info("⏳ Pipeline is executing... Please wait.")

        # Extract settings
        settings = st.session_state.settings
        steps_to_run = settings["steps_to_run"]
        all_steps = ALL_PIPELINE_STEPS
        current_step_index = st.session_state.execution["current_step_index"]

        # Initialize results dict if needed
        if st.session_state.execution["results"] is None:
            st.session_state.execution["results"] = {}

        # One-time setup: mark non-selected steps as skipped
        if current_step_index == 0:
            for step in all_steps:
                if step not in steps_to_run:
                    st.session_state.step_status[step]["status"] = "skipped"

        # Display step status containers - shows current progress
        st.markdown("---")
        st.markdown("### Pipeline Steps")
        display_step_status(STEP_CLASSIFICATION, "Classification", 1)
        display_step_status(STEP_EXTRACTION, "Extraction", 2)
        display_step_status(STEP_VALIDATION_CORRECTION, "Validation & Correction", 3)
        display_step_status(STEP_APPRAISAL, "Appraisal", 4)
        display_step_status(STEP_REPORT_GENERATION, "Report Generation", 5)
        display_step_status(STEP_PODCAST_GENERATION, "Podcast Generation", 6)

        # Check if all steps completed
        if current_step_index >= len(steps_to_run):
            # All steps completed successfully
            st.session_state.execution["status"] = "completed"
            st.session_state.execution["end_time"] = datetime.now()
            st.rerun()
            return

        # Get current step to execute
        current_step_name = steps_to_run[current_step_index]

        # Mark current step as running (if not already) and refresh UI
        if st.session_state.step_status[current_step_name]["status"] == "pending":
            st.session_state.step_status[current_step_name]["status"] = "running"
            st.session_state.step_status[current_step_name]["start_time"] = datetime.now()
            st.rerun()  # Refresh UI to show "running" status before executing
            return

        try:
            # Create progress callback for real-time updates
            callback = create_progress_callback()

            pdf_path = Path(st.session_state.pdf_path)
            file_manager = PipelineFileManager(pdf_path)

            # Step-specific iteration/threshold settings
            max_iter_setting = None
            quality_thresholds = None
            enable_iterative = True
            if current_step_name == STEP_VALIDATION_CORRECTION:
                max_iter_setting = settings.get("max_correction_iterations", 3)
                quality_thresholds = settings.get("quality_thresholds")
            elif current_step_name == STEP_APPRAISAL:
                max_iter_setting = settings.get("max_appraisal_iterations", 3)
                quality_thresholds = settings.get("appraisal_quality_thresholds")
                enable_iterative = settings.get("appraisal_enable_iterative_correction", True)
            elif current_step_name == STEP_REPORT_GENERATION:
                enable_iterative = True  # always use iterative report loop

            # Execute current step with previous results
            step_result = run_single_step(
                step_name=current_step_name,
                pdf_path=pdf_path,
                max_pages=settings["max_pages"],
                llm_provider=settings["llm_provider"],
                file_manager=file_manager,
                progress_callback=callback,
                previous_results=st.session_state.execution["results"],
                max_correction_iterations=max_iter_setting,
                quality_thresholds=quality_thresholds,
                enable_iterative_correction=enable_iterative,
                report_language=settings.get("report_language", "en"),
                report_compile_pdf=settings.get("report_compile_pdf", True),
                report_enable_figures=settings.get("report_enable_figures", True),
                report_renderer=settings.get("report_renderer", "latex"),
            )

            # Store step result
            if current_step_name == STEP_CORRECTION:
                # Correction returns dict with both corrected_extraction and final_validation
                st.session_state.execution["results"].update(step_result)
            else:
                st.session_state.execution["results"][current_step_name] = step_result

            # Mark step as success
            st.session_state.step_status[current_step_name]["status"] = "success"
            st.session_state.step_status[current_step_name]["end_time"] = datetime.now()
            elapsed = (
                st.session_state.step_status[current_step_name]["end_time"]
                - st.session_state.step_status[current_step_name]["start_time"]
            ).total_seconds()
            st.session_state.step_status[current_step_name]["elapsed_seconds"] = elapsed
            st.session_state.step_status[current_step_name]["result"] = step_result

            # Move to next step
            st.session_state.execution["current_step_index"] += 1

            # Rerun to execute next step (or show completion)
            st.rerun()

        except Exception as e:
            # Mark current step as failed
            st.session_state.step_status[current_step_name]["status"] = "failed"
            st.session_state.step_status[current_step_name]["end_time"] = datetime.now()
            st.session_state.step_status[current_step_name]["error"] = str(e)

            if st.session_state.step_status[current_step_name]["start_time"]:
                elapsed = (
                    st.session_state.step_status[current_step_name]["end_time"]
                    - st.session_state.step_status[current_step_name]["start_time"]
                ).total_seconds()
                st.session_state.step_status[current_step_name]["elapsed_seconds"] = elapsed

            # Mark pipeline as failed
            st.session_state.execution["error"] = str(e)
            st.session_state.execution["status"] = "failed"
            st.session_state.execution["end_time"] = datetime.now()

            st.rerun()

    elif status == "completed":
        # Display completion UI
        st.success("✅ Pipeline completed successfully!")

        # Show execution time
        start = st.session_state.execution["start_time"]
        end = st.session_state.execution["end_time"]
        if start and end:
            duration = (end - start).total_seconds()
            st.caption(f"**Total execution time:** {duration:.1f}s")

        st.markdown("---")

        # Display step statuses
        st.markdown("### Pipeline Steps")
        display_step_status(STEP_CLASSIFICATION, "Classification", 1)
        display_step_status(STEP_EXTRACTION, "Extraction", 2)
        display_step_status(STEP_VALIDATION_CORRECTION, "Validation & Correction", 3)
        display_step_status(STEP_APPRAISAL, "Appraisal", 4)
        display_step_status(STEP_REPORT_GENERATION, "Report Generation", 5)
        display_step_status(STEP_PODCAST_GENERATION, "Podcast Generation", 6)

        st.markdown("---")

        # Report artifacts
        display_report_artifacts()

        # Podcast artifacts
        display_podcast_artifacts()

        st.markdown("---")

        # Auto-redirect logic with countdown
        execution = st.session_state.execution
        if execution["auto_redirect_enabled"] and not execution["redirect_cancelled"]:
            # Initialize countdown if not started
            if execution["redirect_countdown"] is None:
                execution["redirect_countdown"] = 30
                st.rerun()

            countdown = execution["redirect_countdown"]

            if countdown > 0:
                # Show countdown with cancel option
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.info(
                        f"🔄 Redirecting to Settings screen in {countdown} second{'s' if countdown > 1 else ''}..."
                    )
                with col2:
                    if st.button("Cancel", key="cancel_redirect", width="stretch"):
                        execution["redirect_cancelled"] = True
                        st.rerun()

                # Decrement countdown
                time.sleep(1)
                execution["redirect_countdown"] -= 1
                st.rerun()

            else:
                # Countdown finished, redirect
                reset_execution_state()
                st.session_state.current_phase = "settings"
                st.rerun()
        else:
            # Auto-redirect disabled or cancelled
            st.info(
                "💡 Pipeline execution completed. View results in Settings screen or run again."
            )

    elif status == "failed":
        # Display error UI with step-level detection
        st.error("❌ Pipeline execution failed")

        # Determine which step failed and show guidance at pipeline level
        failed_step = None
        failed_step_name = None
        for step_name, step_data in st.session_state.step_status.items():
            if step_data["status"] == "failed":
                failed_step = step_data
                failed_step_name = step_name
                break

        if failed_step and failed_step_name:
            # Display error with guidance for the failed step
            st.markdown(f"**Failed at step:** {failed_step_name.title()}")
            st.markdown("---")
            _display_error_with_guidance(failed_step["error"], failed_step_name, failed_step)
        else:
            # Generic error (pipeline-level failure)
            error_msg = st.session_state.execution.get("error", "Unknown error")
            st.markdown(f"**Error:** {error_msg}")

        # Show execution time if available
        st.markdown("---")
        start = st.session_state.execution["start_time"]
        end = st.session_state.execution["end_time"]
        if start and end:
            duration = (end - start).total_seconds()
            st.caption(f"**Failed after:** {duration:.1f}s")

        st.markdown("---")

        # Display step statuses to show where it failed
        st.markdown("### Pipeline Steps")
        display_step_status(STEP_CLASSIFICATION, "Classification", 1)
        display_step_status(STEP_EXTRACTION, "Extraction", 2)
        display_step_status(STEP_VALIDATION_CORRECTION, "Validation & Correction", 3)
        display_step_status(STEP_APPRAISAL, "Appraisal", 4)
        display_step_status(STEP_REPORT_GENERATION, "Report Generation", 5)
        display_step_status(STEP_PODCAST_GENERATION, "Podcast Generation", 6)

        st.markdown("---")

        # If report artifacts exist, still offer downloads
        display_report_artifacts()

        # Podcast artifacts
        display_podcast_artifacts()


def display_report_artifacts():
    """
    Show download buttons for report artifacts (.tex/.pdf) if available.
    """
    if not st.session_state.pdf_path:
        return
    fm = PipelineFileManager(Path(st.session_state.pdf_path))
    render_dir = fm.tmp_dir / "render"
    tex_file = render_dir / "report.tex"
    pdf_file = render_dir / "report.pdf"
    md_file = render_dir / "report.md"
    root_md = fm.tmp_dir / f"{fm.identifier}-report.md"

    st.markdown("### Report Artifacts")
    has_any = False
    if tex_file.exists():
        has_any = True
        with open(tex_file, "rb") as f:
            st.download_button("⬇️ Download LaTeX (.tex)", f, file_name=tex_file.name)
    if pdf_file.exists():
        has_any = True
        with open(pdf_file, "rb") as f:
            st.download_button("⬇️ Download PDF", f, file_name=pdf_file.name)
    if root_md.exists():
        has_any = True
        with open(root_md, "rb") as f:
            st.download_button("⬇️ Download Markdown (.md)", f, file_name=root_md.name)
    elif md_file.exists():
        has_any = True
        with open(md_file, "rb") as f:
            st.download_button("⬇️ Download Markdown (.md)", f, file_name=md_file.name)
    if not has_any:
        st.info("No report artifacts available yet. Run report generation to produce .tex/.pdf.")


def display_podcast_artifacts():
    """
    Show download buttons for podcast artifacts (.json/.md) if available.
    """
    if not st.session_state.pdf_path:
        return
    fm = PipelineFileManager(Path(st.session_state.pdf_path))
    podcast_json = fm.tmp_dir / f"{fm.identifier}-podcast.json"
    podcast_md = fm.tmp_dir / f"{fm.identifier}-podcast.md"

    st.markdown("### Podcast Artifacts")
    has_any = False

    if podcast_json.exists():
        has_any = True
        with open(podcast_json, "rb") as f:
            st.download_button("⬇️ Download Podcast JSON", f, file_name=podcast_json.name)

    if podcast_md.exists():
        has_any = True
        with open(podcast_md, "rb") as f:
            st.download_button("⬇️ Download Podcast Script (.md)", f, file_name=podcast_md.name)

        # Also show transcript preview
        with open(podcast_md) as f:
            content = f.read()
        with st.expander("📄 Preview Transcript"):
            st.markdown(content)

    # Copy transcript button (load from JSON for clean transcript only)
    if podcast_json.exists():
        import json

        with open(podcast_json) as f:
            podcast_data = json.load(f)
        transcript = podcast_data.get("transcript", "")
        if transcript:
            st.text_area(
                "📋 Copy Transcript (for TTS)",
                transcript,
                height=150,
                key="podcast_transcript_copy",
            )

    if not has_any:
        st.info("No podcast artifacts available yet. Run podcast generation to produce script.")


def _display_report_result(result: dict):
    """
    Render a brief summary for the report step (best iteration, quality, outputs).
    """
    if not result:
        st.write("Report generation completed.")
        return

    final_status = result.get("final_status", result.get("_pipeline_metadata", {}).get("status"))
    best_iter = result.get("best_iteration")
    quality = result.get("best_validation", {}).get("validation_summary", {}).get("quality_score")
    warnings = result.get("_pipeline_metadata", {}).get("warnings")

    if best_iter is not None:
        st.write(f"🏆 **Best iteration:** {best_iter}")
    if quality is not None:
        st.write(f"📊 **Quality score:** {quality:.2f}")
    if final_status:
        st.write(f"✅ **Final status:** {final_status}")
    if warnings:
        st.warning(f"⚠️ {warnings}")

    # Show validation status if available
    best_val_status = (
        result.get("best_validation", {}).get("validation_summary", {}).get("overall_status")
    )
    if best_val_status:
        st.write(f"🧪 **Validation:** {best_val_status}")

    # Get iterations for history table
    iterations = result.get("iterations", [])
    best_iteration = result.get("best_iteration", 0)

    # Display iteration history table
    if iterations:
        st.markdown("#### 📊 Iteration History")

        # Build table data
        table_data = []
        for iter_data in iterations:
            metrics = iter_data.get("metrics", {})
            is_best = iter_data.get("iteration_num") == best_iteration

            table_data.append(
                {
                    "Iteration": iter_data.get("iteration_num", 0),
                    "Complete": f"{metrics.get('completeness_score', 0):.1%}",
                    "Accuracy": f"{metrics.get('accuracy_score', 0):.1%}",
                    "XRef": f"{metrics.get('cross_reference_consistency_score', 0):.1%}",
                    "Data": f"{metrics.get('data_consistency_score', 0):.1%}",
                    "Schema": f"{metrics.get('schema_compliance_score', 0):.1%}",
                    "Critical": metrics.get("critical_issues", 0),
                    "Quality": f"{metrics.get('quality_score', 0):.1%}",
                    "Status": "✅ BEST" if is_best else "",
                }
            )

        # Display as DataFrame
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Show metrics from best iteration
    if iterations and best_iteration < len(iterations):
        best_iter_data = iterations[best_iteration]
        best_metrics = best_iter_data.get("metrics", {})

        st.markdown("#### 📈 Best Iteration Metrics")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            completeness = best_metrics.get("completeness_score", 0)
            st.metric("Completeness", f"{completeness:.1%}")

        with col2:
            accuracy = best_metrics.get("accuracy_score", 0)
            st.metric("Accuracy", f"{accuracy:.1%}")

        with col3:
            xref = best_metrics.get("cross_reference_consistency_score", 0)
            st.metric("XRef Consistency", f"{xref:.1%}")

        with col4:
            data_cons = best_metrics.get("data_consistency_score", 0)
            st.metric("Data Consistency", f"{data_cons:.1%}")

    # Re-run button
    execution_status = st.session_state.execution.get("status", "idle")
    if execution_status in {"completed", "failed"}:
        if st.button("🔁 Re-run report generation", key="rerun_report"):
            _trigger_report_rerun()
