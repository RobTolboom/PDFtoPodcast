# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Pipeline execution screen for Streamlit interface.

Provides real-time pipeline execution UI with progress tracking, intelligent error
handling, and session state management. Implements rerun prevention to avoid pipeline
restart on UI interactions.

Components:
    - show_execution_screen(): Main screen function with state machine logic

State management, callbacks, and display functions are delegated to:
    - execution_state: State initialization and reset
    - execution_callbacks: Progress callbacks and error handling
    - execution_display: UI rendering and result display

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
        # ... same structure for other steps
    }

Rerun Prevention Strategy:
    Streamlit reruns the entire script on every user interaction. To prevent pipeline
    restart, we use a state machine with session state flags:

    1. idle → running: Set status, trigger rerun
    2. running → completed/failed: Execute pipeline ONCE, update status, trigger rerun
    3. completed/failed: Display results, no pipeline execution
"""

import time
from datetime import datetime
from pathlib import Path

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
    STEP_VALIDATION_CORRECTION,
    run_single_step,
)

# Import from modular components
from .execution_callbacks import create_progress_callback
from .execution_display import (
    display_error_with_guidance,
    display_podcast_artifacts,
    display_report_artifacts,
    display_step_status,
)
from .execution_state import init_execution_state, reset_execution_state


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
        2. Progress: 6 step status indicators
        3. Navigation: "Back to Settings" button (always available)
        4. Completion: Success message or error display

    State Machine (Rerun Prevention):
        The key insight is that Streamlit reruns the entire script on every user
        interaction. To prevent pipeline restart, we use session state flags:

        if status == "idle":
            status = "running"  # Transition
            st.rerun()          # Rerun to execute

        elif status == "running":
            run_pipeline_step()       # Execute ONCE
            status = "completed"      # Prevent re-execution
            st.rerun()                # Rerun to show results

        elif status == "completed":
            display_results()  # No pipeline execution

        elif status == "failed":
            display_error()    # No pipeline execution
    """
    # Initialize state
    init_execution_state()

    # Header with top navigation
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown("## Pipeline Execution")
    with col2:
        # Top navigation button (always visible)
        status = st.session_state.execution["status"]
        if status == "running":
            # Show confirmation for navigation during execution
            if st.button("Back", key="back_top", use_container_width=True, type="secondary"):
                # Add confirmation state
                if "confirm_navigation" not in st.session_state:
                    st.session_state.confirm_navigation = False

                if not st.session_state.confirm_navigation:
                    st.session_state.confirm_navigation = True
                    st.rerun()
        else:
            # Direct back for non-running states
            if st.button("Back", key="back_top", use_container_width=True, type="secondary"):
                reset_execution_state()
                st.session_state.current_phase = "settings"
                st.rerun()

    # Show confirmation warning if navigation requested during running
    if status == "running" and st.session_state.get("confirm_navigation", False):
        st.warning(
            "**Pipeline is running!** Navigating away will not stop the execution. "
            "Are you sure you want to go back to Settings?"
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, go back", use_container_width=True):
                st.session_state.confirm_navigation = False
                reset_execution_state()
                st.session_state.current_phase = "settings"
                st.rerun()
        with col2:
            if st.button("Cancel", use_container_width=True):
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
        st.info(f"**Processing:** {filename}")

        # Settings summary
        settings = st.session_state.settings
        provider = settings["llm_provider"].upper()
        max_pages = settings["max_pages"] or "All"
        report_lang = settings.get("report_language", "en").upper()
        steps = settings["steps_to_run"]
        steps_text = ", ".join([s.title() for s in steps])

        st.caption(
            f"**Settings:** {provider} | Max pages: {max_pages} | Report lang: {report_lang} | Steps: {steps_text}"
        )
    else:
        st.error("No PDF selected. Please go back to upload screen.")
        if st.button("Back to Upload"):
            st.session_state.current_phase = "upload"
            st.rerun()
        return

    st.markdown("---")

    # State machine for rerun prevention
    status = st.session_state.execution["status"]

    if status == "idle":
        # Transition to running state
        st.info("Starting pipeline execution...")
        st.session_state.execution["status"] = "running"
        st.session_state.execution["start_time"] = datetime.now()
        st.rerun()

    elif status == "running":
        # STEP-BY-STEP EXECUTION WITH UI UPDATES BETWEEN STEPS
        st.info("Pipeline is executing... Please wait.")

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

        # Guard: Prevent re-execution if step is already in progress
        # This handles Streamlit reruns during long-running LLM calls
        if st.session_state.get("_execution_in_progress"):
            st.info("Step is currently executing. Please wait...")
            st.stop()
            return

        # Set execution lock BEFORE starting step
        st.session_state["_execution_in_progress"] = True

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

            # Clear execution lock before rerun
            st.session_state["_execution_in_progress"] = False

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

            # Clear execution lock before rerun
            st.session_state["_execution_in_progress"] = False

            st.rerun()

    elif status == "completed":
        # Display completion UI
        st.success("Pipeline completed successfully!")

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
                        f"Redirecting to Settings screen in {countdown} second{'s' if countdown > 1 else ''}..."
                    )
                with col2:
                    if st.button("Cancel", key="cancel_redirect", use_container_width=True):
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
            st.info("Pipeline execution completed. View results in Settings screen or run again.")

    elif status == "failed":
        # Display error UI with step-level detection
        st.error("Pipeline execution failed")

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
            display_error_with_guidance(failed_step["error"], failed_step_name, failed_step)
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
