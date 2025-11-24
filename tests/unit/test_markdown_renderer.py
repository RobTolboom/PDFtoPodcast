# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for markdown renderer fallback.
"""

from src.rendering.markdown_renderer import render_report_to_markdown


def test_render_report_to_markdown(tmp_path):
    report = {
        "metadata": {"title": "Test Report"},
        "sections": [
            {
                "title": "Intro",
                "blocks": [
                    {"type": "text", "style": "paragraph", "content": ["Hello *world*"]},
                    {"type": "callout", "variant": "note", "text": "Important."},
                    {
                        "type": "table",
                        "columns": [
                            {"key": "col1", "header": "Col1", "align": "l"},
                            {"key": "col2", "header": "Col2", "align": "l"},
                        ],
                        "rows": [{"col1": "A", "col2": "B"}],
                        "caption": "Sample",
                    },
                    {"type": "figure", "file": "figures/foo.png", "caption": "Foo"},
                ],
            }
        ],
    }

    md_path = render_report_to_markdown(report, tmp_path / "render")
    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "# Test Report" in content
    assert "Hello \\*world\\*" in content
    assert "![Foo](figures/foo.png)" in content
