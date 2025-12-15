# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Report step module.

Handles report generation with iterative correction and PDF/markdown rendering.
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
    load_report_correction_prompt,
    load_report_generation_prompt,
    load_report_validation_prompt,
)
from ...rendering.latex_renderer import LatexRenderError, render_report_to_pdf
from ...rendering.markdown_renderer import render_report_to_markdown
from ...rendering.weasy_renderer import WeasyRendererError, render_report_with_weasyprint
from ...schemas_loader import SchemaLoadError, load_schema
from ..file_manager import PipelineFileManager
from ..iterative import detect_quality_degradation as _detect_quality_degradation_new
from ..iterative import select_best_iteration as _select_best_iteration_new
from ..quality import MetricType, extract_report_metrics_as_dict
from ..quality.thresholds import REPORT_THRESHOLDS
from ..utils import _call_progress_callback, _get_provider_name, _strip_metadata_for_pipeline
from ..version import get_pipeline_version

console = Console()

# Step name constant
STEP_REPORT_GENERATION = "report_generation"

# Quality thresholds for report iterative correction loop
# Derived from centralized thresholds for consistency
REPORT_QUALITY_THRESHOLDS = {
    "completeness_score": REPORT_THRESHOLDS.completeness_score,
    "accuracy_score": REPORT_THRESHOLDS.accuracy_score,
    "cross_reference_consistency_score": REPORT_THRESHOLDS.cross_reference_consistency_score,
    "data_consistency_score": REPORT_THRESHOLDS.data_consistency_score,
    "schema_compliance_score": REPORT_THRESHOLDS.schema_compliance_score,
    "critical_issues": REPORT_THRESHOLDS.critical_issues,
}


# Alias for backward compatibility - delegate to centralized version module
_get_pipeline_version = get_pipeline_version


# Alias for backward compatibility - delegate to quality module
_extract_report_metrics = extract_report_metrics_as_dict


def _detect_quality_degradation(iterations: list[dict], window: int = 2) -> bool:
    """Detect if quality has been degrading for the last N iterations."""
    return _detect_quality_degradation_new(iterations, window, MetricType.REPORT)


def _select_best_report_iteration(iterations: list[dict]) -> dict:
    """Select the iteration with the highest quality score."""
    return _select_best_iteration_new(iterations, MetricType.REPORT)


def is_report_quality_sufficient(
    validation_result: dict | None, thresholds: dict | None = None
) -> bool:
    """Check if report validation quality meets thresholds."""
    if thresholds is None:
        thresholds = REPORT_QUALITY_THRESHOLDS

    if validation_result is None:
        return False

    summary = validation_result.get("validation_summary", {})
    if not summary:
        return False

    def safe_score(key: str, default: float = 0.0) -> float:
        val = summary.get(key, default)
        return val if isinstance(val, int | float) else default

    return (
        safe_score("completeness_score") >= thresholds["completeness_score"]
        and safe_score("accuracy_score") >= thresholds["accuracy_score"]
        and safe_score("cross_reference_consistency_score")
        >= thresholds["cross_reference_consistency_score"]
        and safe_score("data_consistency_score") >= thresholds["data_consistency_score"]
        and safe_score("schema_compliance_score") >= thresholds["schema_compliance_score"]
        and safe_score("critical_issues", 999) <= thresholds["critical_issues"]
    )


