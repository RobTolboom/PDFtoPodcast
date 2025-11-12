# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
PDFtoPodcast - Streamlit Web Interface

A web-based interface for the medical literature extraction pipeline.
Provides an intuitive UI for uploading PDFs and running the four-step process:
1. Classification - Identify publication type
2. Extraction - Extract structured data
3. Validation & Correction - Iterative quality control
4. Appraisal - Critical appraisal with RoB/GRADE summary

This interface wraps the core pipeline functionality from run_pipeline.py.
"""

import streamlit as st

# Import streamlit_app components
from src.streamlit_app import init_session_state
from src.streamlit_app.screens import (
    show_execution_screen,
    show_intro_screen,
    show_settings_screen,
    show_upload_screen,
)
from src.streamlit_app.screens.execution import reset_execution_state

# Page configuration - must be first Streamlit command
st.set_page_config(
    page_title="PDFtoPodcast - Medical Literature Extraction",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
init_session_state()


def main():
    """Main application entry point."""

    # Sidebar navigation
    with st.sidebar:
        st.markdown("### Pipeline Steps")

        # Show pipeline progress indicators
        phases = {
            "intro": "Introduction",
            "upload": "Select PDF",
            "settings": "Settings",
            "execution": "Execution",
            "results": "Results",
        }

        current = st.session_state.current_phase
        for phase_key, phase_name in phases.items():
            if phase_key == current:
                st.markdown(f"**→ {phase_name}** ✓")
            else:
                st.markdown(f"   {phase_name}")
        st.markdown("---")
        if st.button("Back to Start"):
            # Reset to intro phase
            st.session_state.current_phase = "intro"

            # Clear file selection state
            st.session_state.pdf_path = None
            st.session_state.uploaded_file_info = None
            st.session_state.highlighted_file = None
            st.session_state.uploader_key += 1  # Force file_uploader widget reset

            # Reset execution state to prevent "process already done" issue
            reset_execution_state()

            st.rerun()

    # Route to appropriate screen based on current phase
    if st.session_state.current_phase == "intro":
        show_intro_screen()
    elif st.session_state.current_phase == "upload":
        show_upload_screen()
    elif st.session_state.current_phase == "settings":
        show_settings_screen()
    elif st.session_state.current_phase == "execution":
        show_execution_screen()
    elif st.session_state.current_phase == "results":
        st.info("📊 Results phase - coming in Phase 5")


if __name__ == "__main__":
    main()
