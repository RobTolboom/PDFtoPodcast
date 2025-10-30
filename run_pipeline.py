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
    from src.pipeline import run_four_step_pipeline, run_single_step
    from src.pipeline.file_manager import PipelineFileManager

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
        description=(
            "PDFtoPodcast Pipeline - Extract structured data from medical research PDFs\n\n"
            "Full Pipeline: python run_pipeline.py paper.pdf\n"
            "Single Step: python run_pipeline.py paper.pdf --step validation_correction --max-iterations 2"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    parser.add_argument(
        "--step",
        choices=[
            "classification",
            "extraction",
            "validation",
            "correction",
            "validation_correction",
        ],
        default=None,
        help="Run specific pipeline step (default: run all steps)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum correction attempts for validation_correction step (default: 3)",
    )
    parser.add_argument(
        "--completeness-threshold",
        type=float,
        default=0.90,
        help="Minimum completeness score 0.0-0.99 (default: 0.90)",
    )
    parser.add_argument(
        "--accuracy-threshold",
        type=float,
        default=0.95,
        help="Minimum accuracy score 0.0-0.99 (default: 0.95)",
    )
    parser.add_argument(
        "--schema-threshold",
        type=float,
        default=0.95,
        help="Minimum schema compliance score 0.0-0.99 (default: 0.95)",
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

    # Check if running single step or full pipeline
    if args.step:
        # Single step execution
        console.print(f"[yellow]🎯 Running single step:[/yellow] {args.step}")

        # Create file manager
        file_manager = PipelineFileManager(pdf_path)

        # Build quality thresholds if validation_correction step
        if args.step == "validation_correction":
            quality_thresholds = {
                "completeness_score": args.completeness_threshold,
                "accuracy_score": args.accuracy_threshold,
                "schema_compliance_score": args.schema_threshold,
                "critical_issues": 0,
            }
            console.print(
                f"[dim]Quality thresholds: completeness={args.completeness_threshold:.0%}, "
                f"accuracy={args.accuracy_threshold:.0%}, "
                f"schema={args.schema_threshold:.0%}[/dim]"
            )
            console.print(f"[dim]Max iterations: {args.max_iterations}[/dim]")
        else:
            quality_thresholds = None

        # Run single step
        with console.status(f"[bold cyan]Running step: {args.step}...[/bold cyan]", spinner="dots"):
            result = run_single_step(
                step_name=args.step,
                pdf_path=pdf_path,
                max_pages=args.max_pages,
                llm_provider=args.llm_provider,
                file_manager=file_manager,
                progress_callback=None,  # CLI has no UI callback
                previous_results=None,  # Load from disk if needed
                max_correction_iterations=(
                    args.max_iterations if args.step == "validation_correction" else None
                ),
                quality_thresholds=quality_thresholds,
            )

        # Print result summary
        console.print(f"\n[bold green]✅ Step '{args.step}' completed[/bold green]")

        # Display step-specific results
        if args.step == "classification":
            pub_type = result.get("publication_type", "—")
            confidence = result.get("classification_confidence", 0)
            doi = result.get("metadata", {}).get("doi", "—")
            console.print(
                f"[cyan]Publication type:[/cyan] {pub_type} (confidence: {confidence:.2f})"
            )
            console.print(f"[cyan]DOI:[/cyan] {doi}")
        elif args.step == "validation_correction":
            final_status = result.get("final_status", "unknown")
            iteration_count = result.get("iteration_count", 0)
            console.print(f"[cyan]Final status:[/cyan] {final_status}")
            console.print(f"[cyan]Iterations:[/cyan] {iteration_count}")
            if "iterations" in result and result["iterations"]:
                best_iter = result.get("best_iteration", 0)
                console.print(f"[cyan]Best iteration:[/cyan] {best_iter}")
        elif args.step in ["validation"]:
            validation_status = result.get("verification_summary", {}).get("overall_status", "—")
            completeness = result.get("verification_summary", {}).get("completeness_score", 0)
            accuracy = result.get("verification_summary", {}).get("accuracy_score", 0)
            console.print(f"[cyan]Status:[/cyan] {validation_status}")
            console.print(f"[cyan]Completeness:[/cyan] {completeness:.2%}")
            console.print(f"[cyan]Accuracy:[/cyan] {accuracy:.2%}")
        else:
            console.print("[dim]Result saved to tmp/[/dim]")

        # Store result for summary section
        results = {args.step: result}

    else:
        # Full pipeline execution
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
