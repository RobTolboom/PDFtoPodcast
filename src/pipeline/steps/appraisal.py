# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Appraisal step module.

Handles critical appraisal (RoB, GRADE, applicability) with iterative correction.
"""

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from rich.console import Console

from ...llm import LLMError, get_llm_provider
from ...prompts import (
    PromptLoadError,
    load_appraisal_correction_prompt,
    load_appraisal_prompt,
    load_appraisal_validation_prompt,
)
from ...schemas_loader import SchemaLoadError, load_schema
from ..file_manager import PipelineFileManager
from ..iterative import IterativeLoopConfig, IterativeLoopRunner
from ..iterative import detect_quality_degradation as _detect_quality_degradation_new
from ..iterative import select_best_iteration as _select_best_iteration_new
from ..quality import MetricType, extract_appraisal_metrics_as_dict
from ..quality.thresholds import APPRAISAL_THRESHOLDS
from ..utils import _call_progress_callback, _get_provider_name, _strip_metadata_for_pipeline

console = Console()

# Step name constants
STEP_APPRAISAL = "appraisal"
STEP_APPRAISAL_VALIDATION = "appraisal_validation"

# Quality thresholds for appraisal iterative correction loop
# Derived from centralized thresholds for consistency
APPRAISAL_QUALITY_THRESHOLDS = {
    "logical_consistency_score": APPRAISAL_THRESHOLDS.logical_consistency_score,
    "completeness_score": APPRAISAL_THRESHOLDS.completeness_score,
    "evidence_support_score": APPRAISAL_THRESHOLDS.evidence_support_score,
    "schema_compliance_score": APPRAISAL_THRESHOLDS.schema_compliance_score,
    "critical_issues": APPRAISAL_THRESHOLDS.critical_issues,
}


class UnsupportedPublicationType(ValueError):
    """Exception raised when a publication type has no appraisal support."""

    def __init__(self, publication_type: str, message: str | None = None):
        self.publication_type = publication_type
        if message is None:
            message = (
                f"Appraisal not supported for publication type '{publication_type}'. "
                f"Supported types: interventional_trial, observational_analytic, "
                f"evidence_synthesis, prediction_prognosis, diagnostic, editorials_opinion."
            )
        super().__init__(message)


def _get_appraisal_prompt_name(publication_type: str) -> str:
    """Map publication type to corresponding appraisal prompt filename."""
    prompt_mapping = {
        "interventional_trial": "Appraisal-interventional",
        "observational_analytic": "Appraisal-observational",
        "evidence_synthesis": "Appraisal-evidence-synthesis",
        "prediction_prognosis": "Appraisal-prediction",
        "diagnostic": "Appraisal-prediction",
        "editorials_opinion": "Appraisal-editorials",
    }

    if publication_type not in prompt_mapping:
        raise UnsupportedPublicationType(publication_type)

    return prompt_mapping[publication_type]


# Alias for backward compatibility - delegate to quality module
_extract_appraisal_metrics = extract_appraisal_metrics_as_dict


def _detect_quality_degradation(iterations: list[dict], window: int = 2) -> bool:
    """Detect if quality has been degrading for the last N iterations."""
    return _detect_quality_degradation_new(iterations, window)


def _select_best_appraisal_iteration(iterations: list[dict]) -> dict:
    """Select the iteration with the highest quality score."""
    return _select_best_iteration_new(iterations, MetricType.APPRAISAL)


def is_appraisal_quality_sufficient(
    validation_result: dict | None, thresholds: dict | None = None
) -> bool:
    """Check if appraisal validation quality meets thresholds."""
    if thresholds is None:
        thresholds = APPRAISAL_QUALITY_THRESHOLDS

    if validation_result is None:
        return False

    summary = validation_result.get("validation_summary", {})
    if not summary:
        return False

    def safe_score(key: str, default: float = 0.0) -> float:
        val = summary.get(key, default)
        return val if isinstance(val, int | float) else default

    return (
        safe_score("logical_consistency_score") >= thresholds["logical_consistency_score"]
        and safe_score("completeness_score") >= thresholds["completeness_score"]
        and safe_score("evidence_support_score") >= thresholds["evidence_support_score"]
        and safe_score("schema_compliance_score") >= thresholds["schema_compliance_score"]
        and safe_score("critical_issues", 999) <= thresholds["critical_issues"]
    )


def run_appraisal_step(
    extraction_result: dict[str, Any],
    publication_type: str,
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """
    Run critical appraisal step of the pipeline.

    Performs tool-specific critical appraisal (RoB 2, ROBINS-I, PROBAST, etc.)
    on validated extraction data.
    """
    console.print("[bold cyan]Critical Appraisal[/bold cyan]")

    start_time = time.time()
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)

    try:
        prompt_name = _get_appraisal_prompt_name(publication_type)
    except UnsupportedPublicationType as e:
        console.print(f"[red]X {e}[/red]")
        raise

    _call_progress_callback(
        progress_callback,
        STEP_APPRAISAL,
        "starting",
        {"publication_type": publication_type, "prompt": prompt_name},
    )

    try:
        appraisal_prompt = load_appraisal_prompt(publication_type)
        appraisal_schema = load_schema("appraisal")

        console.print(f"[dim]Running {prompt_name} critical appraisal...")
        console.print(f"[dim]Tool routing: {publication_type} -> {prompt_name}[/dim]")

        from ...config import llm_settings

        appraisal_result = llm.generate_json_with_schema(
            schema=appraisal_schema,
            system_prompt=appraisal_prompt,
            prompt=f"EXTRACTION_JSON:\n{json.dumps(extraction_clean, indent=2)}",
            schema_name=f"{publication_type}_appraisal",
            reasoning_effort=llm_settings.reasoning_effort_appraisal,
        )

        console.print("[green]+ Critical appraisal completed[/green]")

        elapsed = time.time() - start_time
        appraisal_result["_pipeline_metadata"] = {
            "step": "appraisal",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed,
            "llm_provider": _get_provider_name(llm),
            "model_used": appraisal_result.get("_metadata", {}).get("model"),
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
            "publication_type": publication_type,
            "prompt_used": prompt_name,
        }

        _call_progress_callback(
            progress_callback,
            STEP_APPRAISAL,
            "completed",
            {
                "result": appraisal_result,
                "elapsed_seconds": elapsed,
                "tool_used": appraisal_result.get("tool", {}).get("name", "unknown"),
            },
        )

        return appraisal_result

    except (PromptLoadError, SchemaLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]X Appraisal error: {e}[/red]")

        error_data = {
            "_pipeline_metadata": {
                "step": "appraisal",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": elapsed,
                "llm_provider": _get_provider_name(llm),
                "status": "failed",
                "error_message": str(e),
                "error_type": type(e).__name__,
                "publication_type": publication_type,
            }
        }
        try:
            file_manager.save_json(error_data, STEP_APPRAISAL, status="failed")
        except Exception:
            pass

        _call_progress_callback(
            progress_callback,
            STEP_APPRAISAL,
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def run_appraisal_validation_step(
    appraisal_result: dict[str, Any],
    extraction_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """Run appraisal validation step of the pipeline."""
    console.print("[bold cyan]Appraisal Validation[/bold cyan]")

    start_time = time.time()
    _call_progress_callback(progress_callback, STEP_APPRAISAL_VALIDATION, "starting", {})

    appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)

    try:
        validation_prompt = load_appraisal_validation_prompt()
        appraisal_schema = load_schema("appraisal")
        validation_report_schema = load_schema("appraisal_validation")

        context = f"""APPRAISAL_JSON:
{json.dumps(appraisal_clean, indent=2)}

