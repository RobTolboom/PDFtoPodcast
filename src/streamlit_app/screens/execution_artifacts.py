# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Artifact display functions for pipeline execution screen.

This module handles the display of downloadable artifacts (reports, podcasts)
produced by the pipeline. Extracted from execution_display.py for modularity.

Public API:
    - display_report_artifacts(): Show report download buttons (LaTeX, PDF, Markdown)
    - display_podcast_artifacts(): Show podcast download buttons (JSON, Markdown, transcript)
"""

import json
from pathlib import Path

import streamlit as st

from src.pipeline.file_manager import PipelineFileManager
from src.rendering.podcast_renderer import render_show_summary_plain_text


def display_report_artifacts():
    """
    Show download buttons for report artifacts (.tex/.pdf/.md) if available.

    Discovers report files in the pipeline tmp directory and renders
    download buttons for each available format.

    Files checked:
        - render/report.tex (LaTeX source)
        - render/report.pdf (Compiled PDF)
        - render/report.md or {identifier}-report.md (Markdown)

    Note:
        Requires st.session_state.pdf_path to be set.
    """
    if not st.session_state.pdf_path:
        return

    fm = PipelineFileManager(Path(st.session_state.pdf_path))
    render_dir = fm.tmp_dir / "render"
    tex_file = render_dir / "report.tex"
    pdf_file = render_dir / "report.pdf"
    md_file = render_dir / "report.md"
    root_md = fm.tmp_dir / f"{fm.identifier}-report.md"

    st.markdown("### Report Artifacts")
    has_any = False

    if tex_file.exists():
        has_any = True
        with open(tex_file, "rb") as f:
            st.download_button("Download LaTeX (.tex)", f, file_name=tex_file.name)

    if pdf_file.exists():
        has_any = True
        with open(pdf_file, "rb") as f:
            st.download_button("Download PDF", f, file_name=pdf_file.name)

    if root_md.exists():
        has_any = True
        with open(root_md, "rb") as f:
            st.download_button("Download Markdown (.md)", f, file_name=root_md.name)
    elif md_file.exists():
        has_any = True
        with open(md_file, "rb") as f:
            st.download_button("Download Markdown (.md)", f, file_name=md_file.name)

    if not has_any:
        st.info("No report artifacts available yet. Run report generation to produce .tex/.pdf.")


def display_podcast_artifacts():
    """
    Show download buttons for podcast artifacts (.json/.md) if available.

    Discovers podcast files in the pipeline tmp directory and renders
    download buttons plus a transcript preview/copy area.

    Files checked:
        - {identifier}-podcast.json (Structured podcast data)
        - {identifier}-podcast.md (Human-readable script)

    Features:
        - Download buttons for JSON and Markdown
        - Expandable transcript preview
        - Copy-friendly text area for TTS input

    Note:
        Requires st.session_state.pdf_path to be set.
    """
    if not st.session_state.pdf_path:
        return

    fm = PipelineFileManager(Path(st.session_state.pdf_path))
    podcast_json = fm.tmp_dir / f"{fm.identifier}-podcast.json"
    podcast_md = fm.tmp_dir / f"{fm.identifier}-podcast.md"

    st.markdown("### Podcast Artifacts")
    has_any = False

    if podcast_json.exists():
        has_any = True
        with open(podcast_json, "rb") as f:
            st.download_button("Download Podcast JSON", f, file_name=podcast_json.name)

    if podcast_md.exists():
        has_any = True
        with open(podcast_md, "rb") as f:
            st.download_button("Download Podcast Script (.md)", f, file_name=podcast_md.name)

        # Also show transcript preview
        with open(podcast_md) as f:
            content = f.read()
        with st.expander("Preview Transcript"):
            st.markdown(content)

    # Copy transcript button (load from JSON for clean transcript only)
    if podcast_json.exists():
        with open(podcast_json) as f:
            podcast_data = json.load(f)
        transcript = podcast_data.get("transcript", "")
        if transcript:
            st.text_area(
                "Copy Transcript (for TTS)",
                transcript,
                height=150,
                key="podcast_transcript_copy",
            )

        # Show summary display (plain text for copy-paste to podcast apps)
        show_summary = podcast_data.get("show_summary")
        if show_summary:
            summary_text = render_show_summary_plain_text(show_summary)

            with st.expander("Show Summary"):
                st.text_area(
                    "Copy Show Summary (for podcast apps)",
                    summary_text,
                    height=250,
                    key="podcast_summary_copy",
                )

    if not has_any:
        st.info("No podcast artifacts available yet. Run podcast generation to produce script.")
