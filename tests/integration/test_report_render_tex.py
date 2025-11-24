# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Integration-lite test for LaTeX rendering (no PDF compilation).
"""

from src.rendering.latex_renderer import render_report_to_pdf


def test_render_report_writes_tex(tmp_path):
    report = {
        "layout": {"language": "en", "numbering": False},
        "sections": [
            {
                "title": "Intro",
                "blocks": [{"type": "text", "style": "paragraph", "content": ["Hello"]}],
            }
        ],
    }

    out_dir = tmp_path / "render"
    result = render_report_to_pdf(report, out_dir, compile_pdf=False)

    tex_path = result["tex"]
    assert tex_path.exists()
    assert (out_dir / "preamble.tex").exists()
    content = tex_path.read_text(encoding="utf-8")
    assert "Intro" in content
    # Numbering disabled should insert secnumdepth tweak
    assert "\\setcounter{secnumdepth}{0}" in content
