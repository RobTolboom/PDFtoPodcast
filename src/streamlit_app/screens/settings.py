# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Settings configuration screen for Streamlit interface.

Allows users to configure pipeline execution:
- Select which steps to run
- View/delete existing results
- Configure LLM provider and page limits
- Set debugging options (breakpoints, verbose logging)
- Configure file cleanup policies
"""

from pathlib import Path

import streamlit as st

from ..json_viewer import show_json_viewer
from ..result_checker import (
    check_existing_results,
    get_identifier_from_pdf_path,
    get_result_file_info,
)


def show_settings_screen():
    """
    Display settings configuration screen with pipeline control.

    Provides two tabs:
        1. Basic Settings - Step selection, existing results management
        2. Advanced - LLM provider, page limits, debugging, file management

    Shows which pipeline steps have existing results and allows:
    - Selective execution of steps
    - Viewing existing results in modal dialogs
    - Deleting individual result files
    - Configuring processing options
    """
    st.markdown("## ⚙️ Configure Extraction Settings")
    st.markdown("Configure how the pipeline should process your PDF document.")

    st.markdown("---")

    # Show selected file info
    if st.session_state.pdf_path:
        file_info = st.session_state.uploaded_file_info
        filename = (
            file_info.get("original_name")
            or file_info.get("filename")
            or Path(st.session_state.pdf_path).name
        )
        st.success(f"📄 **Selected PDF:** {filename}")
    else:
        st.error("⚠️ No PDF selected. Please go back and upload a file.")
        if st.button("⬅️ Back to Upload"):
            st.session_state.current_phase = "upload"
            st.rerun()
        return

    # Tabs for Basic and Advanced settings
    tab1, tab2 = st.tabs(["🔧 Basic Settings", "⚡ Advanced"])

    with tab1:
        st.markdown("### Pipeline Control")

        # Check for existing results
        identifier = get_identifier_from_pdf_path(st.session_state.pdf_path)
        existing = check_existing_results(identifier)

        # Define all pipeline steps
        steps = [
            {
                "key": "classification",
                "number": "1",
                "name": "Classification",
                "help": "Identify publication type and extract metadata",
            },
            {
                "key": "extraction",
                "number": "2",
                "name": "Extraction",
                "help": "Extract structured data based on publication type",
            },
            {
                "key": "validation",
                "number": "3",
                "name": "Validation",
                "help": "Validate quality and accuracy of extracted data",
            },
            {
                "key": "correction",
                "number": "4",
                "name": "Correction",
                "help": "Automatically fix issues identified during validation",
            },
        ]

        # Smart defaults: auto-select steps that don't have results yet
        default_steps = []
        for step in steps:
            if not existing[step["key"]]:
                default_steps.append(step["key"])
        # Correction always included by default if validation will run
        if "validation" in default_steps:
            default_steps.append("correction")

        # Track selected steps
        steps_to_run = []

        # Display each step in unified format
        for step in steps:
            step_key = step["key"]
            step_exists = existing[step_key]

            # Get file info if exists
            file_info = None
            if step_exists:
                file_info = get_result_file_info(identifier, step_key)

            # Create columns: [checkbox + name] [status] [actions]
            col1, col2, col3 = st.columns([3, 4, 1.5])

            with col1:
                # Execution checkbox (always enabled - user has full control)
                is_selected = st.checkbox(
                    f"{step['number']}. {step['name']}",
                    value=step_key in default_steps,
                    help=step["help"],
                    key=f"run_{step_key}",
                )
                if is_selected:
                    steps_to_run.append(step_key)

            with col2:
                # Status display
                if file_info:
                    st.markdown(
                        f"✅ **Done** • {file_info['modified']} • {file_info['size_kb']:.1f} KB"
                    )
                else:
                    st.markdown("⏸️ *Not yet processed*")

            with col3:
                # Action buttons (only if file exists)
                if file_info:
                    # Place buttons side-by-side with minimal spacing
                    btn1, btn2 = st.columns([1, 1])
                    with btn1:
                        if st.button("👁️", key=f"view_{step_key}", help="View results"):
                            show_json_viewer(file_info["path"], step["name"], file_info)
                    with btn2:
                        if st.button("🗑️", key=f"delete_{step_key}", help="Delete result"):
                            Path(file_info["path"]).unlink()
                            st.success(f"Deleted {step['name']} results")
                            st.rerun()

        # Update settings
        st.session_state.settings["steps_to_run"] = steps_to_run

        if not steps_to_run:
            st.warning("⚠️ No steps selected. Please select at least one step to execute.")

    with tab2:
        st.markdown("### Advanced Settings")

        # ==================== PROCESSING CONFIGURATION ====================
        st.markdown("#### 📊 Processing Configuration")

        # LLM Provider
        st.markdown("**LLM Provider**")

        col1, col2 = st.columns(2)

        with col1:
            openai_selected = st.radio(
                "Select LLM provider",
                ["OpenAI (GPT-5)", "Claude (Coming Soon)"],
                index=0,
                disabled=False,
                label_visibility="collapsed",
            )
            if "Claude" in openai_selected:
                st.info(
                    "🚧 Claude integration is in development. Currently only OpenAI is available."
                )
                st.session_state.settings["llm_provider"] = "openai"
            else:
                st.session_state.settings["llm_provider"] = "openai"

        with col2:
            st.info(
                """
                **OpenAI (GPT-5)**
                - Fast processing
                - Cost-effective
                - Reliable for most documents
                """
            )

        st.markdown("")

        # Pages to Process
        st.markdown("**Pages to Process**")

        process_all = st.checkbox(
            "Process all pages", value=st.session_state.settings["max_pages"] is None
        )

        if not process_all:
            max_pages = st.slider(
                "Maximum pages to process",
                min_value=1,
                max_value=100,
                value=20,
                help="For quick tests, start with 10-20 pages",
            )
            st.session_state.settings["max_pages"] = max_pages
        else:
            st.session_state.settings["max_pages"] = None
            st.caption("ℹ️ All pages will be processed (may take longer and cost more)")

        st.markdown("---")

        # ==================== DEBUGGING & DEVELOPMENT ====================
        st.markdown("#### 🔧 Debugging & Development")

        # Pipeline Breakpoint
        breakpoint_options = {
            None: "No breakpoint (run all steps)",
            "classification": "Stop after Classification",
            "extraction": "Stop after Extraction",
            "validation": "Stop after Validation",
        }

        breakpoint = st.selectbox(
            "Pipeline Breakpoint",
            options=list(breakpoint_options.keys()),
            format_func=lambda x: breakpoint_options[x],
            index=0,
            help="Stop the pipeline after a specific step for testing",
        )
        st.session_state.settings["breakpoint"] = breakpoint

        st.markdown("")

        # Verbose logging
        verbose = st.checkbox(
            "Enable verbose logging",
            value=st.session_state.settings["verbose_logging"],
            help="Show detailed logs during processing",
        )
        st.session_state.settings["verbose_logging"] = verbose

        st.markdown("---")

        # ==================== FILE MANAGEMENT ====================
        st.markdown("#### 🗂️ File Management")

        # Cleanup policy
        cleanup_options = {
            "keep_forever": "Keep Forever",
            "24h": "Delete after 24 hours",
            "7days": "Delete after 7 days",
            "after_session": "Delete after session ends",
            "immediate": "Delete immediately after processing",
        }

        cleanup_policy = st.selectbox(
            "PDF Cleanup Policy",
            options=list(cleanup_options.keys()),
            format_func=lambda x: cleanup_options[x],
            index=0,
            help="How long should uploaded PDFs be retained?",
        )
        st.session_state.settings["cleanup_policy"] = cleanup_policy

    # Navigation buttons
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        if st.button("⬅️ Back to Upload", use_container_width=True):
            st.session_state.current_phase = "upload"
            st.rerun()

    with col3:
        can_start = len(st.session_state.settings["steps_to_run"]) > 0
        if st.button(
            "▶️ Start Pipeline",
            type="primary",
            use_container_width=True,
            disabled=not can_start,
        ):
            st.session_state.current_phase = "execution"
            st.rerun()
