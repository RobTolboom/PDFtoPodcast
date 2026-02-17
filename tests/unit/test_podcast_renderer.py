# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for podcast markdown renderer.

Tests the podcast_renderer module which converts podcast JSON to human-readable
markdown format. Focus areas:
- Markdown structure correctness
- Metadata defaults handling
- Transcript preservation (no modifications)
- Error handling for invalid input
"""

from pathlib import Path

import pytest

from src.rendering.podcast_renderer import render_podcast_to_markdown


def test_render_podcast_basic(tmp_path):
    """Test rendering a complete podcast with all metadata fields."""
    podcast = {
        "podcast_version": "v1.0",
        "metadata": {
            "title": "Test Study - Efficacy of Drug X",
            "word_count": 950,
            "estimated_duration_minutes": 6,
            "language": "en",
            "target_audience": "practising clinicians",
            "study_id": "doi:10.1234/test",
        },
        "transcript": "This is a test podcast transcript. It contains multiple sentences. The study investigated the efficacy of Drug X versus placebo in treating condition Y.",
    }

    output_path = tmp_path / "test-podcast.md"
    result_path = render_podcast_to_markdown(podcast, output_path)

    # Verify file was created and returned path matches
    assert result_path.exists()
    assert result_path == output_path

    # Read and validate content
    content = result_path.read_text(encoding="utf-8")

    # Validate structure components
    assert "# Test Study - Efficacy of Drug X - Podcast Script" in content
    assert "**Duration**: ~6 minutes" in content
    assert "**Words**: 950" in content
    assert "**Language**: English" in content
    assert "**Audience**: Practising clinicians" in content
    assert "This is a test podcast transcript" in content
    assert "*Generated from: doi:10.1234/test" in content
    assert "Sources: extraction-best.json, appraisal-best.json" in content

    # Validate horizontal rules present
    assert content.count("---") == 2


def test_render_podcast_metadata_defaults(tmp_path):
    """Test rendering with minimal metadata - should use sensible defaults."""
    podcast = {
        "metadata": {"title": "Minimal Test Study"},
        "transcript": "Short transcript for minimal test.",
    }

    output_path = tmp_path / "minimal.md"
    result_path = render_podcast_to_markdown(podcast, output_path)

    content = result_path.read_text(encoding="utf-8")

    # Validate defaults are applied
    assert "**Words**: 0" in content  # Default word_count
    assert "**Duration**: ~0 minutes" in content  # Default duration
    assert "**Language**: English" in content  # Default language (full name)
    assert "**Audience**: Practising clinicians" in content  # Default audience (capitalized)
    assert "*Generated from: N/A" in content  # Default study_id

    # Validate transcript still present
    assert "Short transcript for minimal test." in content


def test_render_podcast_transcript_preservation(tmp_path):
    """Test that transcript is preserved exactly without modifications."""
    # Transcript with various characters that should NOT be escaped
    special_transcript = """This transcript contains special characters:
asterisks *, underscores _, brackets [text], parentheses (text),
and even a hash # symbol. Numbers like 12.5 mg/kg should remain intact.
Medical terms like β-blocker and <0.001 p-value are preserved."""

    podcast = {
        "metadata": {"title": "Special Characters Test"},
        "transcript": special_transcript,
    }

    output_path = tmp_path / "special.md"
    result_path = render_podcast_to_markdown(podcast, output_path)

    content = result_path.read_text(encoding="utf-8")

    # Extract transcript from markdown (between the two --- separators)
    parts = content.split("---")
    assert len(parts) >= 3  # Header, transcript, footer
    extracted_transcript = parts[1].strip()

    # Verify transcript is EXACTLY preserved (no escaping, no modifications)
    assert extracted_transcript == special_transcript.strip()


def test_render_podcast_empty_transcript_raises_error():
    """Test that empty transcript raises ValueError."""
    podcast = {"metadata": {"title": "Empty Test"}, "transcript": ""}

    with pytest.raises(ValueError, match="transcript is empty"):
        render_podcast_to_markdown(podcast, Path("/tmp/test.md"))


def test_render_podcast_whitespace_only_transcript_raises_error():
    """Test that whitespace-only transcript raises ValueError."""
    podcast = {"metadata": {"title": "Whitespace Test"}, "transcript": "   \n\t  "}

    with pytest.raises(ValueError, match="transcript is empty"):
        render_podcast_to_markdown(podcast, Path("/tmp/test.md"))


def test_render_podcast_missing_metadata_dict():
    """Test that missing metadata dict uses defaults."""
    podcast = {"transcript": "Valid transcript without metadata dict."}

    output_path = Path("/tmp/no-metadata.md")
    try:
        result_path = render_podcast_to_markdown(podcast, output_path)
        content = result_path.read_text(encoding="utf-8")

        # Should use all defaults
        assert "# Podcast Script - Podcast Script" in content  # Default title
        assert "**Words**: 0" in content
        assert "*Generated from: N/A" in content
    finally:
        # Cleanup
        if output_path.exists():
            output_path.unlink()


def test_render_podcast_invalid_podcast_type():
    """Test that non-dict podcast raises ValueError."""
    invalid_podcasts = [
        "string podcast",
        ["list", "podcast"],
        123,
        None,
    ]

    for invalid in invalid_podcasts:
        with pytest.raises(ValueError, match="Podcast must be a dict"):
            render_podcast_to_markdown(invalid, Path("/tmp/test.md"))


def test_render_podcast_invalid_metadata_type():
    """Test that non-dict metadata raises ValueError."""
    podcast = {"metadata": "invalid metadata string", "transcript": "Valid transcript"}

    with pytest.raises(ValueError, match="metadata must be a dict"):
        render_podcast_to_markdown(podcast, Path("/tmp/test.md"))


def test_render_podcast_creates_parent_directories(tmp_path):
    """Test that parent directories are created if they don't exist."""
    nested_path = tmp_path / "level1" / "level2" / "level3" / "podcast.md"
    assert not nested_path.parent.exists()

    podcast = {
        "metadata": {"title": "Nested Path Test"},
        "transcript": "Testing directory creation.",
    }

    result_path = render_podcast_to_markdown(podcast, nested_path)

    # Verify file and all parent directories were created
    assert result_path.exists()
    assert nested_path.parent.exists()


