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

    Both OpenAI (GPT-4o vision) and Claude (document API) support PDF upload:
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
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Import LLM and prompt functionality
try:
    from src.llm import LLMError, get_llm_provider
    from src.prompts import (
        PromptLoadError,
        load_classification_prompt,
        load_correction_prompt,
        load_extraction_prompt,
        load_validation_prompt,
    )
    from src.schemas_loader import (
        SchemaLoadError,
        load_schema,
        validate_schema_compatibility,
    )
    from src.validation import ValidationError, validate_extraction_quality

    HAVE_LLM_SUPPORT = True
except ImportError as e:
    console = Console()
    console.print(f"[yellow]⚠️ LLM modules niet beschikbaar: {e}[/yellow]")
    HAVE_LLM_SUPPORT = False

if TYPE_CHECKING:
    from src.llm import BaseLLMProvider

console = Console()

# Validation configuration
# Minimum schema quality score required before running expensive LLM validation
# If schema validation quality < threshold, skip LLM validation and go directly to correction
SCHEMA_QUALITY_THRESHOLD = 0.5  # 50% - extraction must have basic structure

# 🔍 TESTING BREAKPOINT CONFIGURATION
# Set to the step where you want to pause for inspection:
# Options: "classification", "extraction", "validation", "correction", None (run full pipeline)
BREAKPOINT_AFTER_STEP = "extraction"  # Change this to move breakpoint


def doi_to_safe_filename(doi: str) -> str:
    """Convert DOI to filesystem-safe string"""
    # Remove 'doi:' prefix if present
    if doi.lower().startswith("doi:"):
        doi = doi[4:]

    # Replace problematic characters with hyphens
    safe_doi = doi.replace("/", "-").replace(":", "-").replace(".", "-")
    return safe_doi


def get_file_identifier(classification_result: dict, pdf_path: Path) -> str:
    """Get identifier for filenames, preferring DOI over fallback"""
    doi = classification_result.get("metadata", {}).get("doi")

    if doi:
        return doi_to_safe_filename(doi)
    else:
        # Fallback: PDF naam + timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{pdf_path.stem}_{timestamp}"


def get_next_step(current_step: str) -> str:
    """Get the name of the next pipeline step."""
    steps = ["classification", "extraction", "validation", "correction"]
    try:
        idx = steps.index(current_step)
        return steps[idx + 1] if idx + 1 < len(steps) else "None"
    except ValueError:
        return "None"


def check_breakpoint(
    step_name: str, results: Dict[str, Any], file_manager: "PipelineFileManager"
) -> bool:
    """
    Check if pipeline should stop at this step for testing.

    Returns True if breakpoint triggered (stop pipeline), False otherwise.
    """
    if BREAKPOINT_AFTER_STEP == step_name:
        console.print(
            f"\n[bold yellow]⏸️  BREAKPOINT: Stopped after '{step_name}' step[/bold yellow]"
        )
        console.print("[dim]Pipeline paused for step-by-step testing.[/dim]")
        console.print(f"[dim]Results saved to: tmp/{file_manager.identifier}-*[/dim]")
        console.print(
            f"\n[dim]💡 To continue: Set BREAKPOINT_AFTER_STEP = '{get_next_step(step_name)}' or None[/dim]"
        )
        return True
    return False


class PipelineFileManager:
    """Manages DOI-based file naming and storage for pipeline intermediate and final outputs"""

    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.pdf_stem = pdf_path.stem

        # Create tmp directory
        self.tmp_dir = Path("tmp")
        self.tmp_dir.mkdir(exist_ok=True)

        # File identifier will be set after classification
        self.identifier: Optional[str] = None

    def set_identifier_from_classification(self, classification_result: dict):
        """Set file identifier preferring DOI over fallback"""
        self.identifier = get_file_identifier(classification_result, self.pdf_path)
        console.print(f"[blue]📁 Bestandsidentifier: {self.identifier}[/blue]")

    def get_filename(self, step: str, status: str = "") -> Path:
        """Generate consistent filenames for pipeline steps"""
        if not self.identifier:
            raise ValueError("Identifier not set - call set_identifier_from_classification first")

        if status:
            filename = f"{self.identifier}-{step}-{status}.json"
        else:
            filename = f"{self.identifier}-{step}.json"

        return self.tmp_dir / filename

    def save_json(self, data: Dict[Any, Any], step: str, status: str = "") -> Path:
        """Save JSON data with consistent DOI-based naming"""
        filepath = self.get_filename(step, status)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath


