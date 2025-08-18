# run_pipeline.py
import argparse
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.table import Table

console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="AI Podcast Pipeline (PDF → JSON → Script/Shownotes/Rapport)"
    )
    parser.add_argument("pdf", help="Pad naar de PDF")
    parser.add_argument(
        "--max-pages", type=int, default=None, help="Beperk aantal pagina's (voor snelle tests)"
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        console.print(f"[red]❌ PDF niet gevonden:[/red] {pdf_path}")
        raise SystemExit(1)

    console.print(
        Panel.fit(
            "[bold white]PDFtoPodcast[/bold white]\n[dim]PDF → JSON → Appraisal → Script/Shownotes/Rapport[/dim]",
            border_style="magenta",
        )
    )

    console.print(f"[green]✅ PDF gevonden:[/green] {pdf_path}")

    # Pipeline-overzicht
    table = Table(title="Pipeline stappen", box=box.SIMPLE_HEAVY)
    table.add_column("Stap", style="cyan", no_wrap=True)
    table.add_column("Status", style="green")
    steps = [
        ("PDF inlezen", "⏳"),
        ("Extractie (JSON)", ""),
        ("Validatie (appraisal)", ""),
        ("Genereren outputs", ""),
        ("Wegschrijven", ""),
    ]
    for s, st in steps:
        table.add_row(s, st)
    console.print(table)

    # Probeer de echte pipeline te importeren
    try:
        from src.pipeline import run_pipeline  # type: ignore

        have_pipeline = True
    except Exception as e:
        have_pipeline = False
        console.print(
            Panel.fit(
                "[yellow]ℹ️ De echte pipeline-code is nog niet aanwezig of faalt bij import.[/yellow]\n"
                "Voeg de bestanden in [bold]src/[/bold] toe (pdf_io.py, llm.py, pipeline.py, etc.)\n"
                f"[dim]Details: {e}[/dim]",
                border_style="yellow",
            )
        )

    # Simpele “voortgang” animatie
    for _ in track(range(3), description="Voorbereiden..."):
        pass

    if not have_pipeline:
        console.print("[yellow]👉 Demo klaar.[/yellow] Voeg de src/ code toe en run opnieuw.")
        return

    # Run de echte pipeline met spinner
    with console.status("[bold cyan]Bezig met verwerken...[/bold cyan]", spinner="dots"):
        result = run_pipeline(str(pdf_path), max_pages=args.max_pages)

    # Toon korte samenvatting
    console.print("\n[bold green]✅ Pipeline voltooid[/bold green]")

    summary = Table(title="Samenvatting", box=box.SIMPLE)
    summary.add_column("Onderdeel", style="cyan")
    summary.add_column("Opmerking")
    try:
        title = result.get("extraction", {}).get("title", "") or "—"
        n_keys = len(result.get("extraction", {}).keys())
        summary.add_row("Titel (extractie)", title)
        summary.add_row("Velden in extractie", str(n_keys))
        summary.add_row(
            "Shownotes", "gegenereerd" if result.get("deliverables", {}).get("shownotes") else "—"
        )
        summary.add_row(
            "Podcast script",
            "gegenereerd" if result.get("deliverables", {}).get("podcast_script") else "—",
        )
        summary.add_row(
            "Rapport", "gegenereerd" if result.get("deliverables", {}).get("report") else "—"
        )
    except Exception:
        summary.add_row("Resultaat", "Beschikbaar, maar niet samengevat")

    console.print(summary)
    console.print("[dim]Bestanden zijn weggeschreven in ./out[/dim]")


if __name__ == "__main__":
    main()
