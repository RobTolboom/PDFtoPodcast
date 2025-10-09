# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
PDFtoPodcast - Streamlit Web Interface

A web-based interface for the medical literature extraction pipeline.
Provides an intuitive UI for uploading PDFs and running the four-step extraction process:
1. Classification - Identify publication type
2. Extraction - Extract structured data
3. Validation - Quality control
4. Correction - Fix identified issues

This interface wraps the core pipeline functionality from run_pipeline.py.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

import streamlit as st

# Page configuration - must be first Streamlit command
st.set_page_config(
    page_title="PDFtoPodcast - Medical Literature Extraction",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
if "current_phase" not in st.session_state:
    st.session_state.current_phase = "intro"
if "pdf_path" not in st.session_state:
    st.session_state.pdf_path = None
if "uploaded_file_info" not in st.session_state:
    st.session_state.uploaded_file_info = None
if "upload_tab" not in st.session_state:
    st.session_state.upload_tab = 0  # 0 = Upload New, 1 = Select Existing
if "highlighted_file" not in st.session_state:
    st.session_state.highlighted_file = None
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0  # Counter to force file_uploader widget reset
if "settings" not in st.session_state:
    st.session_state.settings = {
        "llm_provider": "openai",
        "max_pages": None,
        "steps_to_run": ["classification", "extraction", "validation", "correction"],
        "cleanup_policy": "keep_forever",
        "breakpoint": None,
        "verbose_logging": False,
    }


# Upload directory and manifest
UPLOAD_DIR = Path("tmp/uploaded")
MANIFEST_FILE = UPLOAD_DIR / ".manifest.json"


def calculate_file_hash(file_bytes: bytes) -> str:
    """Calculate SHA256 hash of file content for duplicate detection."""
    return hashlib.sha256(file_bytes).hexdigest()


def load_manifest() -> dict:
    """Load manifest file containing metadata of all uploaded files."""
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE) as f:
                return json.load(f)
        except Exception:
            return {"files": []}
    return {"files": []}


def save_manifest(manifest: dict):
    """Save manifest file with updated file metadata."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)


def find_duplicate_by_hash(file_hash: str) -> dict | None:
    """Check if a file with this hash already exists. Returns file info if found."""
    manifest = load_manifest()
    for file_info in manifest["files"]:
        if file_info.get("hash") == file_hash:
            # Verify file still exists
            if Path(file_info["path"]).exists():
                return file_info
    return None


def add_file_to_manifest(file_info: dict):
    """Add a new file entry to the manifest."""
    manifest = load_manifest()
    manifest["files"].append(file_info)
    save_manifest(manifest)


def get_uploaded_files() -> list[dict]:
    """Get list of all previously uploaded files from manifest."""
    manifest = load_manifest()
    # Filter out files that no longer exist
    existing_files = [f for f in manifest["files"] if Path(f["path"]).exists()]
    # Update manifest if any files were removed
    if len(existing_files) != len(manifest["files"]):
        manifest["files"] = existing_files
        save_manifest(manifest)
    return existing_files


def show_json_viewer(file_path: str, step_name: str, file_info: dict):
    """Display JSON content in a modal dialog."""
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

            # Display JSON
            st.json(json_content)

            # Show file metadata
            st.caption(
                f"📁 File: `{Path(file_path).name}` • "
                f"Modified: {file_info['modified']} • "
                f"Size: {file_info['size_kb']:.1f} KB"
            )

        except Exception as e:
            st.error(f"❌ Error reading file: {e}")

    # Call the dialog
    dialog_content()


def get_identifier_from_pdf_path(pdf_path: str) -> str | None:
    """Extract identifier from PDF path for finding related result files."""
    # For now, use the PDF filename as identifier
    # Later this can be DOI-based after classification
    if not pdf_path:
        return None
    return Path(pdf_path).stem


def check_existing_results(identifier: str | None) -> dict:
    """Check which pipeline steps have existing results."""
    if not identifier:
        return {
            "classification": False,
            "extraction": False,
            "validation": False,
            "correction": False,
        }

    tmp_dir = Path("tmp")
    results = {
        "classification": (tmp_dir / f"{identifier}-classification.json").exists(),
        "extraction": (tmp_dir / f"{identifier}-extraction.json").exists(),
        "validation": (tmp_dir / f"{identifier}-validation.json").exists(),
        "correction": (tmp_dir / f"{identifier}-extraction-corrected.json").exists(),
    }
    return results


def get_result_file_info(identifier: str, step: str) -> dict | None:
    """Get metadata about a result file if it exists."""
    tmp_dir = Path("tmp")

    # Map step names to filenames
    file_map = {
        "classification": f"{identifier}-classification.json",
        "extraction": f"{identifier}-extraction.json",
        "validation": f"{identifier}-validation.json",
        "correction": f"{identifier}-extraction-corrected.json",
    }

    if step not in file_map:
        return None

    file_path = tmp_dir / file_map[step]
    if not file_path.exists():
        return None

    stat = file_path.stat()
    return {
        "path": str(file_path),
        "size_kb": stat.st_size / 1024,
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }


def show_intro_screen():
    """Display the introduction/welcome screen with logo, description, and license info."""

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
        if st.button("🚀 Start Pipeline", type="primary", use_container_width=True):
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


def show_settings_screen():
    """Display settings configuration screen with pipeline control."""

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


def show_upload_screen():
    """Display PDF upload screen with file validation, duplicate detection, and file selection."""

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
            # Validate file size (32 MB limit for most LLM APIs)
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

            st.rerun()

    # Route to appropriate screen based on current phase
    if st.session_state.current_phase == "intro":
        show_intro_screen()
    elif st.session_state.current_phase == "upload":
        show_upload_screen()
    elif st.session_state.current_phase == "settings":
        show_settings_screen()
    elif st.session_state.current_phase == "execution":
        st.info("🔄 Execution phase - coming in Phase 4")
    elif st.session_state.current_phase == "results":
        st.info("📊 Results phase - coming in Phase 5")


if __name__ == "__main__":
    main()
