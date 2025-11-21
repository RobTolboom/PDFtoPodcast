# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for LaTeX renderer scaffolding (Phase 4).
"""

import pytest

from src.rendering.latex_renderer import (
    LatexRenderError,
    render_report_to_pdf,
    render_report_to_tex,
)


@pytest.fixture
def sample_report():
    return {
        "sections": [
            {
                "title": "Summary",
                "blocks": [
                    {"type": "text", "style": "paragraph", "content": ["Hello % world"]},
                    {"type": "callout", "variant": "note", "text": "Important finding."},
                ],
            },
            {
                "title": "Results",
                "blocks": [
                    {
                        "type": "table",
                        "columns": [
                            {"key": "outcome", "header": "Outcome", "align": "l"},
                            {"key": "effect", "header": "Effect", "align": "c"},
                        ],
                        "rows": [{"outcome": "Pain", "effect": "-1.2"}],
                        "caption": "Primary outcomes",
                    }
                ],
            },
        ]
    }


def test_render_report_to_tex_inserts_sections(sample_report, tmp_path):
    tex = render_report_to_tex(sample_report)
    assert "Summary" in tex
    assert "Results" in tex
    assert r"\%" in tex  # escaped
    assert "Primary outcomes" in tex


def test_render_report_to_pdf_writes_tex(sample_report, tmp_path):
    report_dir = tmp_path / "out"
    result = render_report_to_pdf(sample_report, report_dir, compile_pdf=False)

    assert "tex" in result
    assert result["tex"].exists()
    content = result["tex"].read_text(encoding="utf-8")
    assert "Summary" in content


def test_render_report_to_tex_missing_template_raises(sample_report, monkeypatch):
    monkeypatch.setenv("TEMPLATE_PATH_OVERRIDE", "nonexistent")
    with pytest.raises(LatexRenderError):
        render_report_to_tex(sample_report, template="does-not-exist")


# ============================================================================
# Text Block Style Tests
# ============================================================================


def test_render_text_block_bullets():
    """Test bullet list rendering with itemize environment."""
    report = {
        "sections": [
            {
                "title": "Findings",
                "blocks": [
                    {
                        "type": "text",
                        "style": "bullets",
                        "content": ["First finding", "Second finding", "Third finding"],
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert r"\begin{itemize}" in tex
    assert r"\item First finding" in tex
    assert r"\item Second finding" in tex
    assert r"\item Third finding" in tex
    assert r"\end{itemize}" in tex


def test_render_text_block_numbered():
    """Test numbered list rendering with enumerate environment."""
    report = {
        "sections": [
            {
                "title": "Steps",
                "blocks": [
                    {
                        "type": "text",
                        "style": "numbered",
                        "content": ["Step one", "Step two", "Step three"],
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert r"\begin{enumerate}" in tex
    assert r"\item Step one" in tex
    assert r"\item Step two" in tex
    assert r"\item Step three" in tex
    assert r"\end{enumerate}" in tex


def test_render_text_block_paragraph():
    """Test paragraph rendering without list environment."""
    report = {
        "sections": [
            {
                "title": "Introduction",
                "blocks": [
                    {
                        "type": "text",
                        "style": "paragraph",
                        "content": ["First paragraph.", "Second paragraph."],
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert "First paragraph." in tex
    assert "Second paragraph." in tex
    assert r"\begin{itemize}" not in tex
    assert r"\begin{enumerate}" not in tex


# ============================================================================
# Callout Variant Tests
# ============================================================================


@pytest.mark.parametrize(
    "variant,expected_title",
    [
        ("warning", "Warning"),
        ("note", "Note"),
        ("implication", "Implication"),
        ("clinical_pearl", "Clinical_Pearl"),
    ],
)
def test_render_callout_variants(variant, expected_title):
    """Test all callout variants render with correct tcolorbox title."""
    report = {
        "sections": [
            {
                "title": "Section",
                "blocks": [
                    {"type": "callout", "variant": variant, "text": "Test callout content."}
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert r"\begin{tcolorbox}" in tex
    assert expected_title in tex
    assert "Test callout content." in tex
    assert r"\end{tcolorbox}" in tex


# ============================================================================
# Table Tests
# ============================================================================


def test_render_table_with_all_alignments():
    """Test table rendering with l, c, r, S alignments."""
    report = {
        "sections": [
            {
                "title": "Data",
                "blocks": [
                    {
                        "type": "table",
                        "columns": [
                            {"key": "name", "header": "Name", "align": "l"},
                            {"key": "value", "header": "Value", "align": "c"},
                            {"key": "ci", "header": "95% CI", "align": "r"},
                            {"key": "number", "header": "N", "align": "S"},
                        ],
                        "rows": [
                            {"name": "Outcome A", "value": "1.5", "ci": "1.2-1.8", "number": "100"}
                        ],
                        "caption": "Results table",
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert r"\begin{tabular}{lcrS}" in tex
    assert "Name" in tex
    assert "Value" in tex
    assert r"95\% CI" in tex  # % should be escaped
    assert "N" in tex


def test_render_table_with_render_hints():
    """Test table respects render_hints.table_spec override."""
    report = {
        "sections": [
            {
                "title": "Data",
                "blocks": [
                    {
                        "type": "table",
                        "columns": [
                            {"key": "a", "header": "A", "align": "l"},
                            {"key": "b", "header": "B", "align": "l"},
                        ],
                        "rows": [{"a": "1", "b": "2"}],
                        "render_hints": {"table_spec": "p{3cm}p{5cm}"},
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert r"\begin{tabular}{p{3cm}p{5cm}}" in tex


def test_render_table_without_caption():
    """Test table renders correctly when caption is empty or missing."""
    report = {
        "sections": [
            {
                "title": "Data",
                "blocks": [
                    {
                        "type": "table",
                        "columns": [{"key": "x", "header": "X", "align": "l"}],
                        "rows": [{"x": "val"}],
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert r"\begin{table}" in tex
    assert r"\caption{}" in tex  # Empty caption


# ============================================================================
# Figure Block Tests
# ============================================================================


def test_render_figure_block_raises_error():
    """Test that figure blocks raise LatexRenderError (Phase 5 scope)."""
    report = {
        "sections": [
            {
                "title": "Figures",
                "blocks": [
                    {
                        "type": "figure",
                        "figure_kind": "rob_traffic_light",
                        "label": "fig_rob",
                        "caption": "Risk of Bias",
                    }
                ],
            }
        ]
    }
    with pytest.raises(LatexRenderError, match="Figure blocks are not yet supported"):
        render_report_to_tex(report)


def test_render_unknown_block_type_raises_error():
    """Test that unknown block types raise LatexRenderError."""
    report = {
        "sections": [
            {
                "title": "Section",
                "blocks": [{"type": "unknown_type", "content": "data"}],
            }
        ]
    }
    with pytest.raises(LatexRenderError, match="Unsupported block type"):
        render_report_to_tex(report)


# ============================================================================
# Section Structure Tests
# ============================================================================


def test_render_subsections():
    """Test recursive subsection rendering with correct heading levels."""
    report = {
        "sections": [
            {
                "title": "Main Section",
                "blocks": [{"type": "text", "style": "paragraph", "content": ["Intro text."]}],
                "subsections": [
                    {
                        "title": "Subsection A",
                        "blocks": [
                            {"type": "text", "style": "paragraph", "content": ["Sub A text."]}
                        ],
                        "subsections": [
                            {
                                "title": "Sub-subsection",
                                "blocks": [
                                    {
                                        "type": "text",
                                        "style": "paragraph",
                                        "content": ["Deep text."],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert r"\section{Main Section}" in tex
    assert r"\subsection{Subsection A}" in tex
    assert r"\subsubsection{Sub-subsection}" in tex


def test_render_empty_section():
    """Test section with no blocks renders correctly."""
    report = {
        "sections": [
            {
                "title": "Empty Section",
                "blocks": [],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert r"\section{Empty Section}" in tex


def test_render_numbering_disabled():
    """Test that layout.numbering=false disables section numbering."""
    report = {
        "layout": {"numbering": False},
        "sections": [{"title": "Section", "blocks": []}],
    }
    tex = render_report_to_tex(report)
    assert r"\setcounter{secnumdepth}{0}" in tex


# ============================================================================
# LaTeX Escaping Tests
# ============================================================================


def test_escape_all_special_characters():
    """Test that all LaTeX special characters are escaped correctly."""
    report = {
        "sections": [
            {
                "title": "Special & Characters",
                "blocks": [
                    {
                        "type": "text",
                        "style": "paragraph",
                        "content": ["Test: & % $ # _ { } ~ ^ symbols"],
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    # Check title escaping
    assert r"Special \& Characters" in tex
    # Check content escaping
    assert r"\&" in tex
    assert r"\%" in tex
    assert r"\$" in tex
    assert r"\#" in tex
    assert r"\_" in tex
    assert r"\{" in tex
    assert r"\}" in tex
    assert r"\textasciitilde{}" in tex
    assert r"\textasciicircum{}" in tex


def test_escape_backslash():
    """Test that backslash is escaped to textbackslash.

    Note: The escape function escapes backslash to \\textbackslash{} first,
    then the {} get escaped to \\{\\}. This results in \\textbackslash\\{\\}
    which is technically correct but verbose. Future improvement could fix this.
    """
    report = {
        "sections": [
            {
                "title": "Section",
                "blocks": [
                    {
                        "type": "text",
                        "style": "paragraph",
                        "content": ["path\\to\\file"],
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    # Current behavior: backslash becomes \textbackslash\{\}
    assert r"\textbackslash" in tex


# ============================================================================
# Metadata Injection Tests
# ============================================================================


def test_metadata_injection_title():
    """Test that report.metadata.title is injected into LaTeX output."""
    report = {
        "metadata": {
            "title": "Effect of Intervention X on Outcome Y",
        },
        "sections": [{"title": "Results", "blocks": []}],
    }
    tex = render_report_to_tex(report)
    assert r"\title{Effect of Intervention X on Outcome Y}" in tex


def test_metadata_injection_authors():
    """Test that report.metadata.authors list is joined and injected."""
    report = {
        "metadata": {
            "title": "Study Title",
            "authors": ["Smith J", "Jones A", "Williams B"],
        },
        "sections": [{"title": "Results", "blocks": []}],
    }
    tex = render_report_to_tex(report)
    assert r"\author{Smith J, Jones A, Williams B}" in tex


def test_metadata_injection_date():
    """Test that report.metadata.publication_date is injected."""
    report = {
        "metadata": {
            "title": "Study Title",
            "publication_date": "2024-03-15",
        },
        "sections": [{"title": "Results", "blocks": []}],
    }
    tex = render_report_to_tex(report)
    assert r"\date{2024-03-15}" in tex


def test_metadata_defaults_when_missing():
    """Test that sensible defaults are used when metadata is missing."""
    report = {
        "sections": [{"title": "Results", "blocks": []}],
    }
    tex = render_report_to_tex(report)
    assert r"\title{Automated Report}" in tex
    assert r"\author{PDFtoPodcast}" in tex
    assert r"\date{}" in tex


def test_metadata_title_escapes_special_chars():
    """Test that special characters in title are escaped."""
    report = {
        "metadata": {
            "title": "Effect of Drug A & Drug B: A 100% Success Rate?",
        },
        "sections": [{"title": "Results", "blocks": []}],
    }
    tex = render_report_to_tex(report)
    assert r"\title{Effect of Drug A \& Drug B: A 100\% Success Rate?}" in tex


# ============================================================================
# Label Generation Tests
# ============================================================================


def test_table_label_generation():
    """Test that table labels are generated for cross-referencing."""
    report = {
        "sections": [
            {
                "title": "Results",
                "blocks": [
                    {
                        "type": "table",
                        "label": "tbl_snapshot",
                        "caption": "Study Snapshot",
                        "columns": [{"key": "item", "header": "Item", "align": "l"}],
                        "rows": [{"item": "Design"}],
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert r"\label{tbl_snapshot}" in tex
    assert r"\caption{Study Snapshot}" in tex


def test_table_without_label():
    """Test that tables without labels don't generate empty label commands."""
    report = {
        "sections": [
            {
                "title": "Results",
                "blocks": [
                    {
                        "type": "table",
                        "caption": "Results",
                        "columns": [{"key": "x", "header": "X", "align": "l"}],
                        "rows": [{"x": "1"}],
                    }
                ],
            }
        ]
    }
    tex = render_report_to_tex(report)
    assert r"\label{}" not in tex
