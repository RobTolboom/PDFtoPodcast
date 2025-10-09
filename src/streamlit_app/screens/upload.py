# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
PDF upload screen for Streamlit interface.

Provides two methods for selecting PDFs:
1. Upload new files with duplicate detection
2. Select from previously uploaded files

Features:
- File size validation (10 MB limit for API compatibility)
- SHA256 hash-based duplicate detection
- Manifest-based file tracking
- File metadata display
"""

from datetime import datetime
from pathlib import Path

import streamlit as st

from ..file_management import (
    UPLOAD_DIR,
    add_file_to_manifest,
    calculate_file_hash,
    find_duplicate_by_hash,
    get_uploaded_files,
)


def show_upload_screen():
    """
    Display PDF upload screen with file validation, duplicate detection, and file selection.

    Provides two tabs:
        1. Upload New File - Upload a PDF with validation and duplicate detection
        2. Select Previously Uploaded - Choose from files already in the system

    After selection, shows navigation buttons to proceed to settings or return to intro.
    """
    st.markdown("## 📤 Select PDF document")
    st.markdown("Upload a new PDF or select a previously uploaded file.")

    st.markdown("---")

    # Create upload directory if it doesn't exist
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Tabs for upload methods
    tab1, tab2 = st.tabs(["📤 Upload New File", "📁 Select Previously Uploaded"])

    # Tab 1: Upload New File
    with tab1:
        st.markdown("### Upload a new PDF document")

        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type=["pdf"],
            help="Maximum file size: 10 MB (OpenAI/Claude API limit)",
            key=f"new_file_uploader_{st.session_state.uploader_key}",
        )

        if uploaded_file is not None:
            # Validate file size (10 MB limit for most LLM APIs)
            file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)

            if file_size_mb > 10:
                st.error(
                    f"❌ File too large: {file_size_mb:.1f} MB. Maximum allowed: 10 MB.\n\n"
                    "Please reduce the file size or select a different file."
                )
            else:
                # Calculate file hash for duplicate detection
                file_bytes = uploaded_file.getvalue()
                file_hash = calculate_file_hash(file_bytes)

                # Check for duplicates
                duplicate = find_duplicate_by_hash(file_hash)

                if duplicate:
                    # Duplicate found - show warning and switch to selection tab
                    dup_name = (
                        duplicate.get("original_name")
                        or duplicate.get("filename")
                        or Path(duplicate["path"]).name
                    )
                    dup_date = duplicate.get("upload_time", "Unknown")[:10]
                    st.warning(
                        f"⚠️ **Duplicate detected!**\n\n"
                        f"This file was already uploaded as:\n"
                        f"- **{dup_name}**\n"
                        f"- Uploaded on: {dup_date}\n\n"
                        f"Please use the **'Select Previously Uploaded'** tab to select this file."
                    )

                    # Highlight the duplicate file for easy selection
                    st.session_state.highlighted_file = duplicate["path"]

                    st.info(
                        "👉 Switch to the **'Select Previously Uploaded'** tab to use this file."
                    )
                    # Don't return - let Tab 2 render

                else:
                    # No duplicate - proceed with upload
                    # Generate unique filename with timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_filename = uploaded_file.name.replace(" ", "_")
                    filename = f"{timestamp}_{safe_filename}"
                    file_path = UPLOAD_DIR / filename

                    # Save uploaded file to disk
                    try:
                        with open(file_path, "wb") as f:
                            f.write(file_bytes)

                        # Create file info with hash
                        file_info = {
                            "hash": file_hash,
                            "path": str(file_path),
                            "original_name": uploaded_file.name,
                            "size_mb": file_size_mb,
                            "upload_time": datetime.now().isoformat(),
                        }

                        # Add to manifest
                        add_file_to_manifest(file_info)

                        # Store in session state
                        st.session_state.pdf_path = str(file_path)
                        st.session_state.uploaded_file_info = file_info

                        # Show success message with file preview
                        st.success(f"✅ File uploaded successfully: **{uploaded_file.name}**")

                        # Display file information
                        col1, col2 = st.columns(2)

                        with col1:
                            st.info(
                                f"""
                                **📄 File Information**

                                - **Filename:** {uploaded_file.name}
                                - **Size:** {file_size_mb:.2f} MB
                                - **Saved to:** `{file_path.name}`
                                """
                            )

                        with col2:
                            st.success(
                                """
                                **✅ Upload Status**

                                File has been saved and is ready for processing.

                                Click "Continue to Settings" to configure extraction parameters.
                                """
                            )

                    except Exception as e:
                        st.error(f"❌ Error saving file: {e}")
                        st.markdown("Please try uploading the file again or contact support.")

        else:
            # Show helpful information when no file is uploaded
            st.info(
                """
                **📋 Requirements:**

                - File format: PDF only
                - Maximum size: 10 MB
                - Recommended: Scientific medical publications (research articles, trials, reviews)

                **💡 Tips:**

                - Ensure the PDF has clear text (not scanned images only)
                - For large files, consider using only relevant pages (can configure in settings)
                - High-quality PDFs produce better extraction results
                """
            )

    # Tab 2: Select Previously Uploaded Files
    with tab2:
        st.markdown("### Select from previously uploaded files")

        uploaded_files = get_uploaded_files()

        # Debug output
        st.caption(f"Debug: Found {len(uploaded_files)} file(s) in manifest")

        if not uploaded_files:
            st.info(
                "📭 No previously uploaded files found.\n\n"
                "Upload a file using the **'Upload New File'** tab first."
            )
        else:
            # Sort by upload time (newest first)
            uploaded_files.sort(key=lambda x: x["upload_time"], reverse=True)

            st.markdown(f"Found **{len(uploaded_files)}** previously uploaded file(s):")
            st.markdown("---")

            # Display each file with selection option
            for idx, file_info in enumerate(uploaded_files):
                file_path = Path(file_info["path"])
                is_highlighted = st.session_state.highlighted_file == file_info["path"]

                # Safe access to file metadata with fallbacks
                display_name = (
                    file_info.get("original_name") or file_info.get("filename") or file_path.name
                )
                upload_time = file_info.get("upload_time", "Unknown")[:19]
                file_size = file_info.get("size_mb", 0)

                # Highlight the file that was just uploaded/selected
                if is_highlighted:
                    st.success("✅ **This is the file you just uploaded**")

                col1, col2, col3 = st.columns([3, 2, 1])

                with col1:
                    st.markdown(f"**📄 {display_name}**")
                    st.caption(f"Uploaded: {upload_time}")

                with col2:
                    st.markdown(f"**Size:** {file_size:.2f} MB")
                    st.caption(f"Path: {file_path.name}")

                with col3:
                    if st.button(
                        "✅ Select",
                        key=f"select_{idx}",
                        type="primary" if is_highlighted else "secondary",
                        use_container_width=True,
                    ):
                        # Set selected file in session state
                        st.session_state.pdf_path = file_info["path"]
                        st.session_state.uploaded_file_info = file_info
                        st.session_state.highlighted_file = None
                        st.success(f"Selected: {display_name}")
                        st.rerun()

                st.markdown("---")

    # Navigation buttons (shown below tabs if a file is selected)
    if st.session_state.pdf_path:
        st.markdown("---")
        # Safe access to filename with fallback
        file_info = st.session_state.uploaded_file_info
        filename = (
            file_info.get("original_name")
            or file_info.get("filename")
            or Path(st.session_state.pdf_path).name
        )
        st.success(f"✅ **Selected file:** {filename}")

        col1, col2, col3 = st.columns([1, 1, 1])

        with col1:
            if st.button("⬅️ Back to Intro", use_container_width=True, key="nav_back"):
                st.session_state.current_phase = "intro"
                st.rerun()

        with col2:
            if st.button("🔄 Select Different File", use_container_width=True, key="nav_reset"):
                # Reset session state and force file_uploader to clear
                st.session_state.pdf_path = None
                st.session_state.uploaded_file_info = None
                st.session_state.highlighted_file = None
                st.session_state.uploader_key += 1  # Increment to force widget remount
                st.rerun()

        with col3:
            if st.button(
                "➡️ Continue to Settings",
                type="primary",
                use_container_width=True,
                key="nav_continue",
            ):
                st.session_state.current_phase = "settings"
                st.rerun()
    else:
        # Back button when no file selected
        st.markdown("---")
        if st.button("⬅️ Back to Intro", use_container_width=False, key="nav_back_nofile"):
            st.session_state.current_phase = "intro"
            st.rerun()