def run_dual_validation(
    extraction_result: Dict[str, Any],
    pdf_path: Path,
    max_pages: Optional[int],
    publication_type: str,
    llm: "BaseLLMProvider",
    console: Console,
) -> Dict[str, Any]:
    """
    Run dual validation: schema validation + conditional LLM validation.

    This implements the two-tier validation strategy:
    1. Schema validation (always runs - fast, cheap, catches structural errors)
    2. LLM validation (conditional - only if schema quality >= threshold)

    Args:
        extraction_result: The extracted JSON data to validate
        pdf_path: Path to original PDF file for LLM semantic validation
        max_pages: Maximum number of pages to process from PDF
        publication_type: Type of publication (for schema loading)
        llm: LLM provider instance
        console: Rich console for output

    Returns:
        Dictionary with combined validation results:
        {
            "schema_validation": {...},      # Schema validation details
            "verification_summary": {...},   # Overall status
            "quality_assessment": str,       # Narrative assessment
            "recommendations": [...]         # Improvement suggestions
        }

    See VALIDATION_STRATEGY.md for design rationale.
    """
    try:
        # Step 1: Schema validation (always runs)
        console.print("[dim]Schema validation...[/dim]")
        extraction_schema = load_schema(publication_type)

        schema_validation = validate_extraction_quality(
            data=extraction_result, schema=extraction_schema, strict=False
        )

        console.print(
            f"[dim]Schema compliance: {'✅' if schema_validation['schema_compliant'] else '❌'}[/dim]"
        )
        console.print(f"[dim]Quality score: {schema_validation['quality_score']:.1%}[/dim]")

        # Step 2: LLM-based semantic validation (conditional on schema quality)
        # Only run expensive LLM validation if extraction has decent structure
        if schema_validation["quality_score"] >= SCHEMA_QUALITY_THRESHOLD:
            console.print("[dim]LLM semantic validation with PDF upload...[/dim]")
            validation_prompt = load_validation_prompt()
            validation_schema = load_schema("validation")

            # Prepare validation context (extracted JSON + schema validation results)
            validation_context = f"""
EXTRACTED_JSON: {json.dumps(extraction_result, indent=2)}

SCHEMA_VALIDATION_RESULTS: {json.dumps(schema_validation, indent=2)}

Verify the extracted data against the original PDF document. Check for hallucinations, missing data, accuracy errors, and completeness.
"""

            # Run LLM validation with PDF upload for direct comparison
            llm_validation = llm.generate_json_with_pdf(
                pdf_path=pdf_path,
                schema=validation_schema,
                system_prompt=validation_prompt + "\n\n" + validation_context,
                max_pages=max_pages,
                schema_name="validation_report",
            )

            # Combine schema and LLM validation results
            validation_result = {
                **llm_validation,
                "schema_validation": schema_validation,
                "verification_summary": {
                    **llm_validation.get("verification_summary", {}),
                    "schema_compliance": schema_validation["quality_score"],
                },
            }

            console.print("[green]✅ Combined validation completed[/green]")
        else:
            # Schema quality too low - skip expensive LLM validation
            console.print(
                f"[yellow]⚠️  Schema quality below threshold ({SCHEMA_QUALITY_THRESHOLD:.0%})[/yellow]"
            )
            console.print("[dim]Skipping LLM validation - extraction needs correction first[/dim]")

            # Return schema validation results only
            validation_result = {
                "schema_validation": schema_validation,
                "verification_summary": {
                    "overall_status": "failed",
                    "schema_compliance": schema_validation["quality_score"],
                },
                "quality_assessment": "Schema validation failed. Skipped LLM validation for efficiency.",
                "recommendations": [
                    "Fix structural issues identified in schema validation",
                    f"Quality score: {schema_validation['quality_score']:.1%} (threshold: {SCHEMA_QUALITY_THRESHOLD:.0%})",
                ],
            }

            console.print("[yellow]⚠️  Will proceed to correction step[/yellow]")

        return validation_result

    except SchemaLoadError as e:
        console.print(f"[yellow]⚠️  Schema loading error: {e}[/yellow]")
        # Cannot proceed with validation without schemas
        console.print("[yellow]Skipping validation due to schema error[/yellow]")
        validation_result = {
            "verification_summary": {
                "overall_status": "failed",
                "completeness_score": 0.0,
                "accuracy_score": 0.0,
                "schema_compliance_score": 0.0,
                "total_issues": 1,
                "critical_issues": 1,
            },
            "issues": [
                {
                    "issue_id": "I001",
                    "type": "schema_violation",
                    "severity": "critical",
                    "category": "other",
                    "description": f"Schema loading error: {e}",
                    "recommendation": "Fix schema loading issue",
                }
            ],
            "field_validation": {
                "required_fields_complete": False,
                "schema_compliance": False,
                "source_references_valid": False,
                "data_types_correct": False,
            },
            "completeness_analysis": {},
            "recommendations": ["Fix schema loading system"],
        }
        return validation_result

    except (PromptLoadError, LLMError, ValidationError) as e:
        console.print(f"[red]❌ Validatie fout: {e}[/red]")
        return {
            "verification_summary": {
                "overall_status": "failed",
                "completeness_score": 0.0,
                "accuracy_score": 0.0,
                "schema_compliance_score": 0.0,
                "total_issues": 1,
                "critical_issues": 1,
            },
            "issues": [
                {
                    "issue_id": "I001",
                    "type": "schema_violation",
                    "severity": "critical",
                    "category": "other",
                    "description": f"Validation error: {e}",
                    "recommendation": "Fix validation system",
                }
            ],
            "field_validation": {
                "required_fields_complete": False,
                "schema_compliance": False,
                "source_references_valid": False,
                "data_types_correct": False,
            },
            "completeness_analysis": {},
            "recommendations": ["Fix validation system"],
        }


