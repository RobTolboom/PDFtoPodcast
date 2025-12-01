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

import copy
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .figure_generator import FigureGenerationError, generate_figure


class LatexRenderError(RuntimeError):
    """Raised when LaTeX rendering or compilation fails."""


def _escape_latex(text: str) -> str:
    """Escape minimal LaTeX special characters."""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "[": r"{[}",
        "]": r"{]}",
        "|": r"\textbar{}",
        "<": r"\textless{}",
        ">": r"\textgreater{}",
        "*": r"\textasteriskcentered{}",
        "⊕": r"$\oplus$",  # GRADE certainty symbol
        "○": r"$\circ$",  # GRADE certainty symbol
        "≥": r"$\geq$",
        "≤": r"$\leq$",
        "α": r"$\alpha$",
        "β": r"$\beta$",
        "γ": r"$\gamma$",
        "δ": r"$\delta$",
        "ε": r"$\epsilon$",
        "θ": r"$\theta$",
        "λ": r"$\lambda$",
        "μ": r"$\mu$",
        "π": r"$\pi$",
        "σ": r"$\sigma$",
        "χ": r"$\chi$",
        "ω": r"$\omega$",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


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
    variant_titles = {
        "warning": "Warning",
        "note": "Note",
        "implication": "Implication",
        "clinical_pearl": "Clinical pearl",
    }
    variant_title = variant_titles.get(variant, variant.replace("_", " ").title())
    variant_title = _escape_latex(variant_title)
    text = _escape_latex(block.get("text", ""))
    return (
        f"\\begin{{tcolorbox}}[title={{\\textbf{{{variant_title}}}}}]\n"
        f"{text}\n"
        f"\\end{{tcolorbox}}"
    )


