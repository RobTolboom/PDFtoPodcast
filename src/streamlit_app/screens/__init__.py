# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Streamlit UI screen modules.

This package contains the individual screen implementations for the
Streamlit web interface. Each screen is a self-contained module that
renders a complete UI phase.

Screens:
    - intro: Welcome/introduction screen with license info and feature overview
    - upload: PDF upload and file selection screen with duplicate detection
    - settings: Pipeline configuration screen with step selection and options

Screen Flow:
    The application follows a linear phase progression controlled by
    st.session_state.current_phase:

    intro → upload → settings → execution → results

Usage Example:
    >>> import streamlit as st
    >>> from src.streamlit_app import init_session_state
    >>> from src.streamlit_app.screens import (
    ...     show_intro_screen,
    ...     show_upload_screen,
    ...     show_settings_screen
    ... )
    >>>
    >>> # Initialize session state first
    >>> init_session_state()
    >>>
    >>> # Render appropriate screen based on current phase
    >>> if st.session_state.current_phase == "intro":
    ...     show_intro_screen()
    >>> elif st.session_state.current_phase == "upload":
    ...     show_upload_screen()
    >>> elif st.session_state.current_phase == "settings":
    ...     show_settings_screen()
"""

from .intro import show_intro_screen
from .settings import show_settings_screen
from .upload import show_upload_screen

__all__ = [
    "show_intro_screen",
    "show_upload_screen",
    "show_settings_screen",
]
