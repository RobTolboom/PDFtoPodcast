# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Streamlit session state initialization.

Provides centralized initialization of all session state variables
used throughout the application to avoid repetitive checks in app.py.
"""

import streamlit as st


def init_session_state():
    """
    Initialize all Streamlit session state variables with default values.

    This function should be called once at the start of the application
    (before any other Streamlit commands except st.set_page_config).

    Session state variables:
        - current_phase: Current UI phase ('intro', 'upload', 'settings', 'execution', 'results')
        - pdf_path: Path to selected PDF file (None if no file selected)
        - uploaded_file_info: Metadata dict for uploaded file
        - upload_tab: Active tab index in upload screen (0=Upload New, 1=Select Existing)
        - highlighted_file: Path to file that should be highlighted (for duplicate detection)
        - uploader_key: Counter to force file_uploader widget reset
        - settings: Dictionary with pipeline configuration:
            - llm_provider: LLM provider to use ('openai' or 'claude')
            - max_pages: Max pages to process (None = all pages)
            - steps_to_run: List of steps to execute
            - cleanup_policy: How long to keep uploaded files
            - breakpoint: Pipeline breakpoint for testing
            - verbose_logging: Enable verbose logging

    Example:
        >>> import streamlit as st
        >>> st.set_page_config(page_title="App")
        >>> init_session_state()
        >>> print(st.session_state.current_phase)
        'intro'

    Note:
        This function uses "if key not in st.session_state" checks to ensure
        idempotent behavior - it can be called multiple times safely and will
        only initialize missing keys. This is a Streamlit best practice to
        avoid resetting state during reruns.

        Phase flow: intro → upload → settings → execution → results
    """
    # Current UI phase
    if "current_phase" not in st.session_state:
        st.session_state.current_phase = "intro"

    # PDF file selection
    if "pdf_path" not in st.session_state:
        st.session_state.pdf_path = None

    if "uploaded_file_info" not in st.session_state:
        st.session_state.uploaded_file_info = None

    # Upload screen state
    if "upload_tab" not in st.session_state:
        st.session_state.upload_tab = 0  # 0 = Upload New, 1 = Select Existing

    if "highlighted_file" not in st.session_state:
        st.session_state.highlighted_file = None

    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0  # Counter to force file_uploader widget reset

    # Pipeline settings
    if "settings" not in st.session_state:
        st.session_state.settings = {
            "llm_provider": "openai",
            "max_pages": None,
            "steps_to_run": ["classification", "extraction", "validation_correction"],
            "cleanup_policy": "keep_forever",
            "breakpoint": None,
            "verbose_logging": False,
            "max_correction_iterations": 3,
            "quality_thresholds": {
                "completeness_score": 0.90,
                "accuracy_score": 0.95,
                "schema_compliance_score": 0.95,
                "critical_issues": 0,
            },
            "report_language": "nl",
            "report_renderer": "latex",
            "report_compile_pdf": True,
            "report_enable_figures": True,
            # Appraisal settings
            "max_appraisal_iterations": 3,
            "appraisal_enable_iterative_correction": True,
            "appraisal_quality_thresholds": {
                "logical_consistency_score": 0.90,
                "completeness_score": 0.85,
                "evidence_support_score": 0.90,
                "schema_compliance_score": 0.95,
                "critical_issues": 0,
            },
        }