def run_four_step_pipeline(
    pdf_path: Path, max_pages: Optional[int] = None, llm_provider: str = "openai"
) -> Dict[str, Any]:
    """
    Four-step extraction pipeline with DOI-based file management:
    1. Classification (identify publication type + extract metadata)
    2. Extraction (detailed data extraction based on classified type)
    3. Validation (quality control and schema validation)
    4. Correction (if validation indicates issues)
    """

    file_manager = PipelineFileManager(pdf_path)
    results = {}

    console.print("[bold cyan]📋 Stap 1: Classificatie[/bold cyan]")

    if not HAVE_LLM_SUPPORT:
        console.print("[red]❌ LLM support niet beschikbaar - gebruik mock data[/red]")
        classification_result = {
            "metadata": {
                "title": "Example Study Title",
                "doi": "10.1186/s12871-025-02345-6",
                "journal": "BMC Anesthesiology",
            },
            "publication_type": "interventional_trial",
            "classification_confidence": 0.95,
            "classification_reasoning": "Mock data - LLM support not available",
        }
    else:
        try:
            # Load classification prompt and schema
            classification_prompt = load_classification_prompt()
            classification_schema = load_schema("classification")

            # Get LLM provider
            llm = get_llm_provider(llm_provider)

            # Run classification with direct PDF upload
            console.print("[dim]Uploading PDF for classification...[/dim]")
            classification_result = llm.generate_json_with_pdf(
                pdf_path=pdf_path,
                schema=classification_schema,
                system_prompt=classification_prompt,
                max_pages=max_pages,
                schema_name="classification",
            )

        except (PromptLoadError, LLMError, SchemaLoadError) as e:
            console.print(f"[red]❌ Classificatie fout: {e}[/red]")
            console.print("[yellow]Gebruik mock data voor demonstratie[/yellow]")
            classification_result = {
                "metadata": {
                    "title": "Fallback Study Title",
                    "doi": "10.1186/s12871-025-02345-6",
                    "journal": "BMC Anesthesiology",
                },
                "publication_type": "interventional_trial",
                "classification_confidence": 0.5,
                "classification_reasoning": f"Error in classification: {e}",
            }

    # Set file identifier based on DOI from classification
    file_manager.set_identifier_from_classification(classification_result)

    # Save classification result
    classification_file = file_manager.save_json(classification_result, "classification")
    console.print(f"[green]✅ Classificatie opgeslagen: {classification_file}[/green]")
    results["classification"] = classification_result

    # Check for breakpoint after classification
    if check_breakpoint("classification", results, file_manager):
        return results

    if classification_result["publication_type"] == "overig":
        console.print(
            "[yellow]⚠️ Publicatietype 'overig' - geen gespecialiseerde extractie beschikbaar[/yellow]"
        )
        return results

    console.print("[bold cyan]📊 Stap 2: Data Extractie (Schema-based)[/bold cyan]")

    if not HAVE_LLM_SUPPORT:
        console.print("[red]❌ LLM support niet beschikbaar - gebruik mock data[/red]")
        extraction_result = {
            "schema_version": "v2.0",
            "study_design": {"type": "RCT"},
            "metadata": classification_result["metadata"],
            "placeholder": "mock_extraction_data",
        }
    else:
        try:
            publication_type = classification_result.get("publication_type")

            if publication_type == "overig":
                console.print(
                    "[yellow]⚠️ Publicatietype 'overig' - geen gespecialiseerde extractie beschikbaar[/yellow]"
                )
                extraction_result = {
                    "error": "No specialized extraction available for publication type 'overig'",
                    "metadata": classification_result["metadata"],
                }
            else:
                # Load appropriate extraction prompt and schema
                extraction_prompt = load_extraction_prompt(publication_type)
                extraction_schema = load_schema(publication_type)

                # Check schema compatibility with OpenAI
                compatibility = validate_schema_compatibility(extraction_schema)
                if compatibility["warnings"]:
                    console.print("[yellow]⚠️  Schema compatibility warnings:[/yellow]")
                    for warning in compatibility["warnings"][:3]:
                        console.print(f"[dim]  • {warning}[/dim]")

                console.print(
                    f"[dim]Running schema-based {publication_type} extraction with PDF upload..."
                )
                console.print(f"[dim]Schema: ~{compatibility['estimated_tokens']} tokens[/dim]")

                # Run schema-based extraction with direct PDF upload
                extraction_result = llm.generate_json_with_pdf(
                    pdf_path=pdf_path,
                    schema=extraction_schema,
                    system_prompt=extraction_prompt,
                    max_pages=max_pages,
                    schema_name=f"{publication_type}_extraction",
                )

                console.print("[green]✅ Schema-conforming extraction completed[/green]")

        except SchemaLoadError as e:
            console.print(f"[red]❌ Schema loading fout: {e}[/red]")
            console.print("[yellow]Cannot proceed without schema - skipping extraction[/yellow]")
            try:
                # Without schema, we can't use PDF upload effectively
                # This should rarely happen in production
                extraction_result = {
                    "schema_version": "v2.0",
                    "metadata": classification_result["metadata"],
                    "error": f"Schema loading error: {e}",
                }
            except (PromptLoadError, LLMError) as e2:
                extraction_result = {
                    "schema_version": "v2.0",
                    "metadata": classification_result["metadata"],
                    "error": f"Extraction error: {e2}",
                }

        except (PromptLoadError, LLMError) as e:
            console.print(f"[red]❌ Extractie fout: {e}[/red]")
            console.print("[yellow]Gebruik mock data voor demonstratie[/yellow]")
            extraction_result = {
                "schema_version": "v2.0",
                "study_design": {"type": "Unknown"},
                "metadata": classification_result["metadata"],
                "error": f"Extraction error: {e}",
            }

    extraction_file = file_manager.save_json(extraction_result, "extraction")
    console.print(f"[green]✅ Extractie opgeslagen: {extraction_file}[/green]")
    results["extraction"] = extraction_result

    # Check for breakpoint after extraction
    if check_breakpoint("extraction", results, file_manager):
        return results

    console.print("[bold cyan]🔍 Stap 3: Validatie (Schema + LLM)[/bold cyan]")

    if not HAVE_LLM_SUPPORT:
        console.print("[red]❌ LLM support niet beschikbaar - gebruik mock data[/red]")
        validation_result = {
            "verification_summary": {
                "overall_status": "passed",
                "completeness_score": 0.92,
                "accuracy_score": 0.95,
                "schema_compliance": 1.0,
            },
            "quality_assessment": "Mock validation data",
            "recommendations": [],
        }
    else:
        # Run dual validation (schema + conditional LLM)
        publication_type = classification_result.get("publication_type")
        validation_result = run_dual_validation(
            extraction_result=extraction_result,
            pdf_path=pdf_path,
            max_pages=max_pages,
            publication_type=publication_type,
            llm=llm,
            console=console,
        )

    validation_file = file_manager.save_json(validation_result, "validation")
    console.print(f"[green]✅ Validatie opgeslagen: {validation_file}[/green]")
    results["validation"] = validation_result

    # Check for breakpoint after validation
    if check_breakpoint("validation", results, file_manager):
        return results

    # Conditional step 4: Correction if validation indicates issues
    validation_status = validation_result.get("verification_summary", {}).get("overall_status")
    if validation_status != "passed":
        console.print("[bold cyan]🔧 Stap 4: Correctie[/bold cyan]")

        if not HAVE_LLM_SUPPORT:
            console.print("[red]❌ LLM support niet beschikbaar - gebruik mock correctie[/red]")
            corrected_extraction = {
                **extraction_result,
                "corrected": True,
                "correction_notes": "Mock correction - LLM support not available",
            }
        else:
            try:
                # Load correction prompt and extraction schema
                correction_prompt = load_correction_prompt()
                extraction_schema = load_schema(publication_type)

                # Prepare correction context with original extraction and validation feedback
                correction_context = f"""
ORIGINAL_EXTRACTION: {json.dumps(extraction_result, indent=2)}

VALIDATION_REPORT: {json.dumps(validation_result, indent=2)}

Systematically address all identified issues and produce corrected, complete, schema-compliant JSON extraction.
"""

                # Run correction with PDF upload for direct reference
                console.print("[dim]Running correction with PDF upload...[/dim]")
                corrected_extraction = llm.generate_json_with_pdf(
                    pdf_path=pdf_path,
                    schema=extraction_schema,
                    system_prompt=correction_prompt + "\n\n" + correction_context,
                    max_pages=max_pages,
                    schema_name=f"{publication_type}_extraction_corrected",
                )

                # Ensure correction metadata
                if "correction_notes" not in corrected_extraction:
                    corrected_extraction["correction_notes"] = (
                        "Corrections applied based on validation feedback"
                    )

            except (PromptLoadError, LLMError) as e:
                console.print(f"[red]❌ Correctie fout: {e}[/red]")
                console.print("[yellow]Gebruik fallback correctie[/yellow]")
                corrected_extraction = {
                    **extraction_result,
                    "corrected": True,
                    "correction_notes": f"Correction error: {e}",
                    "error": "Automatic correction failed",
                }

        corrected_file = file_manager.save_json(corrected_extraction, "extraction", "corrected")
        console.print(f"[green]✅ Correctie opgeslagen: {corrected_file}[/green]")

        # Final validation of corrected extraction - use same dual validation approach
        console.print("[dim]Running final validation on corrected extraction...[/dim]")
        if not HAVE_LLM_SUPPORT:
            console.print(
                "[red]❌ LLM support niet beschikbaar - gebruik mock finale validatie[/red]"
            )
            final_validation = {
                "verification_summary": {
                    "overall_status": "passed",
                    "completeness_score": 0.96,
                    "accuracy_score": 0.97,
                    "schema_compliance": 1.0,
                },
                "quality_assessment": "Mock final validation",
                "recommendations": [],
            }
        else:
            # Re-run dual validation on corrected extraction
            final_validation = run_dual_validation(
                extraction_result=corrected_extraction,
                pdf_path=pdf_path,
                max_pages=max_pages,
                publication_type=publication_type,
                llm=llm,
                console=console,
            )

        final_validation_file = file_manager.save_json(final_validation, "validation", "corrected")
        console.print(f"[green]✅ Finale validatie opgeslagen: {final_validation_file}[/green]")

        results["extraction_corrected"] = corrected_extraction
        results["validation_corrected"] = final_validation

        # Check for breakpoint after correction
        if check_breakpoint("correction", results, file_manager):
            return results

    return results


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
            pdf_path, max_pages=args.max_pages, llm_provider=args.llm_provider
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
