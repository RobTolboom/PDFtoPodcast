"""
Lightweight LaTeX renderer for structured report JSON (Phase 4 scaffolding).

Current scope:
- Render text, callout, and table blocks into LaTeX strings
- Assemble sections recursively
- Produce a .tex file and optionally trigger PDF compilation (off by default)

This keeps dependencies minimal and is safe for unit tests without requiring a LaTeX
runtime. Future phases can extend block coverage (figures), template features,
and full PDF compilation in CI/production environments.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


class LatexRenderError(RuntimeError):
    """Raised when LaTeX rendering or compilation fails."""


def _escape_latex(text: str) -> str:
    """Escape minimal LaTeX special characters."""
    # Order matters: escape backslash first so subsequent escapes are preserved.
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _render_text_block(block: dict[str, Any]) -> str:
    style = block.get("style", "paragraph")
    content = block.get("content", [])
    if style == "bullets":
        items = "\n".join(f"\\item {_escape_latex(line)}" for line in content)
        return f"\\begin{{itemize}}\n{items}\n\\end{{itemize}}"
    if style == "numbered":
        items = "\n".join(f"\\item {_escape_latex(line)}" for line in content)
        return f"\\begin{{enumerate}}\n{items}\n\\end{{enumerate}}"
    # paragraph fallback
    return "\n\n".join(_escape_latex(line) for line in content)


def _render_callout_block(block: dict[str, Any]) -> str:
    variant = block.get("variant", "note")
    text = _escape_latex(block.get("text", ""))
    return (
        f"\\begin{{tcolorbox}}[title={{\\textbf{{{variant.title()}}}}}]\n"
        f"{text}\n"
        f"\\end{{tcolorbox}}"
    )


def _render_table_block(block: dict[str, Any]) -> str:
    columns = block.get("columns", [])
    rows = block.get("rows", [])
    headers = " & ".join(_escape_latex(col.get("header", "")) for col in columns)
    table_spec = block.get("render_hints", {}).get(
        "table_spec", "".join(col.get("align", "l") for col in columns)
    )
    body_lines: list[str] = []
    for row in rows:
        cells = []
        for col in columns:
            val = row.get(col.get("key", ""), "")
            cells.append(_escape_latex(str(val)))
        body_lines.append(" & ".join(cells) + r" \\")
    body = "\n".join(body_lines)
    caption = _escape_latex(block.get("caption", "")) if block.get("caption") else ""

    # Generate label if present (for cross-referencing)
    label = block.get("label", "")
    label_line = f"\\label{{{label}}}\n" if label else ""

    return (
        "\\begin{table}[tbp]\n"
        f"\\centering\n"
        f"\\begin{{tabular}}{{{table_spec}}}\n"
        "\\toprule\n"
        f"{headers} \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        f"\\caption{{{caption}}}\n"
        f"{label_line}"
        "\\end{table}"
    )


def _render_block(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if block_type == "text":
        return _render_text_block(block)
    if block_type == "callout":
        return _render_callout_block(block)
    if block_type == "table":
        return _render_table_block(block)
    if block_type == "figure":
        raise LatexRenderError("Figure blocks are not yet supported in Phase 4")
    raise LatexRenderError(f"Unsupported block type: {block_type}")


def _render_section(section: dict[str, Any], depth: int = 1) -> str:
    title = _escape_latex(section.get("title", ""))
    heading_cmd = {1: "\\section", 2: "\\subsection", 3: "\\subsubsection"}.get(
        depth, "\\paragraph"
    )
    rendered_blocks = []
    for block in section.get("blocks", []):
        rendered_blocks.append(_render_block(block))
    for subsection in section.get("subsections", []) or []:
        rendered_blocks.append(_render_section(subsection, depth + 1))
    body = "\n\n".join(rendered_blocks)
    return f"{heading_cmd}{{{title}}}\n{body}"


def render_report_to_tex(report: dict[str, Any], template: str = "vetrix") -> str:
    """Render report JSON to a LaTeX document string."""
    template_dir = Path("templates/latex") / template
    main_tex = template_dir / "main.tex"
    if not main_tex.exists():
        raise LatexRenderError(f"Template not found: {main_tex}")

    # Render sections recursively
    sections_tex = []
    for section in report.get("sections", []):
        sections_tex.append(_render_section(section))
    rendered_sections = "\n\n".join(sections_tex)

    main_content = main_tex.read_text(encoding="utf-8")

    # Handle numbering toggle from layout if present
    numbering = report.get("layout", {}).get("numbering", True)
    if not numbering:
        main_content = main_content.replace(
            "\\begin{document}",
            "\\setcounter{secnumdepth}{0}\n\\begin{document}",
            1,
        )

    # Inject metadata from report.metadata
    metadata = report.get("metadata", {})
    title = _escape_latex(metadata.get("title", "Automated Report"))
    authors_list = metadata.get("authors", [])
    if authors_list:
        authors = _escape_latex(", ".join(authors_list))
    else:
        authors = "PDFtoPodcast"
    pub_date = metadata.get("publication_date", "")

    main_content = main_content.replace("{{TITLE}}", title)
    main_content = main_content.replace("{{AUTHORS}}", authors)
    main_content = main_content.replace("{{DATE}}", pub_date)

    return main_content.replace("{{SECTIONS}}", rendered_sections)


def render_report_to_pdf(
    report: dict[str, Any],
    output_dir: Path,
    template: str = "vetrix",
    engine: str = "xelatex",
    compile_pdf: bool = True,
) -> dict[str, Path]:
    """
    Render report JSON to LaTeX, optionally compile to PDF.

    Returns a dict with paths to .tex and (optionally) .pdf.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    tex_str = render_report_to_tex(report, template)

    tex_path = output_dir / "report.tex"
    tex_path.write_text(tex_str, encoding="utf-8")

    result = {"tex": tex_path}

    if compile_pdf:
        if not shutil.which(engine):
            raise LatexRenderError(f"LaTeX engine '{engine}' not found in PATH")
        cmd = [engine, "-interaction=nonstopmode", tex_path.name]
        try:
            subprocess.run(cmd, cwd=output_dir, check=True, capture_output=True)
            result["pdf"] = output_dir / "report.pdf"
        except subprocess.CalledProcessError as exc:
            raise LatexRenderError(
                f"LaTeX compilation failed: {exc.stderr.decode('utf-8', 'ignore')}"
            ) from exc

    return result
