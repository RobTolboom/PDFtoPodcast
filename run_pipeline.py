# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

# run_pipeline.py
"""
Four-step PDF extraction pipeline with direct PDF upload and schema-based validation.

Pipeline Steps:
    1. Classification - Identify publication type and extract metadata via PDF upload
    2. Extraction - Schema-based structured data extraction via PDF upload
    3. Validation - Dual validation (schema + LLM semantic via PDF upload)
    4. Correction - Fix issues identified during validation via PDF upload

PDF Upload Strategy:
    All LLM steps use direct PDF upload (no text extraction) to preserve:
    - Tables and figures (critical for medical research data)
    - Images and charts (visual data representation)
    - Complex formatting and layout information
    - Complete document structure and context

    Cost: ~1,500-3,000 tokens per page (3-6x more than text extraction)
    Benefit: Complete data fidelity - no loss of tables, images, or formatting

    Both OpenAI (GPT-5 vision) and Claude (document API) support PDF upload:
    - 100 page limit, 32 MB file size limit
    - Base64-encoded PDFs sent directly to LLM
    - Vision models analyze both text and visual content

Validation Strategy:
    The pipeline uses a two-tier validation approach:

    Step 3a: Schema Validation (Fast & Cheap)
        - Validates JSON structure against JSON schema
        - Checks types, required fields, constraints
        - Calculates quality score (schema compliance + completeness)
        - Runs in milliseconds, no API cost
        - Catches ~80% of errors (structural issues)

    Step 3b: LLM Semantic Validation (Slow & Expensive) [CONDITIONAL]
        - Only runs if schema quality score >= 50% (configurable)
        - Verifies content accuracy against source PDF via PDF upload
        - Checks medical/domain plausibility
        - Identifies subtle semantic errors
        - Catches ~20% of errors (content issues)

    Why both?
        - Schema validation filters out broken extractions before expensive LLM call
        - LLM validation catches subtle errors schema can't detect
        - Cost-effective: only pay for LLM when extraction has decent structure
        - Best of both worlds: structural + semantic validation

Configuration:
    SCHEMA_QUALITY_THRESHOLD: Minimum score to trigger LLM validation (default: 0.5)
"""

import argparse
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Import pipeline functionality
try:
    from src.pipeline import run_four_step_pipeline

    HAVE_LLM_SUPPORT = True
except ImportError as e:
    console = Console()
    console.print(f"[yellow]⚠️ LLM modules niet beschikbaar: {e}[/yellow]")
    HAVE_LLM_SUPPORT = False

console = Console()

# 🔍 TESTING BREAKPOINT CONFIGURATION
# Set to the step where you want to pause for inspection:
# Options: "classification", "extraction", "validation", "correction", None (run full pipeline)
BREAKPOINT_AFTER_STEP = None  # Change this to move breakpoint


def main():
    parser = argparse.ArgumentParser(
        description="AI Podcast Pipeline (PDF → Classification → Extraction → Validation → Outputs)"
    )
    parser.add_argument("pdf", help="Pad naar de PDF")
    parser.add_argument(
        "--max-pages", type=int, default=None, help="Beperk aantal pagina's (voor snelle tests)"
    )
    parser.add_argument(
        "--keep-tmp", action="store_true", help="Bewaar tussenbestanden in tmp/ directory"
    )
    parser.add_argument(
        "--llm-provider",
        choices=["openai", "claude"],
        default="openai",
        help="Kies LLM provider (standaard: openai)",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        console.print(f"[red]❌ PDF niet gevonden:[/red] {pdf_path}")
        raise SystemExit(1)

    console.print(
        Panel.fit(
            "[bold white]PDFtoPodcast[/bold white]\n[dim]PDF → Classification → Extraction → Validation → Outputs[/dim]",
            border_style="magenta",
        )
    )

    console.print(f"[green]✅ PDF gevonden:[/green] {pdf_path}")
    console.print("[blue]📁 Tussenbestanden worden opgeslagen in: tmp/ (DOI-gebaseerd)[/blue]")
    console.print(f"[blue]🤖 LLM Provider: {args.llm_provider.upper()}[/blue]")

    # Updated pipeline steps for 4-component system
    table = Table(title="Pipeline stappen (4-component systeem)", box=box.SIMPLE_HEAVY)
    table.add_column("Stap", style="cyan", no_wrap=True)
    table.add_column("Status", style="green")
    steps = [
        ("1. Classificatie", "⏳"),
        ("2. Data extractie", ""),
        ("3. Validatie", ""),
        ("4. Correctie (indien nodig)", ""),
        ("5. Finale outputs", ""),
    ]
    for s, st in steps:
        table.add_row(s, st)
    console.print(table)

    # Run the four-step pipeline with selected LLM provider
    with console.status(
        "[bold cyan]Bezig met vier-staps extractie pipeline...[/bold cyan]", spinner="dots"
    ):
        results = run_four_step_pipeline(
            pdf_path=pdf_path,
            max_pages=args.max_pages,
            llm_provider=args.llm_provider,
            breakpoint_after_step=BREAKPOINT_AFTER_STEP,
            have_llm_support=HAVE_LLM_SUPPORT,
        )

    # Show detailed summary
    console.print("\n[bold green]✅ Pipeline voltooid[/bold green]")

    summary = Table(title="Samenvatting", box=box.SIMPLE)
    summary.add_column("Onderdeel", style="cyan")
    summary.add_column("Resultaat")

    # Classification summary
    classification = results.get("classification", {})
    publication_type = classification.get("publication_type", "—")
    confidence = classification.get("classification_confidence", 0)
    doi = classification.get("metadata", {}).get("doi", "—")

    summary.add_row("DOI", doi)
    summary.add_row("Publicatietype", publication_type)
    summary.add_row("Classificatie betrouwbaarheid", f"{confidence:.2f}")

    # Extraction summary
    if "extraction" in results:
        summary.add_row("Data extractie", "✅ Voltooid")

    # Validation summary
    validation = results.get("validation", {})
    validation_status = validation.get("verification_summary", {}).get("overall_status", "—")
    completeness = validation.get("verification_summary", {}).get("completeness_score", 0)
    accuracy = validation.get("verification_summary", {}).get("accuracy_score", 0)

    summary.add_row("Validatie status", validation_status)
    summary.add_row("Compleetheid score", f"{completeness:.2f}")
    summary.add_row("Nauwkeurigheid score", f"{accuracy:.2f}")

    # Correction summary
    if "extraction_corrected" in results:
        summary.add_row("Correctie uitgevoerd", "✅ Ja")
        final_validation = results.get("validation_corrected", {})
        final_status = final_validation.get("verification_summary", {}).get("overall_status", "—")
        summary.add_row("Finale validatie", final_status)

    console.print(summary)

    if args.keep_tmp:
        console.print("[blue]📁 Tussenbestanden behouden in: tmp/[/blue]")
        console.print("[dim]Gebruik de DOI-gebaseerde bestandsnamen voor verdere verwerking[/dim]")
    else:
        console.print("[dim]💡 Gebruik --keep-tmp om tussenbestanden te behouden[/dim]")
        console.print("[dim]Tussenbestanden worden automatisch overschreven bij volgende run[/dim]")


if __name__ == "__main__":
    main()
