import argparse
import json
from pathlib import Path

from rich.console import Console

from src.rendering.latex_renderer import LatexRenderError, render_report_to_pdf
from src.rendering.markdown_renderer import render_report_to_markdown
from src.rendering.weasy_renderer import WeasyRendererError, render_report_with_weasyprint

console = Console()


def _load_json_if_exists(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _figure_data_from_extraction(extraction: dict | None) -> dict:
    """Prepare figure data payloads from extraction JSON."""
    if not extraction:
        return {}
    data: dict[str, dict] = {}

    # CONSORT flow mapping from figures_summary key_values
    summaries = extraction.get("figures_summary") or []
    if summaries:
        kv = summaries[0].get("key_values", {})
        n_screened = kv.get("assessed_eligibility")
        n_randomised = kv.get("randomised")
        n_excluded_screening = kv.get("excluded_screening")
        if n_excluded_screening is None and n_screened is not None and n_randomised is not None:
            try:
                n_excluded_screening = max(int(n_screened) - int(n_randomised), 0)
            except Exception:
                n_excluded_screening = None

        def _arm(label_key: str, pretty: str) -> dict:
            return {
                "label": pretty,
                "n_assigned": kv.get(f"allocated_{label_key}")
                or kv.get(f"received_{label_key}")
                or kv.get(f"{label_key}_assigned"),
                "n_analysed": kv.get(f"analysed_itt_{label_key}")
                or kv.get(f"per_protocol_{label_key}")
                or kv.get(f"{label_key}_analysed"),
            }

        arms = []
        arms.append(_arm("esketamine", "Esketamine"))
        arms.append(_arm("placebo", "Placebo"))

        data["consort"] = {
            "n_screened": n_screened,
            "n_excluded_screening": n_excluded_screening,
            "n_randomised": n_randomised,
            "arms": arms,
        }

    return data


def _figure_data_from_appraisal(appraisal: dict | None) -> dict:
    if not appraisal:
        return {}
    data: dict[str, dict] = {}
    rob = appraisal.get("risk_of_bias")
    if rob:
        domains = rob.get("domains") or []
        data["rob_traffic_light"] = {
            "domains": [d.get("domain", "") for d in domains],
            "judgements": [d.get("judgement", "") for d in domains],
        }
    return data


def _hydrate_figure_blocks(report: dict, base_dir: Path, prefix: str) -> dict:
    """Resolve figure data for blocks that only declare data_ref."""
    extraction = None
    appraisal = None

    def _first_existing(suffixes: list[str]) -> Path | None:
        for suf in suffixes:
            candidate = base_dir / f"{prefix}-{suf}.json"
            if candidate.exists():
                return candidate
        return None

    extraction_path = _first_existing(["extraction-best", "extraction", "extraction0"])
    appraisal_path = _first_existing(["appraisal-best", "appraisal", "appraisal0"])

    if extraction_path:
        extraction = _load_json_if_exists(extraction_path)
    if appraisal_path:
        appraisal = _load_json_if_exists(appraisal_path)

    fig_data = {}
    fig_data.update(_figure_data_from_extraction(extraction))
    fig_data.update(_figure_data_from_appraisal(appraisal))

    def _maybe_set_data(block: dict) -> None:
        if block.get("type") != "figure" or block.get("data") is not None:
            return
        kind = block.get("figure_kind")
        if kind in fig_data:
            block["data"] = fig_data[kind]

    for section in report.get("sections", []):
        for block in section.get("blocks", []) or []:
            _maybe_set_data(block)
        for subsection in section.get("subsections", []) or []:
            for block in subsection.get("blocks", []) or []:
                _maybe_set_data(block)

    return report


def render_report(
    report_path: Path, output_dir: Path, renderer: str, compile_pdf: bool, enable_figures: bool
) -> None:
    report = json.loads(report_path.read_text())
    output_dir.mkdir(parents=True, exist_ok=True)

    # Attach figure data from companion extraction/appraisal files if present
    prefix = report_path.stem.split("-report", 1)[0]
    report = _hydrate_figure_blocks(report, report_path.parent, prefix)

    render_dirs: dict[str, Path] = {}
    try:
        if renderer == "weasyprint":
            render_dirs = render_report_with_weasyprint(report, output_dir)
        else:
            render_dirs = render_report_to_pdf(
                report,
                output_dir,
                compile_pdf=compile_pdf,
                enable_figures=enable_figures,
            )
        console.print(f"[green]✓ Rendered with {renderer}: {render_dirs}[/green]")
    except (LatexRenderError, WeasyRendererError) as e:
        console.print(f"[yellow]⚠️ Render error with {renderer}: {e}[/yellow]")
    except Exception as e:  # pragma: no cover - defensive
        console.print(f"[red]Unexpected render error: {e}[/red]")

    try:
        md_path = render_report_to_markdown(report, output_dir)
        render_dirs["markdown"] = md_path
        # Also write a root-level copy next to the JSON for convenience
        root_md = report_path.parent / f"{report_path.stem}.md"
        root_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
        render_dirs["markdown_root"] = root_md
        console.print(f"[green]✓ Markdown written: {md_path}[/green]")
        console.print(f"[green]✓ Markdown copy: {root_md}[/green]")
    except Exception as e:  # pragma: no cover - defensive
        console.print(f"[yellow]⚠️ Failed to write markdown: {e}[/yellow]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render an existing report JSON to PDF/HTML/Markdown without LLM calls.",
    )
    parser.add_argument("report_json", type=Path, help="Path to report-best.json (or iteration)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/render"),
        help="Directory to write render outputs (default: tmp/render)",
    )
    parser.add_argument(
        "--renderer",
        choices=["latex", "weasyprint"],
        default="latex",
        help="Renderer to use (default: latex)",
    )
    parser.add_argument(
        "--no-compile-pdf",
        dest="compile_pdf",
        action="store_false",
        help="Skip PDF compilation (still writes .tex)",
    )
    parser.set_defaults(compile_pdf=True)
    parser.add_argument(
        "--disable-figures",
        dest="enable_figures",
        action="store_false",
        help="Skip figure generation (drops figure blocks)",
    )
    parser.set_defaults(enable_figures=True)

    args = parser.parse_args()

    if not args.report_json.exists():
        console.print(f"[red]Report JSON not found: {args.report_json}[/red]")
        raise SystemExit(1)

    render_report(
        report_path=args.report_json,
        output_dir=args.output_dir,
        renderer=args.renderer,
        compile_pdf=args.compile_pdf,
        enable_figures=args.enable_figures,
    )


if __name__ == "__main__":
    main()
