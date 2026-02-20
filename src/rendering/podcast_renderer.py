# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Podcast markdown renderer.

This module provides rendering functions to convert podcast JSON to human-readable
markdown format. The markdown output is designed for:
- Human readability
- TTS compatibility (plain text transcript, no structural markup)
- Easy distribution and sharing

The renderer produces a simple structure:
1. Title header (H1)
2. Metadata line (duration, word count, language, audience)
3. Continuous transcript (plain text, TTS-ready)
4. Show summary as plain text (optional, for podcast app descriptions)
5. Source attribution footer
"""

from pathlib import Path
from typing import Any

# Language code to full name mapping
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
}


def render_show_summary_plain_text(show_summary: dict[str, Any]) -> str:
    """Render show_summary as plain text for podcast apps and web.

    Produces unformatted text suitable for podcast app description fields,
    RSS feed descriptions, and web display. No markdown formatting is used.

    Args:
        show_summary: Dictionary with optional keys:
            - citation (str): Full citation string
            - synopsis (str): Episode synopsis paragraph
            - study_at_a_glance (list[dict]): Bullet items with label/content

    Returns:
        Plain text string with citation, synopsis, and study-at-a-glance bullets.
    """
    lines: list[str] = []

    citation = show_summary.get("citation", "")
    if citation:
        lines.append(f"Citation:\n{citation}")
        lines.append("")

    synopsis = show_summary.get("synopsis", "")
    if synopsis:
        lines.append(synopsis)
        lines.append("")

    bullets = show_summary.get("study_at_a_glance", [])
    if bullets:
        lines.append("Study at a glance")
        for bullet in bullets:
            if isinstance(bullet, dict):
                label = bullet.get("label", "")
                content_text = bullet.get("content", "")
                lines.append(f"- {label}: {content_text}")
            else:
                lines.append(f"- {bullet}")

    return "\n".join(lines)


def render_podcast_to_markdown(podcast: dict[str, Any], output_path: Path) -> Path:
    """
    Render podcast JSON to human-readable markdown.

    Args:
        podcast: Podcast JSON object with structure:
            {
                "metadata": {
                    "title": str,
                    "word_count": int,
                    "estimated_duration_minutes": int,
                    "language": str (default "en"),
                    "target_audience": str (default "practising clinicians"),
                    "study_id": str (optional)
                },
                "transcript": str (continuous text, TTS-ready),
                "show_summary": {  # optional
                    "citation": str,
                    "synopsis": str,
                    "study_at_a_glance": [{"label": str, "content": str}, ...]
                }
            }
        output_path: Full path where to save the .md file

    Returns:
        Path to the saved markdown file

    Raises:
        ValueError: If podcast structure is invalid or transcript is empty
        OSError: If file write fails

    Example:
        >>> podcast = {
        ...     "metadata": {"title": "Study X", "word_count": 950, ...},
        ...     "transcript": "This is the podcast script..."
        ... }
        >>> output_path = Path("tmp/study-podcast.md")
        >>> render_podcast_to_markdown(podcast, output_path)
        Path('tmp/study-podcast.md')
    """
    # Extract and validate metadata
    if not isinstance(podcast, dict):
        raise ValueError(f"Podcast must be a dict, got {type(podcast).__name__}")

    metadata = podcast.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"Podcast metadata must be a dict, got {type(metadata).__name__}")

    # Extract metadata fields with defaults
    title = metadata.get("title", "Podcast Script")
    word_count = metadata.get("word_count", 0)
    duration = metadata.get("estimated_duration_minutes", 0)
    language = LANGUAGE_NAMES.get(metadata.get("language", "en"), "English")
    audience = metadata.get("target_audience", "Practising clinicians")
    # Capitalize first letter if lowercase
    if audience and len(audience) > 0 and audience[0].islower():
        audience = audience[0].upper() + audience[1:]
    study_id = metadata.get("study_id", "N/A")

    # Extract and validate transcript
    transcript = podcast.get("transcript", "")
    if not transcript or not transcript.strip():
        raise ValueError("Podcast transcript is empty or contains only whitespace")

    # Build markdown content
    # Structure:
    # - H1: Title + "Podcast Script"
    # - Metadata line: Duration | Words | Language | Audience
    # - Horizontal rule
    # - Transcript (plain text, no escaping needed)
    # - Horizontal rule
    # - Show summary as plain text (if present)
    # - Horizontal rule (if show summary present)
    # - Footer: Source attribution
    lines = [
        f"# {title} - Podcast Script",
        "",
        f"**Duration**: ~{duration} minutes | **Words**: {word_count} | **Language**: {language} | **Audience**: {audience}",
        "",
        "---",
        "",
        transcript,  # Plain text, no escaping needed (TTS-ready)
        "",
        "---",
    ]

    # Append show summary as plain text (if present)
    show_summary = podcast.get("show_summary")
    if show_summary and isinstance(show_summary, dict):
        lines.append("")
        lines.append(render_show_summary_plain_text(show_summary))
        lines.append("")
        lines.append("---")

    lines.append("")
    lines.append(
        f"*Generated from: {study_id} | Sources: extraction-best.json, appraisal-best.json*"
    )

    md_content = "\n".join(lines)

    # Write to file
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_content, encoding="utf-8")
    except OSError as e:
        raise OSError(f"Failed to write markdown to {output_path}: {e}") from e

    return output_path