def _render_table_block(block: dict[str, Any]) -> str:
    columns = block.get("columns", [])
    rows = block.get("rows", [])
    headers = " & ".join(_escape_latex(col.get("header", "")) for col in columns)
    render_hints = block.get("render_hints", {})
    placement = render_hints.get("placement", "H")

    # Allow explicit table spec override
    custom_spec = render_hints.get("table_spec")

    def _build_table_spec() -> tuple[str, bool]:
        """Build column spec and decide whether to use tabularx for wrapping."""
        if custom_spec:
            return custom_spec, False

        spec_parts: list[str] = []
        use_tabularx = False
        for col in columns:
            align = col.get("align", "l")
            if align == "l":
                spec_parts.append(r">{\raggedright\arraybackslash}X")
                use_tabularx = True
            elif align == "c":
                spec_parts.append(r">{\centering\arraybackslash}X")
                use_tabularx = True
            elif align == "r":
                spec_parts.append(r">{\raggedleft\arraybackslash}X")
                use_tabularx = True
            else:
                # Pass through for numeric or custom columns (e.g., S, p{...})
                spec_parts.append(align)
        return "".join(spec_parts), use_tabularx

    table_spec, use_tabularx = _build_table_spec()
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

    table_begin = (
        f"\\begin{{tabularx}}{{\\textwidth}}{{{table_spec}}}\n"
        if use_tabularx
        else f"\\begin{{tabular}}{{{table_spec}}}\n"
    )
    table_end = "\\end{tabularx}\n" if use_tabularx else "\\end{tabular}\n"
    size_prefix = ""
    size_suffix = ""
    if len(columns) >= 4:
        # Slightly shrink wide tables to reduce overfull boxes
        size_prefix = "\\small\n"
        size_suffix = "\n\\normalsize"

    return (
        f"\\begin{{table}}[{placement}]\n"
        f"\\centering\n"
        f"{size_prefix}"
        f"{table_begin}"
        "\\toprule\n"
        f"{headers} \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        f"{table_end}"
        f"{size_suffix}"
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
        # Expect block['file'] to be set by figure generation step
        file_ref = block.get("file")
        if not file_ref:
            raise LatexRenderError("Figure block missing 'file' path after generation")
        caption = _escape_latex(block.get("caption", ""))
        render_hints = block.get("render_hints", {}) or {}
        placement = render_hints.get("placement", "tbp")
        width = render_hints.get("width")
        # Default narrower width for RoB plots unless explicitly overridden
        if block.get("figure_kind") == "rob_traffic_light":
            if not width or width in {"\\linewidth", "\\textwidth"}:
                width = "0.5\\linewidth"
        width = width or "\\linewidth"
        label = block.get("label", "")
        label_tex = f"\\label{{{label}}}" if label else ""
        return (
            f"\\begin{{figure}}[{placement}]\n"
            f"\\centering\n"
            f"\\includegraphics[width={width}]{{{file_ref}}}\n"
            f"\\caption{{{caption}}}\n"
            f"{label_tex}\n"
            f"\\end{{figure}}"
        )
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
    # Use path relative to this file to find templates
    template_dir = Path(__file__).parent.parent.parent / "templates" / "latex" / template
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
    enable_figures: bool = True,
) -> dict[str, Path]:
    """
    Render report JSON to LaTeX, optionally compile to PDF.

    Returns a dict with paths to .tex and (optionally) .pdf.
    """
    # Security check for engine
    allowed_engines = {"pdflatex", "xelatex", "lualatex"}
    if engine not in allowed_engines:
        raise ValueError(f"Invalid LaTeX engine: {engine}. Must be one of {allowed_engines}")

    output_dir.mkdir(parents=True, exist_ok=True)
    # Use path relative to this file to find templates
    template_dir = Path(__file__).parent.parent.parent / "templates" / "latex" / template
    report_copy = copy.deepcopy(report)

    from collections.abc import Iterator

    def _walk_sections(sections: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Yield all sections and subsections for figure handling."""
        stack = list(sections)
        while stack:
            sec = stack.pop()
            yield sec
            subs = sec.get("subsections") or []
            stack.extend(subs)

    # Generate figures if enabled (walk subsections too)
    if enable_figures:
        fig_dir = output_dir / "figures"
        for section in _walk_sections(report_copy.get("sections", [])):
            for block in section.get("blocks", []) or []:
                if block.get("type") == "figure" and not block.get("file"):
                    try:
                        fig_path = generate_figure(block, fig_dir)
                        # Use relative path from tex location
                        block["file"] = f"figures/{fig_path.name}"
                    except FigureGenerationError as e:
                        raise LatexRenderError(str(e)) from e
    else:
        # Strip figures everywhere to avoid LaTeX errors
        for section in _walk_sections(report_copy.get("sections", [])):
            blocks = section.get("blocks", []) or []
            section["blocks"] = [b for b in blocks if b.get("type") != "figure"]

    tex_str = render_report_to_tex(report_copy, template)

    tex_path = output_dir / "report.tex"
    tex_path.write_text(tex_str, encoding="utf-8")

    # Copy auxiliary template files (e.g., preamble.tex) so \input references resolve
    for template_file in template_dir.iterdir():
        if template_file.name == "main.tex":
            continue
        if template_file.is_file():
            shutil.copy(template_file, output_dir / template_file.name)

    result = {"tex": tex_path}

    if compile_pdf:
        if not shutil.which(engine):
            raise LatexRenderError(f"LaTeX engine '{engine}' not found in PATH")
        cmd = [engine, "-interaction=nonstopmode", tex_path.name]
        try:
            # Safe: using list args (shell=False) prevents command injection
            # tex_path.name is also safe as it comes from pathlib
            subprocess.run(cmd, cwd=output_dir, check=True, capture_output=True)
            result["pdf"] = output_dir / "report.pdf"
        except subprocess.CalledProcessError as exc:
            raise LatexRenderError(
                f"LaTeX compilation failed: {exc.stderr.decode('utf-8', 'ignore')}"
            ) from exc

    return result