def test_render_podcast_language_full_name(tmp_path):
    """Test that language code is converted to full name."""
    podcast = {
        "metadata": {"title": "Language Test", "language": "en"},
        "transcript": "Testing language field transformation.",
    }

    output_path = tmp_path / "language.md"
    result_path = render_podcast_to_markdown(podcast, output_path)

    content = result_path.read_text(encoding="utf-8")
    assert "**Language**: English" in content  # Should be full name


def test_render_podcast_multiline_transcript(tmp_path):
    """Test rendering transcript with multiple paragraphs/lines."""
    multiline_transcript = """This is the first paragraph of the podcast.

This is the second paragraph with some important information.

And here is the third paragraph concluding the podcast."""

    podcast = {
        "metadata": {"title": "Multiline Test"},
        "transcript": multiline_transcript,
    }

    output_path = tmp_path / "multiline.md"
    result_path = render_podcast_to_markdown(podcast, output_path)

    content = result_path.read_text(encoding="utf-8")

    # Verify multiline structure is preserved
    assert "first paragraph" in content
    assert "second paragraph" in content
    assert "third paragraph" in content

    # Extract and verify exact preservation
    parts = content.split("---")
    extracted_transcript = parts[1].strip()
    assert extracted_transcript == multiline_transcript.strip()


def test_render_podcast_with_show_summary(tmp_path):
    """Test rendering podcast with show_summary as plain text."""
    podcast = {
        "metadata": {"title": "Summary Test", "word_count": 950, "estimated_duration_minutes": 6},
        "transcript": "This is the transcript content for the test.",
        "show_summary": {
            "citation": "Lee D, Lee H. Impact of Suggestions on Dreaming. Anesth Analg. 2025.",
            "synopsis": "This episode examines whether preoperative positive suggestions influence dreaming during IV sedation.",
            "study_at_a_glance": [
                {
                    "label": "Design and setting",
                    "content": "Single-centre, double-blinded RCT (n=188).",
                },
                {
                    "label": "Primary outcome",
                    "content": "Ketamine increased dream recall (OR 2.14, 95% CI 1.23-3.72; p=0.007).",
                },
                {
                    "label": "Risk of bias and certainty",
                    "content": "RoB 2 judgment: some concerns; GRADE: moderate.",
                },
            ],
        },
    }

    output_path = tmp_path / "summary.md"
    result_path = render_podcast_to_markdown(podcast, output_path)
    content = result_path.read_text(encoding="utf-8")

    # Verify show summary rendered as plain text
    assert "Citation:" in content
    assert "Lee D, Lee H. Impact of Suggestions" in content
    assert "This episode examines" in content
    assert "Study at a glance" in content
    assert "- Design and setting: Single-centre" in content
    assert "- Primary outcome: Ketamine increased" in content
    assert "- Risk of bias and certainty: RoB 2" in content

    # Verify 3 horizontal rules (header, post-transcript, post-summary)
    assert content.count("---") == 3

    # Verify no markdown formatting in summary section
    summary_start = content.index("Citation:")
    summary_section = content[summary_start:]
    assert "**" not in summary_section.split("*Generated")[0]
    assert "# " not in summary_section.split("*Generated")[0]


def test_render_podcast_without_show_summary(tmp_path):
    """Test that missing show_summary is handled gracefully (backward compat)."""
    podcast = {
        "metadata": {"title": "No Summary Test"},
        "transcript": "Transcript without a show summary.",
    }

    output_path = tmp_path / "no-summary.md"
    result_path = render_podcast_to_markdown(podcast, output_path)
    content = result_path.read_text(encoding="utf-8")

    # Should render normally without show summary section
    assert "Transcript without a show summary." in content
    assert "Citation:" not in content
    assert "Study at a glance" not in content