EXTRACTION_JSON (for evidence checking):
{json.dumps(extraction_clean, indent=2)}

APPRAISAL_SCHEMA:
{json.dumps(appraisal_schema, indent=2)}"""

        console.print(
            "[dim]Validating appraisal for logical consistency, completeness, evidence support...[/dim]"
        )

        validation_result = llm.generate_json_with_schema(
            schema=validation_report_schema,
            system_prompt=validation_prompt,
            prompt=context,
            schema_name="appraisal_validation",
        )

        console.print("[green]+ Appraisal validation completed[/green]")

        elapsed = time.time() - start_time
        validation_result["_pipeline_metadata"] = {
            "step": "appraisal_validation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed,
            "llm_provider": _get_provider_name(llm),
            "model_used": validation_result.get("_metadata", {}).get("model"),
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
            "validation_passed": validation_result.get("validation_summary", {}).get(
                "overall_status"
            )
            == "passed",
        }

        _call_progress_callback(
            progress_callback,
            STEP_APPRAISAL_VALIDATION,
            "completed",
            {
                "result": validation_result,
                "elapsed_seconds": elapsed,
                "validation_status": validation_result.get("validation_summary", {}).get(
                    "overall_status"
                ),
            },
        )

        return validation_result

    except (PromptLoadError, SchemaLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]X Appraisal validation error: {e}[/red]")

        _call_progress_callback(
            progress_callback,
            STEP_APPRAISAL_VALIDATION,
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def run_appraisal_correction_step(
    appraisal_result: dict[str, Any],
    validation_result: dict[str, Any],
    extraction_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """Run appraisal correction step of the pipeline."""
    console.print("[bold cyan]Appraisal Correction[/bold cyan]")

    start_time = time.time()
    validation_status = validation_result.get("validation_summary", {}).get("overall_status")

    _call_progress_callback(
        progress_callback,
        "appraisal_correction",
        "starting",
        {"validation_status": validation_status},
    )

    appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)
    validation_clean = _strip_metadata_for_pipeline(validation_result)
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)

    try:
        correction_prompt = load_appraisal_correction_prompt()
        appraisal_schema = load_schema("appraisal")

        context = f"""VALIDATION_REPORT:
{json.dumps(validation_clean, indent=2)}

