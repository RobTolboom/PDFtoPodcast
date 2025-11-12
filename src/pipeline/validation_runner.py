# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Dual validation runner for extraction quality control.

This module implements the two-tier validation strategy:
1. Schema validation (fast, cheap, catches structural errors)
2. LLM validation (conditional, expensive, catches semantic errors)

See VALIDATION_STRATEGY.md for design rationale.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console

from ..llm import LLMError
from ..prompts import PromptLoadError, load_validation_prompt
from ..schemas_loader import SchemaLoadError, load_schema
from ..validation import ValidationError, validate_extraction_quality

if TYPE_CHECKING:
    from ..llm import BaseLLMProvider

console = Console()

# Validation configuration
# Minimum schema quality score required before running expensive LLM validation
# If schema validation quality < threshold, skip LLM validation and go directly to correction
SCHEMA_QUALITY_THRESHOLD = 0.5  # 50% - extraction must have basic structure


def run_dual_validation(
    extraction_result: dict[str, Any],
    pdf_path: Path,
    max_pages: int | None,
    publication_type: str,
    llm: "BaseLLMProvider",
    console: Console,
    schema_quality_threshold: float = SCHEMA_QUALITY_THRESHOLD,
    banner_label: str | None = None,
) -> dict[str, Any]:
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
        schema_quality_threshold: Minimum quality score to trigger LLM validation
        banner_label: Optional custom label for console output banner

    Returns:
        Dictionary with combined validation results:
        {
            "schema_validation": {...},      # Schema validation details
            "verification_summary": {...},   # Overall status
            "quality_assessment": str,       # Narrative assessment
            "recommendations": [...]         # Improvement suggestions
        }

    Raises:
        LLMError: If LLM validation fails
        SchemaLoadError: If schema cannot be loaded
        ValidationError: If validation process fails

    Example:
        >>> from pathlib import Path
        >>> from src.llm import get_llm_provider
        >>> llm = get_llm_provider("openai")
        >>> result = run_dual_validation(
        ...     extraction_result={"trial_name": "Study A"},
        ...     pdf_path=Path("paper.pdf"),
        ...     max_pages=20,
        ...     publication_type="interventional_trial",
        ...     llm=llm,
        ...     console=Console()
        ... )
        >>> result["verification_summary"]["overall_status"]
        'passed'
    """
    try:
        # Step 1: Schema validation (always runs)
        title = banner_label or "VALIDATION"
        console.print(f"\n[bold magenta]═══ {title} ═══[/bold magenta]\n")
        console.print("[dim]Running schema validation...[/dim]")
        extraction_schema = load_schema(publication_type)

        schema_validation = validate_extraction_quality(
            data=extraction_result, schema=extraction_schema, strict=False
        )

        schema_quality = schema_validation["quality_score"]
        console.print(
            "[dim]Schema compliance: "
            f"{'✅' if schema_validation['schema_compliant'] else '❌'} "
            f"({schema_quality:.1%})[/dim]"
        )

        # Step 2: LLM-based semantic validation (conditional on schema quality)
        # Only run expensive LLM validation if extraction has decent structure
        if schema_quality >= schema_quality_threshold:
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

            console.print("[green]✅ Validation completed[/green]")

            # Display validation results summary
            summary = validation_result.get("verification_summary", {})
            overall_quality = (
                summary.get("overall_quality") or summary.get("quality_score") or schema_quality
            )
            console.print("\n[bold]Quality Summary:[/bold]")
            if overall_quality is not None:
                console.print(f"  Overall Quality:   {overall_quality:.1%}")
            status = summary.get("overall_status")
            console.print(f"  Validation Status: {status.title() if status else 'Unknown'}")

        else:
            # Schema quality too low - skip expensive LLM validation
            console.print(
                f"[yellow]⚠️  Schema quality {schema_quality:.1%} below threshold "
                f"({schema_quality_threshold:.0%}).[/yellow]"
            )
            console.print("[dim]Skipping LLM validation and continuing to correction.[/dim]")

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
                    f"Quality score: {schema_validation['quality_score']:.1%} (threshold: {schema_quality_threshold:.0%})",
                ],
            }

            console.print("[yellow]⚠️  Proceeding to correction loop.[/yellow]")

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

    except (PromptLoadError, ValidationError, LLMError) as e:
        console.print(f"[red]❌ Validation error: {e}[/red]")
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
