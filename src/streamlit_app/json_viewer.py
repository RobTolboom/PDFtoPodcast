# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
JSON viewer component for Streamlit interface.

Provides a modal dialog to display JSON result files from pipeline steps
with formatted display and file metadata.
"""

import json
from pathlib import Path

import streamlit as st


def show_json_viewer(file_path: str, step_name: str, file_info: dict):
    """
    Display JSON content in a modal dialog with metadata.

    Args:
        file_path: Path to JSON file to display
        step_name: Name of pipeline step (e.g., "Classification", "Extraction")
        file_info: Dictionary with file metadata:
            - modified: Last modified timestamp string
            - size_kb: File size in kilobytes

    Example:
        >>> file_info = {
        ...     "path": "tmp/paper-classification.json",
        ...     "modified": "2025-01-09 12:00:00",
        ...     "size_kb": 3.2
        ... }
        >>> show_json_viewer(
        ...     file_path="tmp/paper-classification.json",
        ...     step_name="Classification",
        ...     file_info=file_info
        ... )
    """
    # Icon mapping for each step type
    step_icons = {
        "Classification": "🏷️",
        "Extraction": "📊",
        "Validation": "✅",
        "Correction": "🔧",
    }

    icon = step_icons.get(step_name, "📋")

    # Create dialog with dynamic title
    @st.dialog(f"{icon} {step_name}", width="large")
    def dialog_content():
        try:
            with open(file_path) as f:
                json_content = json.load(f)

            # Display JSON with syntax highlighting
            st.json(json_content)

            # Show file metadata below JSON
            st.caption(
                f"📁 File: `{Path(file_path).name}` • "
                f"Modified: {file_info['modified']} • "
                f"Size: {file_info['size_kb']:.1f} KB"
            )

        except Exception as e:
            st.error(f"❌ Error reading file: {e}")

    # Call the dialog (Streamlit will handle modal display)
    dialog_content()