ORIGINAL_APPRAISAL:
{json.dumps(appraisal_clean, indent=2)}

EXTRACTION_JSON (for re-checking evidence):
{json.dumps(extraction_clean, indent=2)}

APPRAISAL_SCHEMA:
{json.dumps(appraisal_schema, indent=2)}"""

        console.print("[dim]Correcting appraisal based on validation issues...[/dim]")

        corrected_appraisal = llm.generate_json_with_schema(
            schema=appraisal_schema,
            system_prompt=correction_prompt,
            prompt=context,
            schema_name="appraisal_correction",
        )

        console.print("[green]+ Appraisal correction completed[/green]")

        elapsed = time.time() - start_time
        corrected_appraisal["_pipeline_metadata"] = {
            "step": "appraisal_correction",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed,
            "llm_provider": _get_provider_name(llm),
            "model_used": corrected_appraisal.get("_metadata", {}).get("model"),
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
            "validation_status_before_correction": validation_status,
        }

        _call_progress_callback(
            progress_callback,
            "appraisal_correction",
            "completed",
            {"result": corrected_appraisal, "elapsed_seconds": elapsed},
        )

        return corrected_appraisal

    except (PromptLoadError, SchemaLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]X Appraisal correction error: {e}[/red]")

        _call_progress_callback(
            progress_callback,
            "appraisal_correction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def run_appraisal_single_pass(
    extraction_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm_provider: str,
    file_manager: PipelineFileManager,
    quality_thresholds: dict | None = None,
    progress_callback: Callable[[str, str, dict], None] | None = None,
) -> dict[str, Any]:
    """Run a single appraisal + validation cycle without iterative correction."""
    console.print("\n[bold magenta]=== CRITICAL APPRAISAL (Single Pass) ===[/bold magenta]\n")

    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")
    if not publication_type:
        raise ValueError("Classification result missing publication_type")

    if quality_thresholds is None:
        quality_thresholds = APPRAISAL_QUALITY_THRESHOLDS

    llm = get_llm_provider(llm_provider)

    appraisal = run_appraisal_step(
        extraction_result=extraction_result,
        publication_type=publication_type,
        llm=llm,
        file_manager=file_manager,
        progress_callback=progress_callback,
    )

    validation = run_appraisal_validation_step(
        appraisal_result=appraisal,
        extraction_result=extraction_result,
        llm=llm,
        file_manager=file_manager,
        progress_callback=progress_callback,
    )

    metrics = _extract_appraisal_metrics(validation)
    iteration_record = {
        "iteration_num": 0,
        "appraisal": appraisal,
        "validation": validation,
        "metrics": metrics,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    file_manager.save_json(appraisal, STEP_APPRAISAL)
    file_manager.save_json(validation, STEP_APPRAISAL_VALIDATION)
    file_manager.save_best_appraisal(appraisal, validation)

    summary = validation.get("validation_summary", {})
    final_status = summary.get("overall_status", "single_pass")

    console.print(
        f"[cyan]Single-pass appraisal complete. Status: {final_status}, "
        f"Quality: {metrics['quality_score']:.2f}[/cyan]"
    )

    return {
        "best_appraisal": appraisal,
        "best_validation": validation,
        "best_iteration": 0,
        "iterations": [iteration_record],
        "final_status": final_status,
        "iteration_count": 1,
        "improvement_trajectory": [metrics["quality_score"]],
        "iterative_mode": "single_pass",
    }


def run_appraisal_with_correction(
    extraction_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm_provider: str,
    file_manager: PipelineFileManager,
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    progress_callback: Callable[[str, str, dict], None] | None = None,
) -> dict[str, Any]:
    """
    Run critical appraisal with automatic iterative correction until quality is sufficient.
    """
    console.print(
        "\n[bold magenta]=== CRITICAL APPRAISAL WITH ITERATIVE CORRECTION ===[/bold magenta]\n"
    )

    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")

    if not publication_type:
        raise ValueError("Classification result missing publication_type")

    console.print(f"[blue]Publication type: {publication_type}[/blue]")
    console.print(f"[blue]Max iterations: {max_iterations}[/blue]\n")

    if quality_thresholds is None:
        quality_thresholds = APPRAISAL_QUALITY_THRESHOLDS

    try:
        llm = get_llm_provider(llm_provider)
    except Exception as e:
        console.print(f"[red]X LLM provider error: {e}[/red]")
        raise

    # Step 1: Run initial appraisal (before iterative loop)
    try:
        initial_appraisal = run_appraisal_step(
            extraction_result=extraction_result,
            publication_type=publication_type,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )
    except (UnsupportedPublicationType, PromptLoadError, SchemaLoadError, LLMError) as e:
        console.print(f"[red]X Initial appraisal failed: {e}[/red]")
        raise

    # Step 2: Configure and run iterative validation/correction loop
    config = IterativeLoopConfig(
        metric_type=MetricType.APPRAISAL,
        max_iterations=max_iterations,
        quality_thresholds=APPRAISAL_THRESHOLDS,
        degradation_window=2,
        step_name="APPRAISAL VALIDATION & CORRECTION",
        step_number=4,
        show_banner=False,  # We already printed our own banner
    )

    # Define callbacks that capture the required context
    def validate_fn(appraisal_result: dict) -> dict:
        return run_appraisal_validation_step(
            appraisal_result=appraisal_result,
            extraction_result=extraction_result,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )

    def correct_fn(appraisal_result: dict, validation_result: dict) -> dict:
        corrected = run_appraisal_correction_step(
            appraisal_result=appraisal_result,
            validation_result=validation_result,
            extraction_result=extraction_result,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )
        return _strip_metadata_for_pipeline(corrected)

    def save_iteration_fn(
        iteration_num: int, appraisal_result: dict, validation_result: dict
    ) -> tuple:
        return file_manager.save_appraisal_iteration(
            iteration=iteration_num,
            appraisal_result=appraisal_result,
            validation_result=validation_result,
        )

    def save_best_fn(appraisal_result: dict, validation_result: dict) -> tuple:
        return file_manager.save_best_appraisal(appraisal_result, validation_result)

    def regenerate_initial_fn() -> dict:
        """Regenerate the initial appraisal if it fails schema validation."""
        return run_appraisal_step(
            extraction_result=extraction_result,
            publication_type=publication_type,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )

    def save_failed_fn(appraisal_result: dict, validation_result: dict) -> tuple:
        """Save failed appraisal and validation for debugging."""
        appraisal_path = file_manager.save_json(appraisal_result, "appraisal", status="failed")
        validation_path = file_manager.save_json(
            validation_result, "appraisal_validation", status="failed"
        )
        return (appraisal_path, validation_path)

    runner = IterativeLoopRunner(
        config=config,
        initial_result=initial_appraisal,
        validate_fn=validate_fn,
        correct_fn=correct_fn,
        save_iteration_fn=save_iteration_fn,
        save_best_fn=save_best_fn,
        regenerate_initial_fn=regenerate_initial_fn,
        save_failed_fn=save_failed_fn,
        progress_callback=progress_callback,
        console_instance=console,
    )

    loop_result = runner.run()

    # Step 3: Convert IterativeLoopResult to expected dict format
    return loop_result.to_dict(result_key="best_appraisal")


# Backward compatibility aliases
_run_appraisal_step = run_appraisal_step
_run_appraisal_validation_step = run_appraisal_validation_step
_run_appraisal_correction_step = run_appraisal_correction_step
