"""
HTML → PDF renderer using WeasyPrint (optional alternative to LaTeX).

Scope: basic support for text, table, callout, and figure blocks.
Figures must have 'file' set to an image path (PNG).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .figure_generator import FigureGenerationError, generate_figure


class WeasyRendererError(RuntimeError):
    """Raised when WeasyPrint rendering fails or dependency missing."""


def _import_weasyprint():
    try:
        from weasyprint import HTML  # type: ignore
    except Exception as e:
        raise WeasyRendererError(
            "WeasyPrint is not installed. Install with 'pip install weasyprint[lxml]'"
        ) from e
    return HTML


def _escape_html(text: str) -> str:
    import html

    return html.escape(text)


def _render_block(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if block_type == "text":
        style = block.get("style", "paragraph")
        content = block.get("content", [])
        if style == "bullets":
            items = "".join(f"<li>{_escape_html(c)}</li>" for c in content)
            return f"<ul>{items}</ul>"
        if style == "numbered":
            items = "".join(f"<li>{_escape_html(c)}</li>" for c in content)
            return f"<ol>{items}</ol>"
        return "".join(f"<p>{_escape_html(c)}</p>" for c in content)
    if block_type == "callout":
        variant = block.get("variant", "note")
        text = _escape_html(block.get("text", ""))
        return f'<div class="callout {variant}">{text}</div>'
    if block_type == "table":
        columns = block.get("columns", [])
        rows = block.get("rows", [])
        headers = "".join(f"<th>{_escape_html(col.get('header',''))}</th>" for col in columns)
        body_rows = []
        for row in rows:
            cells = []
            for col in columns:
                val = row.get(col.get("key", ""), "")
                cells.append(f"<td>{_escape_html(str(val))}</td>")
            body_rows.append(f"<tr>{''.join(cells)}</tr>")
        body_html = "".join(body_rows)
        caption = _escape_html(block.get("caption", "")) if block.get("caption") else ""
        caption_html = f"<caption>{caption}</caption>" if caption else ""
        return (
            f"<table class='report-table'>{caption_html}<thead><tr>{headers}</tr></thead>"
            f"<tbody>{body_html}</tbody></table>"
        )
    if block_type == "figure":
        file_ref = block.get("file")
        if not file_ref:
            raise WeasyRendererError("Figure block missing 'file' path")
        caption = _escape_html(block.get("caption", ""))
        label = _escape_html(block.get("label", ""))
        return (
            "<figure>"
            f"<img src='{file_ref}' alt='{caption}' />"
            f"<figcaption>{caption} {label}</figcaption>"
            "</figure>"
        )
    raise WeasyRendererError(f"Unsupported block type for WeasyPrint: {block_type}")


def _render_section(section: dict[str, Any]) -> str:
    title = _escape_html(section.get("title", ""))
    blocks_html = []
    for block in section.get("blocks", []):
        blocks_html.append(_render_block(block))
    for subsection in section.get("subsections", []) or []:
        blocks_html.append(_render_section(subsection))
    body = "".join(blocks_html)
    return f"<section><h2>{title}</h2>{body}</section>"


def render_report_to_html(report: dict[str, Any]) -> str:
    sections_html = "".join(_render_section(s) for s in report.get("sections", []))
    language = report.get("layout", {}).get("language", "en")
    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="utf-8"/>
<style>
body {{ font-family: sans-serif; margin: 32px; }}
h1,h2,h3 {{ color: #222; }}
table.report-table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
table.report-table th, table.report-table td {{ border: 1px solid #ccc; padding: 6px; font-size: 12px; }}
table.report-table caption {{ font-weight: bold; margin-bottom: 4px; }}
.callout {{ border-left: 4px solid #999; padding: 8px 12px; margin: 8px 0; background: #f8f8f8; }}
.callout.warning {{ border-color: #d9534f; }}
.callout.note {{ border-color: #0275d8; }}
.callout.implication {{ border-color: #5cb85c; }}
</style>
</head>
<body>
<h1>{_escape_html(report.get('metadata', {}).get('title', 'Report'))}</h1>
{sections_html}
</body>
</html>"""


def render_report_with_weasyprint(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    """
    Render report JSON to HTML and PDF using WeasyPrint.

    Returns dict with 'html' and 'pdf' paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate figures first
    from collections.abc import Iterator

    def _walk_sections(sections: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Yield all sections and subsections for figure handling."""
        stack = list(sections)
        while stack:
            section = stack.pop(0)
            yield section
            # Add subsections to stack
            if "subsections" in section:
                stack.extend(section["subsections"])

    # Walk through all sections to find and generate figures
    for section in _walk_sections(report.get("sections", [])):
        for block in section.get("blocks", []):
            if block.get("type") == "figure":
                # If file path is missing, generate it
                if not block.get("file"):
                    try:
                        # Generate figure using shared figure generator
                        # This will create the file in output_dir/figures
                        fig_path = generate_figure(block, output_dir)
                        # Update block with absolute path to generated file
                        block["file"] = str(fig_path)
                    except FigureGenerationError as e:
                        # Log error but continue (will likely fail rendering or show broken image)
                        print(f"Failed to generate figure: {e}")
                        # Don't raise here, let renderer handle missing file or skip

    html_str = render_report_to_html(report)
    html_path = output_dir / "report.html"
    html_path.write_text(html_str, encoding="utf-8")

    HTML = _import_weasyprint()
    try:
        pdf_path = output_dir / "report.pdf"
        HTML(string=html_str, base_url=str(output_dir)).write_pdf(str(pdf_path))
    except Exception as e:
        raise WeasyRendererError(f"WeasyPrint failed: {e}") from e

    return {"html": html_path, "pdf": pdf_path}
