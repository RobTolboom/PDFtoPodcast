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
    Display settings configuration screen with pipeline control and step management.

    Renders a comprehensive settings UI with two tabs for pipeline configuration.
    Checks for existing pipeline results and provides smart defaults for step
    selection. Users can view/delete existing results, configure LLM settings,
    and set debugging options.

    Tab Structure:
        **Basic Settings:**
        - Pipeline Control section with 4-step checkboxes
        - Each step shows: [Checkbox + Name] [Status] [View/Delete buttons]
        - Status display: "✅ Done" with metadata or "⏸️ Not yet processed"
        - Smart defaults: Auto-selects steps without existing results
        - Action buttons (View/Delete) only shown if result file exists

        **Advanced:**
        - Processing Configuration:
          - LLM Provider selection (OpenAI/Claude)
          - Pages to Process (slider or "all pages" checkbox)
        - Debugging & Development:
          - Pipeline Breakpoint selector (stop after specific step)
          - Verbose logging toggle
        - File Management:
          - PDF Cleanup Policy (keep forever, 24h, 7days, etc.)

    State Management:
        Reads from session state:
        - current_phase: Current UI phase (should be "settings")
        - pdf_path: Path to selected PDF file
        - uploaded_file_info: Metadata dict for uploaded file
        - settings: Dictionary with pipeline configuration

        Writes to session state:
        - settings["steps_to_run"]: List of selected step keys
        - settings["llm_provider"]: Selected provider ("openai" or "claude")
        - settings["max_pages"]: Max pages (int or None for all)
        - settings["breakpoint"]: Pipeline stop point (str or None)
        - settings["verbose_logging"]: Boolean flag
        - settings["cleanup_policy"]: File retention policy string

    Navigation:
        - "Back to Upload" button: Sets current_phase = "upload"
        - "Start Pipeline" button: Sets current_phase = "execution"
        - Start button disabled if no steps selected

    Existing Results Management:
        Uses result_checker functions to:
        1. Get identifier from PDF path (filename stem)
        2. Check which steps have existing results
        3. Get file metadata (size, modified timestamp)
        4. Allow viewing JSON in modal dialog (via show_json_viewer)
        5. Allow deletion of individual result files

    Example Workflow:
        1. User arrives from upload screen with pdf_path set
        2. Screen checks for existing results (classification, extraction, etc.)
        3. Steps without results are auto-selected by default
        4. User can uncheck/check steps, view existing results, or delete them
        5. User configures advanced options (LLM, pages, debugging)
        6. User clicks "Start Pipeline" to proceed to execution phase

    Note:
        - If no PDF is selected (pdf_path is None), shows error and back button
        - Iteration files use numbered naming: extraction0.json, extraction1.json, validation0.json, etc.
        - All result files stored in tmp/ directory
        - Modal dialogs opened via show_json_viewer() function
        - File deletion triggers immediate st.rerun() to update UI
        - Warning shown if no steps selected (Start button disabled)
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
                "key": "validation_correction",
                "number": "3",
                "name": "Validation & Correction",
                "help": "Iterative validation and correction loop until quality thresholds are met",
            },
            {
                "key": "appraisal",
                "number": "4",
                "name": "Critical Appraisal",
                "help": "Assess study quality with RoB 2, ROBINS-I, PROBAST, AMSTAR 2, and GRADE ratings",
            },
            {
                "key": "report_generation",
                "number": "5",
                "name": "Report Generation",
                "help": "Generate structured report JSON ready for LaTeX rendering",
            },
            {
                "key": "podcast_generation",
                "number": "6",
                "name": "Podcast Generation",
                "help": "Generate podcast script from extraction and appraisal data",
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

        st.markdown("---")
        st.markdown("### Report Settings")
        current_lang = st.session_state.settings.get("report_language", "nl")
        lang_choice = st.selectbox(
            "Report language",
            options=["nl", "en"],
            index=0 if current_lang == "nl" else 1,
            help="Language used for report generation (affects all report sections).",
        )
        st.session_state.settings["report_language"] = lang_choice

        renderer_choice = st.selectbox(
            "Report renderer",
            options=["latex", "weasyprint"],
            index=0 if st.session_state.settings.get("report_renderer", "latex") == "latex" else 1,
            help="Choose output renderer. LaTeX gives best typography; WeasyPrint is HTML/CSS based.",
        )
        st.session_state.settings["report_renderer"] = renderer_choice

        st.session_state.settings["report_compile_pdf"] = st.checkbox(
            "Compile PDF (xelatex required)",
            value=st.session_state.settings.get("report_compile_pdf", True),
            help="If disabled, only .tex is produced. If xelatex is missing, this will warn and continue.",
        )

        st.session_state.settings["report_enable_figures"] = st.checkbox(
            "Generate figures (traffic light, forest)",
            value=st.session_state.settings.get("report_enable_figures", True),
            help="If disabled, figure blocks will be skipped.",
        )

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
                ["OpenAI (GPT-5.1)", "Claude (Coming Soon)"],
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
                **OpenAI (GPT-5.1)**
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

        # ==================== VALIDATION & CORRECTION ====================
        st.markdown("#### 🔁 Validation & Correction")

        col1, col2 = st.columns(2)

        with col1:
            max_iterations = st.number_input(
                "Maximum correction iterations",
                min_value=1,
                max_value=5,
                value=st.session_state.settings.get("max_correction_iterations", 3),
                help="Maximum number of correction attempts if quality is insufficient",
            )
            st.session_state.settings["max_correction_iterations"] = max_iterations

        with col2:
            st.caption("**Quality Thresholds**")
            st.caption("Loop stops when all thresholds are met or max iterations is reached")

        # Get current thresholds from session state
        current_thresholds = st.session_state.settings.get(
            "quality_thresholds",
            {
                "completeness_score": 0.90,
                "accuracy_score": 0.95,
                "schema_compliance_score": 0.95,
                "critical_issues": 0,
            },
        )

        # Threshold sliders (cap at 0.99 to prevent infinite loops!)
        completeness_threshold = st.slider(
            "Completeness threshold",
            min_value=0.5,
            max_value=0.99,
            value=current_thresholds.get("completeness_score", 0.90),
            step=0.05,
            help="Minimum required completeness score (0.90 = 90%). Max 99% - requiring perfect scores would prevent loop termination.",
        )

        accuracy_threshold = st.slider(
            "Accuracy threshold",
            min_value=0.5,
            max_value=0.99,
            value=current_thresholds.get("accuracy_score", 0.95),
            step=0.05,
            help="Minimum required accuracy score (0.95 = 95%). Max 99% - requiring perfect scores would prevent loop termination.",
        )

        schema_compliance_threshold = st.slider(
            "Schema compliance threshold",
            min_value=0.5,
            max_value=0.99,
            value=current_thresholds.get("schema_compliance_score", 0.95),
            step=0.05,
            help="Minimum required schema compliance score. Max 99% - requiring perfect scores would prevent loop termination.",
        )

        # Store thresholds in session state
        st.session_state.settings["quality_thresholds"] = {
            "completeness_score": completeness_threshold,
            "accuracy_score": accuracy_threshold,
            "schema_compliance_score": schema_compliance_threshold,
            "critical_issues": 0,  # Fixed - always 0
        }

        st.markdown("---")

        # ==================== APPRAISAL ====================
        st.markdown("#### 🎯 Critical Appraisal")

        col1, col2 = st.columns(2)

        with col1:
            max_appraisal_iterations = st.number_input(
                "Maximum appraisal iterations",
                min_value=1,
                max_value=5,
                value=st.session_state.settings.get("max_appraisal_iterations", 3),
                help="Maximum number of correction attempts for appraisal if quality is insufficient",
            )
        st.session_state.settings["max_appraisal_iterations"] = max_appraisal_iterations

        # Toggle for single-pass vs iterative correction
        enable_iterative = st.checkbox(
            "Enable iterative appraisal correction",
            value=st.session_state.settings.get("appraisal_enable_iterative_correction", True),
            help="Disable this to run appraisal once without automatic corrections (legacy mode).",
        )
        st.session_state.settings["appraisal_enable_iterative_correction"] = enable_iterative

        with col2:
            st.caption("**Quality Thresholds**")
            st.caption(
                "Appraisal loop stops when all thresholds are met or max iterations is reached"
            )

        # Get current appraisal thresholds from session state
        current_appraisal_thresholds = st.session_state.settings.get(
            "appraisal_quality_thresholds",
            {
                "logical_consistency_score": 0.90,
                "completeness_score": 0.85,
                "evidence_support_score": 0.90,
                "schema_compliance_score": 0.95,
                "critical_issues": 0,
            },
        )

        # Appraisal threshold sliders
        logical_consistency_threshold = st.slider(
            "Logical consistency threshold (appraisal)",
            min_value=0.5,
            max_value=0.99,
            value=current_appraisal_thresholds.get("logical_consistency_score", 0.90),
            step=0.05,
            help="Minimum required logical consistency (e.g., overall RoB matches worst domain). Max 99%.",
        )

        appraisal_completeness_threshold = st.slider(
            "Completeness threshold (appraisal)",
            min_value=0.5,
            max_value=0.99,
            value=current_appraisal_thresholds.get("completeness_score", 0.85),
            step=0.05,
            help="Minimum required completeness (all domains assessed, rationales substantive). Max 99%.",
        )

        evidence_support_threshold = st.slider(
            "Evidence support threshold",
            min_value=0.5,
            max_value=0.99,
            value=current_appraisal_thresholds.get("evidence_support_score", 0.90),
            step=0.05,
            help="Minimum required evidence support (judgements traceable to extraction). Max 99%.",
        )

        appraisal_schema_compliance_threshold = st.slider(
            "Schema compliance threshold (appraisal)",
            min_value=0.5,
            max_value=0.99,
            value=current_appraisal_thresholds.get("schema_compliance_score", 0.95),
            step=0.05,
            help="Minimum required schema compliance for appraisal. Max 99%.",
        )

        # Store appraisal thresholds in session state
        st.session_state.settings["appraisal_quality_thresholds"] = {
            "logical_consistency_score": logical_consistency_threshold,
            "completeness_score": appraisal_completeness_threshold,
            "evidence_support_score": evidence_support_threshold,
            "schema_compliance_score": appraisal_schema_compliance_threshold,
            "critical_issues": 0,  # Fixed - always 0
        }

        st.markdown("---")

        # ==================== DEBUGGING & DEVELOPMENT ====================
        st.markdown("#### 🔧 Debugging & Development")

        # Pipeline Breakpoint
        breakpoint_options = {
            None: "No breakpoint (run all steps)",
            "classification": "Stop after Classification",
            "extraction": "Stop after Extraction",
            "validation_correction": "Stop after Validation & Correction",
            "appraisal": "Stop after Critical Appraisal",
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
        if st.button("⬅️ Back to Upload", width="stretch"):
            st.session_state.current_phase = "upload"
            st.rerun()

    with col3:
        can_start = len(st.session_state.settings["steps_to_run"]) > 0
        if st.button(
            "▶️ Start Pipeline",
            type="primary",
            width="stretch",
            disabled=not can_start,
        ):
            st.session_state.current_phase = "execution"
            st.rerun()
