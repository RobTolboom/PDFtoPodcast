# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Introduction/welcome screen for Streamlit interface.

Displays project information, supported features, license details,
and navigation to start the pipeline.
"""

import streamlit as st


def show_intro_screen():
    """
    Display the introduction/welcome screen with project information and navigation.

    Renders a full-page welcome screen with:
    - Application title and description
    - Feature overview (4-step pipeline explanation)
    - "How it works" guide
    - Output format description
    - Best practices tips (sidebar box)
    - Supported publication types list (sidebar box)
    - License information (Prosperity Public License 3.0.0)
    - Usage warnings and disclaimers
    - "Start Pipeline" button to navigate to upload screen

    Layout Structure:
        - Centered header with title and tagline (HTML markdown)
        - Two-column main content (col1: 2/3 width, col2: 1/3 width)
        - Two-column license section
        - Centered navigation button
        - Footer with copyright and version info

    Navigation:
        Sets st.session_state.current_phase = "upload" on button click,
        then calls st.rerun() to refresh the UI and show upload screen.

    Note:
        This is the application entry point screen. Users must click
        "Start Pipeline" to proceed - there's no automatic progression.
        Uses st.markdown with unsafe_allow_html=True for custom styling.
    """
    # Main header with emoji logo (can replace with actual logo image later)
    st.markdown(
        """
        <div style="text-align: center; padding: 2rem 0;">
            <h1 style="font-size: 3rem; margin-bottom: 0;">PDFtoPodcast</h1>
            <p style="font-size: 1.3rem; color: #666; margin-top: 0.5rem;">
                Medical Literature Extraction Pipeline
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Project description
    st.markdown("---")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(
            """
            ### What does this application do?

            PDFtoPodcast is an intelligent extraction tool for medical literature that:

            - **Classifies** publications (RCT, observational, meta-analysis, etc.)
            - **Extracts** structured data from scientific articles
            - **Validates** the quality and accuracy of extracted data
            - **Corrects** automatically identified issues

            ### How does it work?

            1. Upload a PDF of a medical scientific article
            2. Configure extraction settings (LLM provider, max pages)
            3. Let the AI pipeline perform data extraction
            4. View and download the structured results

            ### Output Formats

            The pipeline generates JSON files with:
            - **Metadata** - Title, authors, DOI, Vancouver citation
            - **Study Design** - Study type, population, interventions
            - **Results** - Primary/secondary outcomes, statistical analyses
            - **Tables & Figures** - Structured data from tables and charts
            """
        )

    with col2:
        st.info(
            """
            **For optimal results:**
            - Use PDFs with clear structure
            - Start with max 10-20 pages for quick tests
            - Choose Claude for complex extractions
            - Use OpenAI for cost savings
            """
        )

        st.success(
            """
            **Supported Publication Types:**

            ✅ Interventional Trials (RCT)\n
            ✅ Observational Studies\n
            ✅ Evidence Synthesis (Meta-analyses)\n
            ✅ Prediction/Prognosis Models\n
            ✅ Editorials & Opinion Pieces
            """
        )

    # License information
    st.markdown("---")
    st.markdown("### License & Usage")

    license_col1, license_col2 = st.columns(2)

    with license_col1:
        st.markdown(
            """
            **Prosperity Public License 3.0.0**

            This software is available under the Prosperity Public License:
            - **Free for non-commercial use** (education, research, personal)
            - **Commercial use requires separate license**
            - See `LICENSE` and `COMMERCIAL_LICENSE.md` for details

            For commercial licenses, contact Tolboom Medical.
            """
        )

    with license_col2:
        st.warning(
            """
            **⚠️ Important**

            This tool is intended as a supporting tool for medical research.

            - Always verify extracted data with the original article
            - Do not use extracted data without validation for clinical decisions
            - Accuracy depends on PDF quality and AI model capabilities
            """
        )

    # Get started button
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 1])

    with col2:
        if st.button("🚀 Start Pipeline", type="primary", width="stretch"):
            st.session_state.current_phase = "upload"
            st.rerun()

    # Footer
    st.markdown(
        """
        <div style="text-align: center; padding: 2rem 0; color: #666; font-size: 0.9rem;">
            <p>Developed by Tolboom Medical | © 2025 | Version 1.0.0</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
