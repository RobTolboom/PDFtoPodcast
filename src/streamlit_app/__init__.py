# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Streamlit web interface package for PDF extraction pipeline.

This package provides a modular web interface for the medical literature
extraction pipeline, including file management, result visualization, and
pipeline execution control.

Main Components:
    - file_management: Upload handling, manifest management, duplicate detection
    - result_checker: Check for existing pipeline results
    - json_viewer: Display JSON results in modal dialogs
    - session_state: Streamlit session state initialization
    - screens: UI screen modules (intro, upload, settings)

Usage:
    >>> from src.streamlit_app import init_session_state
    >>> from src.streamlit_app.screens import show_intro_screen
    >>> init_session_state()
    >>> show_intro_screen()
"""

from .file_management import (
    MANIFEST_FILE,
    UPLOAD_DIR,
    add_file_to_manifest,
    calculate_file_hash,
    find_duplicate_by_hash,
    get_uploaded_files,
    load_manifest,
    save_manifest,
)
from .json_viewer import show_json_viewer
from .result_checker import (
    check_existing_results,
    get_identifier_from_pdf_path,
    get_result_file_info,
)
from .session_state import init_session_state

__all__ = [
    # Session state
    "init_session_state",
    # File management
    "UPLOAD_DIR",
    "MANIFEST_FILE",
    "calculate_file_hash",
    "load_manifest",
    "save_manifest",
    "find_duplicate_by_hash",
    "add_file_to_manifest",
    "get_uploaded_files",
    # Result checking
    "get_identifier_from_pdf_path",
    "check_existing_results",
    "get_result_file_info",
    # JSON viewer
    "show_json_viewer",
]