def run_report_generation(
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm_provider: str,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Generate a structured report from extraction and appraisal data (single-pass)."""
    console.print("\n[bold cyan]=== REPORT GENERATION (Phase 2 - Single Pass) ===[/bold cyan]\n")

    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")
    if not publication_type:
        raise ValueError("Classification result missing publication_type")

    if progress_callback:
        progress_callback(
            STEP_REPORT_GENERATION,
            "started",
            {"publication_type": publication_type, "iteration": 0},
        )

    console.print("[yellow]Loading report generation prompt...[/yellow]")
    try:
        report_prompt = load_report_generation_prompt()
    except PromptLoadError as e:
        console.print(f"[red]X Failed to load report generation prompt: {e}[/red]")
        raise

    console.print("[yellow]Loading report schema...[/yellow]")
    try:
        report_schema = load_schema("report")
    except SchemaLoadError as e:
        console.print(f"[red]X Failed to load report schema: {e}[/red]")
        raise

    extraction_clean = _strip_metadata_for_pipeline(extraction_result)
    appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)

    generation_timestamp = datetime.now(timezone.utc).isoformat()
    pipeline_version = _get_pipeline_version()
    report_schema_str = json.dumps(report_schema, indent=2)

    prompt_context = f"""CLASSIFICATION_JSON:
{json.dumps(classification_clean, indent=2)}

EXTRACTION_JSON:
{json.dumps(extraction_clean, indent=2)}

APPRAISAL_JSON:
{json.dumps(appraisal_clean, indent=2)}

LANGUAGE: {language}
GENERATION_TIMESTAMP: {generation_timestamp}
PIPELINE_VERSION: {pipeline_version}

REPORT_SCHEMA:
{report_schema_str}
"""

    llm = get_llm_provider(llm_provider)

    console.print(f"[yellow]Generating report via {llm_provider}...[/yellow]")
    console.print(f"[dim]Publication type: {publication_type}, Language: {language}[/dim]")

    try:
        from ...config import llm_settings

        report_json = llm.generate_json_with_schema(
            schema=report_schema,
            system_prompt=report_prompt,
            prompt=prompt_context,
            schema_name="report_generation",
            reasoning_effort=llm_settings.reasoning_effort_report,
        )
    except LLMError as e:
        console.print(f"[red]X LLM call failed: {e}[/red]")
        if progress_callback:
            progress_callback(STEP_REPORT_GENERATION, "failed", {"error": str(e)})
        raise

    console.print("[yellow]Validating report against schema...[/yellow]")
    from ...validation import validate_with_schema

    report_clean = _strip_metadata_for_pipeline(report_json)
    is_valid, validation_errors = validate_with_schema(report_clean, report_schema, strict=True)
    if not is_valid:
        error_msg = "\n".join(validation_errors)
        console.print(f"[red]X Report schema validation failed:\n{error_msg}[/red]")
        if progress_callback:
            progress_callback(
                STEP_REPORT_GENERATION, "failed", {"error": f"Schema validation: {error_msg}"}
            )
        raise SchemaLoadError(f"Report schema validation failed:\n{error_msg}")

    console.print("[green]+ Report schema validation passed[/green]")

    console.print("[yellow]Saving report iteration 0...[/yellow]")
    report_path, _ = file_manager.save_report_iteration(
        iteration=0, report_result=report_json, validation_result=None
    )
    console.print(f"[green]+ Report saved: {report_path.name}[/green]")

    timestamp = datetime.now(timezone.utc).isoformat()
    result = {
        "report": report_json,
        "iteration": 0,
        "status": "completed",
        "_pipeline_metadata": {
            "step": STEP_REPORT_GENERATION,
            "timestamp": timestamp,
            "llm_provider": llm_provider,
            "publication_type": publication_type,
            "phase": "phase_2_single_pass",
        },
    }

    if progress_callback:
        progress_callback(
            STEP_REPORT_GENERATION,
            "completed",
            {"iteration": 0, "file": report_path.name},
        )

    console.print("\n[bold green]+ Report generation completed successfully[/bold green]\n")

    return result


def run_report_validation_step(
    report_result: dict[str, Any],
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """Run report validation step of the pipeline."""
    console.print("[bold cyan]Report Validation[/bold cyan]")

    start_time = time.time()
    _call_progress_callback(progress_callback, "report_validation", "starting", {})

    report_clean = _strip_metadata_for_pipeline(report_result)
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)
    appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)

    try:
        validation_prompt = load_report_validation_prompt()
        validation_schema = load_schema("report_validation")

        context = f"""REPORT_JSON:
{json.dumps(report_clean, indent=2)}

EXTRACTION_JSON (for data accuracy checking):
{json.dumps(extraction_clean, indent=2)}

APPRAISAL_JSON (for quality assessment cross-checking):
{json.dumps(appraisal_clean, indent=2)}"""

        console.print("[dim]Validating report for completeness, accuracy, consistency...[/dim]")

        validation_result = llm.generate_json_with_schema(
            schema=validation_schema,
            system_prompt=validation_prompt,
            prompt=context,
            schema_name="report_validation",
        )

        console.print("[green]+ Report validation completed[/green]")

        elapsed = time.time() - start_time
        validation_result["_pipeline_metadata"] = {
            "step": "report_validation",
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
            "report_validation",
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
        console.print(f"[red]X Report validation error: {e}[/red]")

        _call_progress_callback(
            progress_callback,
            "report_validation",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def run_report_correction_step(
    report_result: dict[str, Any],
    validation_result: dict[str, Any],
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """Run report correction step of the pipeline."""
    console.print("[bold cyan]Report Correction[/bold cyan]")

    start_time = time.time()
    validation_status = validation_result.get("validation_summary", {}).get("overall_status")

    _call_progress_callback(
        progress_callback,
        "report_correction",
        "starting",
        {"validation_status": validation_status},
    )

    report_clean = _strip_metadata_for_pipeline(report_result)
    validation_clean = _strip_metadata_for_pipeline(validation_result)
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)
    appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)

    try:
        correction_prompt = load_report_correction_prompt()
        report_schema = load_schema("report")

        context = f"""VALIDATION_REPORT:
{json.dumps(validation_clean, indent=2)}

ORIGINAL_REPORT:
{json.dumps(report_clean, indent=2)}

EXTRACTION_JSON (for re-checking data accuracy):
{json.dumps(extraction_clean, indent=2)}

APPRAISAL_JSON (for re-checking quality assessments):
{json.dumps(appraisal_clean, indent=2)}

REPORT_SCHEMA:
{json.dumps(report_schema, indent=2)}"""

        console.print("[dim]Correcting report based on validation issues...[/dim]")

        corrected_report = llm.generate_json_with_schema(
            schema=report_schema,
            system_prompt=correction_prompt,
            prompt=context,
            schema_name="report_correction",
        )

        console.print("[green]+ Report correction completed[/green]")

        elapsed = time.time() - start_time
        corrected_report["_pipeline_metadata"] = {
            "step": "report_correction",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed,
            "llm_provider": _get_provider_name(llm),
            "model_used": corrected_report.get("_metadata", {}).get("model"),
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
            "validation_status_before_correction": validation_status,
        }

        _call_progress_callback(
            progress_callback,
            "report_correction",
            "completed",
            {"result": corrected_report, "elapsed_seconds": elapsed},
        )

        return corrected_report

    except (PromptLoadError, SchemaLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]X Report correction error: {e}[/red]")

        _call_progress_callback(
            progress_callback,
            "report_correction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def run_report_with_correction(
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm_provider: str,
    file_manager: PipelineFileManager,
    language: str = "en",
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    compile_pdf: bool = True,
    enable_figures: bool = True,
    renderer: str = "latex",
    progress_callback: Callable[[str, str, dict], None] | None = None,
) -> dict[str, Any]:
    """Run report generation with automatic iterative correction until quality is sufficient."""
    console.print(
        "\n[bold magenta]=== REPORT GENERATION WITH ITERATIVE CORRECTION ===[/bold magenta]\n"
    )

    console.print(f"[blue]Report language: {language}[/blue]")
    console.print(f"[blue]Max iterations: {max_iterations}[/blue]\n")

    if quality_thresholds is None:
        quality_thresholds = REPORT_QUALITY_THRESHOLDS

    try:
        llm = get_llm_provider(llm_provider)
    except Exception as e:
        console.print(f"[red]X LLM provider error: {e}[/red]")
        raise

    # Dependency gating
    console.print("\n[bold]Checking upstream dependencies...[/bold]")

    extraction_quality = extraction_result.get("quality_score")
    if extraction_quality is None:
        validation_summary = extraction_result.get("validation_summary", {})
        extraction_quality = validation_summary.get("quality_score")

    if extraction_quality is not None:
        console.print(f"  Extraction quality: {extraction_quality:.2f}")
        if extraction_quality < 0.70:
            return {
                "_pipeline_metadata": {
                    "step": STEP_REPORT_GENERATION,
                    "status": "blocked",
                    "reason": "extraction_quality_low",
                },
                "status": "blocked",
                "message": "Extraction quality insufficient for report generation",
                "extraction_quality": extraction_quality,
            }

    appraisal_final_status = appraisal_result.get("final_status", appraisal_result.get("status"))
    risk_of_bias = appraisal_result.get("risk_of_bias")

    blocking_statuses = {"failed", "failed_schema_validation", "failed_llm_error"}
    if appraisal_final_status in blocking_statuses or risk_of_bias is None:
        return {
            "_pipeline_metadata": {
                "step": STEP_REPORT_GENERATION,
                "status": "blocked",
                "reason": "appraisal_failed",
            },
            "status": "blocked",
            "message": "Appraisal data missing or incomplete",
        }

    console.print("  [green]+ Dependency checks passed[/green]")

    iterations = []
    current_report = None
    current_validation = None
    iteration_num = 0

    while iteration_num <= max_iterations:
        console.print(f"\n[bold cyan]--- Iteration {iteration_num} ---[/bold cyan]")

        try:
            if iteration_num == 0:
                result = run_report_generation(
                    extraction_result=extraction_result,
                    appraisal_result=appraisal_result,
                    classification_result=classification_result,
                    llm_provider=llm_provider,
                    file_manager=file_manager,
                    progress_callback=progress_callback,
                    language=language,
                )
                current_report = result["report"]

            current_validation = run_report_validation_step(
                report_result=current_report,
                extraction_result=extraction_result,
                appraisal_result=appraisal_result,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
            )

            report_file, validation_file = file_manager.save_report_iteration(
                iteration=iteration_num,
                report_result=current_report,
                validation_result=current_validation,
            )
            console.print(f"[dim]Saved: {report_file.name}[/dim]")
            if validation_file:
                console.print(f"[dim]Saved: {validation_file.name}[/dim]")

            metrics = _extract_report_metrics(current_validation)

            iteration_data = {
                "iteration_num": iteration_num,
                "report": current_report,
                "validation": current_validation,
                "metrics": metrics,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            iterations.append(iteration_data)

            console.print(f"\n[bold]Quality Scores (Iteration {iteration_num}):[/bold]")
            console.print(f"  Completeness:          {metrics['completeness_score']:.2f}")
            console.print(f"  Accuracy:              {metrics['accuracy_score']:.2f}")
            console.print(
                f"  Cross-Ref Consistency: {metrics['cross_reference_consistency_score']:.2f}"
            )
            console.print(f"  Data Consistency:      {metrics['data_consistency_score']:.2f}")
            console.print(f"  Schema Compliance:     {metrics['schema_compliance_score']:.2f}")
            console.print(f"  [bold]Quality Score:         {metrics['quality_score']:.2f}[/bold]")
            console.print(f"  Critical Issues:       {metrics['critical_issues']}")

            if len(iterations) > 1:
                prev_score = iterations[-2]["metrics"]["quality_score"]
                delta = metrics["quality_score"] - prev_score
                if delta > 0:
                    symbol, color = "^", "green"
                elif delta < 0:
                    symbol, color = "v", "red"
                else:
                    symbol, color = "->", "yellow"
                console.print(
                    f"  [{color}]Improvement: {symbol} {delta:+.3f} (prev: {prev_score:.2f})[/{color}]"
                )

            if is_report_quality_sufficient(current_validation, quality_thresholds):
                console.print(
                    f"\n[green]+ Quality sufficient at iteration {iteration_num}! Stopping.[/green]"
                )

                file_manager.save_best_report(current_report, current_validation)

                # Render PDF/markdown
                render_dirs = {}
                render_root = file_manager.tmp_dir / "render"
                try:
                    if renderer == "weasyprint":
                        render_dirs = render_report_with_weasyprint(current_report, render_root)
                    else:
                        render_dirs = render_report_to_pdf(
                            current_report,
                            render_root,
                            compile_pdf=compile_pdf,
                            enable_figures=enable_figures,
                        )
                except (LatexRenderError, WeasyRendererError) as e:
                    console.print(f"[yellow]! Failed to render report: {e}[/yellow]")
                    render_dirs = {"error": str(e), "renderer": renderer}
                except Exception as e:
                    console.print(f"[yellow]! Failed to render report: {e}[/yellow]")
                    render_dirs = {}

                try:
                    md_path = render_report_to_markdown(current_report, render_root)
                    render_dirs["markdown"] = md_path
                except Exception as e:
                    console.print(f"[yellow]! Failed to write markdown: {e}[/yellow]")

                return {
                    "best_report": current_report,
                    "best_validation": current_validation,
                    "best_iteration": iteration_num,
                    "iterations": iterations,
                    "final_status": "passed",
                    "iteration_count": iteration_num + 1,
                    "improvement_trajectory": [it["metrics"]["quality_score"] for it in iterations],
                    "rendered_paths": render_dirs,
                }

            if _detect_quality_degradation(iterations, window=2):
                console.print(
                    "\n[yellow]! Quality degrading - stopping early and selecting best[/yellow]"
                )

                best = _select_best_report_iteration(iterations)
                file_manager.save_best_report(best["report"], best["validation"])

                return {
                    "best_report": best["report"],
                    "best_validation": best["validation"],
                    "best_iteration": best["iteration_num"],
                    "iterations": iterations,
                    "final_status": "early_stopped_degradation",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": [it["metrics"]["quality_score"] for it in iterations],
                }

            if iteration_num >= max_iterations:
                console.print(
                    f"\n[yellow]! Max iterations ({max_iterations}) reached - selecting best[/yellow]"
                )

                best = _select_best_report_iteration(iterations)
                file_manager.save_best_report(best["report"], best["validation"])

                return {
                    "best_report": best["report"],
                    "best_validation": best["validation"],
                    "best_iteration": best["iteration_num"],
                    "iterations": iterations,
                    "final_status": "max_iterations_reached",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": [it["metrics"]["quality_score"] for it in iterations],
                }

            console.print(
                f"\n[yellow]Quality insufficient (iteration {iteration_num}). Running correction...[/yellow]"
            )

            current_report = run_report_correction_step(
                report_result=current_report,
                validation_result=current_validation,
                extraction_result=extraction_result,
                appraisal_result=appraisal_result,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
            )

            iteration_num += 1

        except (PromptLoadError, SchemaLoadError) as e:
            console.print(f"\n[red]X Fatal error: {e}[/red]")

            if iterations:
                best = _select_best_report_iteration(iterations)
                file_manager.save_best_report(best["report"], best["validation"])

                return {
                    "best_report": best["report"],
                    "best_validation": best["validation"],
                    "best_iteration": best["iteration_num"],
                    "iterations": iterations,
                    "final_status": "failed",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": [it["metrics"]["quality_score"] for it in iterations],
                    "error": str(e),
                }
            raise

        except LLMError as e:
            console.print(f"\n[red]X LLM error at iteration {iteration_num}: {e}[/red]")

            if iterations:
                best = _select_best_report_iteration(iterations)
                file_manager.save_best_report(best["report"], best["validation"])

                return {
                    "best_report": best["report"],
                    "best_validation": best["validation"],
                    "best_iteration": best["iteration_num"],
                    "iterations": iterations,
                    "final_status": "failed_llm_error",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": [it["metrics"]["quality_score"] for it in iterations],
                    "error": str(e),
                }
            raise

    raise RuntimeError("Report loop exited unexpectedly")


# Backward compatibility aliases
_run_report_validation_step = run_report_validation_step
_run_report_correction_step = run_report_correction_step
