"""
Markdown renderer for report JSON (fallback when PDF/LaTeX fail).

Supports text, table, callout, and figure blocks by producing markdown with
tables and image references. Figures must have 'file' set; otherwise they are skipped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _escape_md(text: str) -> str:
    # Minimal escaping for markdown
    for ch in ["*", "_", "`"]:
        text = text.replace(ch, f"\\{ch}")
    return text


def _render_block(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if block_type == "text":
        style = block.get("style", "paragraph")
        content = block.get("content", [])
        if style == "bullets":
            return "\n".join(f"- {_escape_md(c)}" for c in content) + "\n"
        if style == "numbered":
            return "\n".join(f"1. {_escape_md(c)}" for c in content) + "\n"
        return "\n\n".join(_escape_md(c) for c in content) + "\n"
    if block_type == "callout":
        variant = block.get("variant", "note").upper()
        text = _escape_md(block.get("text", ""))
        return f"> **{variant}:** {text}\n"
    if block_type == "table":
        columns = block.get("columns", [])
        rows = block.get("rows", [])
        headers = " | ".join(_escape_md(col.get("header", "")) for col in columns)
        separator = " | ".join("---" for _ in columns)
        body_lines = []
        for row in rows:
            cells = []
            for col in columns:
                val = row.get(col.get("key", ""), "")
                cells.append(_escape_md(str(val)))
            body_lines.append(" | ".join(cells))
        body = "\n".join(body_lines)
        caption = block.get("caption", "")
        caption_md = f"\n*{_escape_md(caption)}*\n" if caption else "\n"
        return f"{headers}\n{separator}\n{body}{caption_md}"
    if block_type == "figure":
        file_ref = block.get("file")
        caption = _escape_md(block.get("caption", ""))
        if not file_ref:
            return ""
        return f"![{caption}]({file_ref})\n"
    return ""


def _render_section(section: dict[str, Any], depth: int = 1) -> str:
    hashes = "#" * min(depth, 6)
    title = _escape_md(section.get("title", ""))
    parts = [f"{hashes} {title}"]
    for block in section.get("blocks", []):
        parts.append(_render_block(block))
    for subsection in section.get("subsections", []) or []:
        parts.append(_render_section(subsection, depth + 1))
    return "\n".join(parts)


def render_report_to_markdown(report: dict[str, Any], output_dir: Path) -> Path:
    """
    Render report JSON to Markdown and save as report.md in output_dir.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    md_parts = []
    title = report.get("metadata", {}).get("title", "Report")
    md_parts.append(f"# {_escape_md(title)}\n")
    for section in report.get("sections", []):
        md_parts.append(_render_section(section))
    md_content = "\n\n".join(md_parts)
    md_path = output_dir / "report.md"
    md_path.write_text(md_content, encoding="utf-8")
    return md_path
