# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Execution state management for Streamlit pipeline interface.

This module handles session state initialization and reset for the pipeline
execution screen, extracted from execution.py for better modularity.

Public API:
    - init_execution_state(): Initialize execution and step_status session state
    - reset_execution_state(): Reset state for retry/navigation
"""

import streamlit as st

from src.pipeline.orchestrator import ALL_PIPELINE_STEPS


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

        For each step in ALL_PIPELINE_STEPS:
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

    # Clear execution lock to allow new runs
    st.session_state["_execution_in_progress"] = False

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
