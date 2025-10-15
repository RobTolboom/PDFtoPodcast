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

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.pipeline.orchestrator import run_four_step_pipeline


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
            }
            for step in ["classification", "extraction", "validation", "correction"]
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
    }

    st.session_state.step_status = {
        step: {
            "status": "pending",
            "start_time": None,
            "end_time": None,
            "result": None,
            "error": None,
            "elapsed_seconds": None,
        }
        for step in ["classification", "extraction", "validation", "correction"]
    }


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

        elif status == "failed":
            # Step failed with error
            step["status"] = "failed"
            step["end_time"] = datetime.now()
            step["elapsed_seconds"] = data.get("elapsed_seconds")
            step["error"] = data.get("error", "Unknown error")

        elif status == "skipped":
            # Step was skipped (not in steps_to_run or not needed)
            step["status"] = "skipped"
            # No timestamps for skipped steps

    return callback


def display_step_status(step_name: str, step_label: str, step_number: int):
    """
    Display status UI for a single pipeline step.

    Renders a Streamlit status container with:
    - Status icon (⏳ Pending / 🔄 Running / ✅ Success / ❌ Failed / ⏭️ Skipped)
    - Elapsed time (for running/completed steps)
    - Error message (for failed steps)
    - Expandable details section (collapsed by default)

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

    Example:
        >>> display_step_status("classification", "Classification", 1)
        # Renders: "Step 1: Classification  ✅ Completed in 8.3s"

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

    # Calculate elapsed time
    elapsed_text = ""
    if step["elapsed_seconds"] is not None:
        elapsed = step["elapsed_seconds"]
        elapsed_text = f" • {elapsed:.1f}s"
    elif status == "running" and step["start_time"] is not None:
        elapsed = (datetime.now() - step["start_time"]).total_seconds()
        elapsed_text = f" • {elapsed:.1f}s"

    # Status container configuration
    if status == "pending":
        # Not expandable for pending
        st.markdown(f"{icon} **{label}** - Not yet started")

    elif status == "running":
        # Auto-expanded for running
        with st.status(f"{icon} {label} - Running{elapsed_text}", expanded=True):
            st.write(f"Started: {step['start_time'].strftime('%H:%M:%S')}")
            st.write("Executing pipeline step...")

    elif status == "success":
        # Collapsed by default for success
        with st.status(f"{icon} {label} - Completed{elapsed_text}", expanded=False):
            st.write(f"Completed: {step['end_time'].strftime('%H:%M:%S')}")
            if step["result"]:
                st.write("Result data available")

    elif status == "failed":
        # Auto-expanded for errors
        with st.status(f"{icon} {label} - Failed{elapsed_text}", expanded=True, state="error"):
            st.error(f"**Error:** {step['error']}")
            if step["start_time"]:
                st.write(f"Started: {step['start_time'].strftime('%H:%M:%S')}")
            if step["end_time"]:
                st.write(f"Failed: {step['end_time'].strftime('%H:%M:%S')}")

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
        - Verbose logging placeholders (Fase 6 - TODO)
        - Advanced error handling (Fase 7 - TODO)
        - Auto-redirect (Fase 8 - TODO)
    """
    # Initialize state
    init_execution_state()

    # Header
    st.markdown("## 🚀 Pipeline Execution")

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
        steps = settings["steps_to_run"]
        steps_text = ", ".join([s.title() for s in steps])

        st.caption(f"**Settings:** {provider} • Max pages: {max_pages} • Steps: {steps_text}")
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
        # EXECUTE PIPELINE EXACTLY ONCE
        st.info("⏳ Pipeline is executing... Please wait.")

        try:
            # Create progress callback for real-time UI updates
            callback = create_progress_callback()

            # Extract settings
            settings = st.session_state.settings
            pdf_path = Path(st.session_state.pdf_path)

            # Call orchestrator with callbacks
            # Callback will update step_status in real-time during execution
            results = run_four_step_pipeline(
                pdf_path=pdf_path,
                max_pages=settings["max_pages"],
                llm_provider=settings["llm_provider"],
                steps_to_run=settings["steps_to_run"],
                progress_callback=callback,
                have_llm_support=True,
            )

            # Store results and mark as completed
            st.session_state.execution["results"] = results
            st.session_state.execution["status"] = "completed"
            st.session_state.execution["end_time"] = datetime.now()

            st.rerun()

        except Exception as e:
            # Handle pipeline errors gracefully
            st.session_state.execution["error"] = str(e)
            st.session_state.execution["status"] = "failed"
            st.session_state.execution["end_time"] = datetime.now()

            # TODO Fase 6: Store error traceback for verbose logging display
            # import traceback
            # error_traceback = traceback.format_exc()

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
        display_step_status("classification", "Classification", 1)
        display_step_status("extraction", "Extraction", 2)
        display_step_status("validation", "Validation", 3)
        display_step_status("correction", "Correction", 4)

        st.markdown("---")

        # TODO Fase 8: Auto-redirect to settings after 3 seconds
        st.info("💡 Pipeline execution completed. View results in Settings screen or run again.")

    elif status == "failed":
        # Display error UI
        st.error("❌ Pipeline execution failed")

        error_msg = st.session_state.execution.get("error", "Unknown error")
        st.markdown(f"**Error:** {error_msg}")

        # Show execution time if available
        start = st.session_state.execution["start_time"]
        end = st.session_state.execution["end_time"]
        if start and end:
            duration = (end - start).total_seconds()
            st.caption(f"**Failed after:** {duration:.1f}s")

        st.markdown("---")

        # Display step statuses to show where it failed
        st.markdown("### Pipeline Steps")
        display_step_status("classification", "Classification", 1)
        display_step_status("extraction", "Extraction", 2)
        display_step_status("validation", "Validation", 3)
        display_step_status("correction", "Correction", 4)

        st.markdown("---")

        # TODO Fase 7: More sophisticated error handling and actionable messages

    # Navigation button (always available)
    st.markdown("---")
    if st.button("⬅️ Back to Settings", use_container_width=False):
        reset_execution_state()
        st.session_state.current_phase = "settings"
        st.rerun()
