# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Progress callbacks and error handling for pipeline execution.

This module provides progress tracking callbacks and error classification/guidance
for the Streamlit pipeline interface, extracted from execution.py for modularity.

Public API:
    - create_progress_callback(): Factory for pipeline progress callbacks
    - ERROR_MESSAGES: Error guidance dictionary
    - classify_error_type(): Classify errors into categories
    - get_error_guidance(): Get user-friendly error guidance
    - extract_token_usage(): Extract token usage from LLM results
"""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

import streamlit as st


# Type definition for progress callback
class ProgressCallback(Protocol):
    """Protocol for pipeline progress callbacks."""

    def __call__(self, step: str, status: str, data: dict) -> None:
        """
        Report pipeline progress.

        Args:
            step: Step identifier (classification, extraction, etc.)
            status: Status string (starting, completed, failed, skipped)
            data: Status-specific data payload
        """
        ...


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


def classify_error_type(error_msg: str, step_name: str) -> str:
    """
    Classify error type based on error message and step name.

    Args:
        error_msg: Error message from exception or callback
        step_name: Step where error occurred ("classification", "extraction", etc.)

    Returns:
        Error type: "api_key", "network", "rate_limit", "publication_type", "generic"

    Example:
        >>> classify_error_type("401 Unauthorized", "classification")
        'api_key'
        >>> classify_error_type("Rate limit exceeded", "extraction")
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


def get_error_guidance(error_type: str, error_msg: str) -> dict:
    """
    Get user-friendly error guidance for a given error type.

    Args:
        error_type: Classified error type
        error_msg: Original error message

    Returns:
        Dict with keys: title, message, actions, technical_details

    Example:
        >>> get_error_guidance("api_key", "401 Unauthorized")
        {'title': 'API Key Error', 'message': '...', 'actions': [...], ...}
    """
    guidance = ERROR_MESSAGES.get(error_type, ERROR_MESSAGES["generic"]).copy()
    guidance["technical_details"] = error_msg
    return guidance


def extract_token_usage(result: dict) -> dict | None:
    """
    Extract token usage information from LLM result dictionary.

    Searches for common token usage keys in result dict and returns standardized format.

    Args:
        result: LLM result dictionary that may contain usage/token information

    Returns:
        Dict with standardized keys {input, output, total} or None if not found

    Example:
        >>> result = {"usage": {"input_tokens": 1000, "output_tokens": 250}}
        >>> extract_token_usage(result)
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
