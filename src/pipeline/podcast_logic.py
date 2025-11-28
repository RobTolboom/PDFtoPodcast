import json
import re
from collections.abc import Callable
from typing import Any

from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as jsonschema_validate
from rich.console import Console

from ..llm import get_llm_provider
from ..prompts import load_podcast_generation_prompt
from ..rendering.podcast_renderer import render_podcast_to_markdown
from ..schemas_loader import load_schema
from .file_manager import PipelineFileManager
from .utils import _call_progress_callback, _strip_metadata_for_pipeline

# Constants
STEP_PODCAST_GENERATION = "podcast_generation"

console = Console()


def run_podcast_generation(
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm_provider: str,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None = None,
) -> dict[str, Any]:
    """
    Generate a podcast script from extraction and appraisal data.

    Args:
        extraction_result: Validated extraction JSON
        appraisal_result: Best appraisal JSON
        classification_result: Classification result
        llm_provider: LLM provider name ("openai" | "claude")
        file_manager: File manager for saving output
        progress_callback: Optional callback for progress updates

    Returns:
        dict: {
            'podcast': dict,           # Generated podcast (metadata + transcript)
            'status': str,             # "success" | "failed"
            'validation': dict         # Validation results
        }
    """
    _call_progress_callback(progress_callback, STEP_PODCAST_GENERATION, "starting", {})

    try:
        # Load schema and prompt
        schema = load_schema("podcast")
        prompt_template = load_podcast_generation_prompt()

        # Prepare input data
        # Strip metadata to reduce token usage and focus on content
        extraction_clean = _strip_metadata_for_pipeline(extraction_result)
        appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)

        # Build prompt context with input data (matches report generation pattern)
        # System prompt contains instructions, user prompt contains data
        prompt_context = f"""EXTRACTION_JSON:
{json.dumps(extraction_clean, indent=2)}

APPRAISAL_JSON:
{json.dumps(appraisal_clean, indent=2)}

CLASSIFICATION_JSON:
{json.dumps(classification_result, indent=2)}

PODCAST_SCHEMA:
{json.dumps(schema, indent=2)}
"""

        # Call LLM with correct parameter pattern
        llm = get_llm_provider(llm_provider)
        _call_progress_callback(progress_callback, STEP_PODCAST_GENERATION, "generating_script", {})

        # Use generate_json_with_schema for structured output
        # system_prompt = instructions (from Podcast-generation.txt)
        # prompt = data (extraction, appraisal, classification, schema)
        podcast_json = llm.generate_json_with_schema(
            schema=schema,
            system_prompt=prompt_template,
            prompt=prompt_context,
            schema_name="podcast_generation",
        )

        # Recalculate metadata from actual transcript
        transcript = podcast_json.get("transcript", "")
        actual_word_count = len(transcript.split())
        # Estimate duration: ~150 words per minute (spoken pace)
        actual_duration = round(actual_word_count / 150)

        # Update metadata with actual values
        if "metadata" not in podcast_json:
            podcast_json["metadata"] = {}
        podcast_json["metadata"]["word_count"] = actual_word_count
        podcast_json["metadata"]["estimated_duration_minutes"] = max(1, min(actual_duration, 10))

        # Light validation (single pass)
        validation_issues = []  # Non-critical issues (warnings)
        critical_issues = []  # Critical issues (hard fail)

        # Check 0: Schema validation (hard requirement)
        try:
            jsonschema_validate(podcast_json, schema)
        except JsonSchemaValidationError as e:
            critical_issues.append(f"Schema validation failed: {e.message}")

        # Check 1: Length check (hard requirement: 800-1500 words)
        word_count = actual_word_count
        if word_count < 800:
            critical_issues.append(f"Transcript too short ({word_count} words). Minimum: 800.")
        elif word_count > 1500:
            critical_issues.append(f"Transcript too long ({word_count} words). Maximum: 1500.")

        # Check 2: No abbreviations (enhanced with regex for word boundaries)
        common_abbrs = [
            "ICU",
            "CI",
            "HR",
            "OR",
            "RR",
            "mg",
            "kg",
            "RCT",
            "BMI",
            "ECG",
            "COPD",
            "ARDS",
            "CHF",
            "MI",
            "IV",
            "IM",
            "SC",
            "PMID",
            "DOI",
            "vs",
            "etc",
            "ie",
            "eg",
        ]
        found_abbrs = []
        for abbr in common_abbrs:
            # Use word boundaries to avoid false positives like "FORM" matching "OR"
            if re.search(rf"\b{re.escape(abbr)}\b", transcript, re.IGNORECASE):
                found_abbrs.append(abbr)
        if found_abbrs:
            validation_issues.append(f"Found potential abbreviations: {', '.join(found_abbrs)}")

        # Check 3: No markdown headings
        if "# " in transcript or "**" in transcript:
            validation_issues.append("Transcript contains markdown formatting (headings/bold).")

        # Check 4: Key outcomes presence (heuristic)
        # Verify primary outcome from extraction is mentioned in transcript
        primary_outcome = (
            extraction_result.get("outcomes", {}).get("primary", {}).get("description", "")
        )
        if primary_outcome and primary_outcome.lower() not in transcript.lower():
            validation_issues.append(
                f"Primary outcome may not be mentioned: '{primary_outcome[:50]}...'"
            )

        # Check 5: Numeric accuracy (spot check sample size)
        sample_size = extraction_result.get("participants", {}).get("sample_size", {}).get("total")
        if sample_size and str(sample_size) not in transcript:
            validation_issues.append(f"Sample size {sample_size} may not appear in transcript")

        # Check 6: GRADE certainty alignment
        # High-certainty words should not be used with low/very low GRADE evidence
        grade_certainty = appraisal_result.get("grade", {}).get("certainty_overall", "").lower()
        high_certainty_words = ["shows", "demonstrates", "reduces", "increases"]
        transcript_lower = transcript.lower()
        if grade_certainty in ["low", "very low"]:
            for word in high_certainty_words:
                if word in transcript_lower:
                    validation_issues.append(
                        f"High-certainty word '{word}' used with {grade_certainty} GRADE evidence"
                    )
                    break

        # Check 7: "Insufficiently reported" for missing data
        # If key fields are missing, transcript should acknowledge this
        missing_fields = []
        if not extraction_result.get("interventions"):
            missing_fields.append("interventions")
        if not extraction_result.get("outcomes", {}).get("primary"):
            missing_fields.append("primary outcome")
        if missing_fields and "insufficiently reported" not in transcript_lower:
            validation_issues.append(
                f"Missing data ({', '.join(missing_fields)}) but "
                "'insufficiently reported' not found in transcript"
            )

        # Check 8: Max 3 numerical statements
        # Heuristic: count numbers in transcript (integers and decimals)
        numbers_in_transcript = re.findall(r"\b\d+(?:\.\d+)?\b", transcript)
        # Filter out small numbers (1, 2, 3) which are often non-data
        significant_numbers = [n for n in numbers_in_transcript if len(n) > 1 or int(n) > 3]
        if len(significant_numbers) > 3:
            validation_issues.append(
                f"Transcript contains {len(significant_numbers)} numerical values "
                f"(max 3 recommended): {', '.join(significant_numbers[:5])}..."
            )

        # Determine validation status
        # Critical issues → failed (hard fail, no file save)
        # Non-critical issues → warnings (step succeeds with warnings)
        # No issues → passed
        if critical_issues:
            validation_status = "failed"
        elif validation_issues:
            validation_status = "warnings"
        else:
            validation_status = "passed"

        validation_result = {
            "status": validation_status,
            "issues": validation_issues + critical_issues,
            "critical_issues": critical_issues,
            "ready_for_tts": validation_status != "failed",
        }

        # Always save files per spec (even on failure)
        podcast_file = file_manager.save_json(podcast_json, "podcast")
        console.print(f"[green]✅ Podcast script saved: {podcast_file}[/green]")

        # Also save validation result
        file_manager.save_json(validation_result, "podcast_validation")

        # Render markdown
        try:
            md_filename = f"{file_manager.identifier}-podcast.md"
            md_path = file_manager.tmp_dir / md_filename
            render_podcast_to_markdown(podcast_json, md_path)
            console.print(f"[green]✅ Podcast markdown saved: {md_path}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️  Failed to render podcast markdown: {e}[/yellow]")
            # Continue - markdown is optional, don't fail the step

        # Handle validation failure (files saved, but step marked as failed)
        if validation_status == "failed":
            error_msg = f"Podcast validation failed: {'; '.join(critical_issues)}"
            console.print(f"[red]❌ {error_msg}[/red]")
            _call_progress_callback(
                progress_callback,
                STEP_PODCAST_GENERATION,
                "failed",
                {"file": str(podcast_file), "error": error_msg, "validation": validation_result},
            )
            return {"podcast": podcast_json, "status": "failed", "validation": validation_result}

        _call_progress_callback(
            progress_callback,
            STEP_PODCAST_GENERATION,
            "completed",
            {"file": str(podcast_file), "validation": validation_result},
        )

        return {"podcast": podcast_json, "status": "success", "validation": validation_result}

    except Exception as e:
        console.print(f"[red]❌ Podcast generation failed: {e}[/red]")
        _call_progress_callback(
            progress_callback, STEP_PODCAST_GENERATION, "failed", {"error": str(e)}
        )
        raise
