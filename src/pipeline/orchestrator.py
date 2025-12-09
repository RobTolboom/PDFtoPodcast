# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""

Five-step PDF extraction + appraisal + reporting pipeline orchestration.

This module contains the main pipeline orchestration logic that coordinates
the six primary steps: Classification → Extraction → Validation & Correction → Appraisal → Report Generation → Podcast Generation.

Pipeline Steps:
    1. Classification - Identify publication type and extract metadata
    2. Extraction - Schema-based structured data extraction
    3. Validation & Correction - Iterative validation with automatic correction
    4. Appraisal - Critical appraisal (risk of bias, GRADE, applicability)
    5. Report Generation - Generate structured report and render to PDF
    6. Podcast Generation - Generate audio script from extraction and appraisal

Public APIs:
    - run_single_step(): Execute individual pipeline steps with dependency validation
      Enables step-by-step execution with UI updates between steps.

    - run_full_pipeline(): Execute all steps sequentially
      Runs the complete pipeline in one call without intermediate updates.

Step-by-Step Execution Example:
    >>> from pathlib import Path
    >>> from src.pipeline.orchestrator import run_single_step
    >>> from src.pipeline.file_manager import PipelineFileManager
    >>>
    >>> pdf_path = Path("paper.pdf")
    >>> fm = PipelineFileManager(pdf_path)
    >>>
    >>> # Step 1: Classification
    >>> result1 = run_single_step("classification", pdf_path, None, "openai", fm)
    >>>
    >>> # Step 2: Extraction (requires classification)
    >>> result2 = run_single_step(
    ...     "extraction", pdf_path, None, "openai", fm,
    ...     previous_results={"classification": result1}
    ... )
    >>>
    >>> # Step 3: Validation (requires classification + extraction)
    >>> result3 = run_single_step(
    ...     "validation", pdf_path, None, "openai", fm,
    ...     previous_results={"classification": result1, "extraction": result2}
    ... )

PDF Upload Strategy:
    All LLM steps use direct PDF upload (no text extraction) to preserve:
    - Tables and figures (critical for medical research data)
    - Images and charts (visual data representation)
    - Complex formatting and layout information
    - Complete document structure and context

    Cost: ~1,500-3,000 tokens per page (3-6x more than text extraction)
    Benefit: Complete data fidelity - no loss of tables, images, or formatting
"""

import functools
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Console

from .file_manager import PipelineFileManager
from .iterative import detect_quality_degradation as _detect_quality_degradation_new
from .iterative import select_best_iteration as _select_best_iteration_new
from .podcast_logic import run_podcast_generation
from .quality import (
    MetricType,
    extract_appraisal_metrics_as_dict,
    extract_extraction_metrics_as_dict,
    extract_report_metrics_as_dict,
)
from .steps.appraisal import (
    UnsupportedPublicationType,  # noqa: F401 - re-export for backward compat
    run_appraisal_single_pass,
    run_appraisal_with_correction,
)
from .steps.appraisal import _get_appraisal_prompt_name as _get_appraisal_prompt_name_impl
from .steps.appraisal import (
    is_appraisal_quality_sufficient as _is_appraisal_quality_sufficient,
)
from .steps.classification import run_classification_step as _run_classification_step_impl
from .steps.extraction import run_extraction_step as _run_extraction_step_impl
from .steps.report import (
    is_report_quality_sufficient as _is_report_quality_sufficient,
)
from .steps.report import run_report_generation, run_report_with_correction
from .steps.validation import (
    is_quality_sufficient as _is_quality_sufficient,
)
from .steps.validation import (
    run_correction_step as _run_correction_step_impl,
)
from .steps.validation import (
    run_validation_step as _run_validation_step_impl,
)
from .steps.validation import (
    run_validation_with_correction as run_validation_with_correction_impl,
)
from .utils import (
    _call_progress_callback,
    _strip_metadata_for_pipeline,
    check_breakpoint,
)

# Pipeline step name constants
STEP_CLASSIFICATION = "classification"
STEP_EXTRACTION = "extraction"
STEP_VALIDATION = "validation"
STEP_CORRECTION = "correction"
STEP_VALIDATION_CORRECTION = "validation_correction"
STEP_APPRAISAL = "appraisal"
STEP_APPRAISAL_VALIDATION = "appraisal_validation"
STEP_REPORT_GENERATION = "report_generation"
STEP_PODCAST_GENERATION = "podcast_generation"

# Default pipeline steps (validation_correction replaces separate validation+correction)
ALL_PIPELINE_STEPS = [
    STEP_CLASSIFICATION,
    STEP_EXTRACTION,
    STEP_VALIDATION_CORRECTION,
    STEP_APPRAISAL,  # Critical appraisal after extraction validation
    STEP_REPORT_GENERATION,  # Report generation after appraisal
    STEP_PODCAST_GENERATION,  # Podcast generation after report
]
# Note: STEP_VALIDATION and STEP_CORRECTION remain available for CLI backward compatibility

STEP_DISPLAY_NAMES = {
    STEP_CLASSIFICATION: "Step 1 - Classification",
    STEP_EXTRACTION: "Step 2 - Extraction",
    STEP_VALIDATION_CORRECTION: "Step 3 - Validation & Correction",
    STEP_APPRAISAL: "Step 4 - Appraisal",
    STEP_REPORT_GENERATION: "Step 5 - Report Generation",
    STEP_PODCAST_GENERATION: "Step 6 - Podcast Generation",
}


@functools.cache
def _get_pipeline_version() -> str:
    """
    Retrieve pipeline version from installed package or pyproject.toml.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("pdftopodcast")
    except ImportError:
        pass
    except PackageNotFoundError:
        pass

    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject_path.exists():
        in_project_section = False
        for line in pyproject_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                in_project_section = stripped == "[project]"
                continue
            if in_project_section and stripped.startswith("version"):
                match = re.search(r'version\s*=\s*"([^"]+)"', stripped)
                if match:
                    _PIPELINE_VERSION_CACHE = match.group(1)
                    return _PIPELINE_VERSION_CACHE

    _PIPELINE_VERSION_CACHE = "0.0.0"
    return _PIPELINE_VERSION_CACHE


# Default quality thresholds for iterative correction loop (extraction)
DEFAULT_QUALITY_THRESHOLDS = {
    "completeness_score": 0.90,  # ≥90% of PDF data extracted
    "accuracy_score": 0.95,  # ≥95% correct data (max 5% errors)
    "schema_compliance_score": 0.95,  # ≥95% schema compliant
    "critical_issues": 0,  # Absolutely no critical errors
}

# Quality thresholds for appraisal iterative correction loop
APPRAISAL_QUALITY_THRESHOLDS = {
    "logical_consistency_score": 0.90,  # ≥90% logical consistency (overall = worst domain)
    "completeness_score": 0.85,  # ≥85% completeness (all domains, outcomes)
    "evidence_support_score": 0.90,  # ≥90% evidence support (rationales match extraction)
    "schema_compliance_score": 0.95,  # ≥95% schema compliance (enums, required fields)
    "critical_issues": 0,  # Absolutely no critical errors
}

# Quality thresholds for report iterative correction loop
REPORT_QUALITY_THRESHOLDS = {
    "completeness_score": 0.85,  # ≥85% completeness (all core sections present)
    "accuracy_score": 0.95,  # ≥95% accuracy (data correctness paramount)
    "cross_reference_consistency_score": 0.90,  # ≥90% cross-ref consistency (table/figure refs valid)
    "data_consistency_score": 0.90,  # ≥90% data consistency (bottom-line matches results)
    "schema_compliance_score": 0.95,  # ≥95% schema compliance (enums, required fields)
    "critical_issues": 0,  # Absolutely no critical errors
}

# Final status codes for iterative loop results
FINAL_STATUS_CODES = {
    "passed": "Quality thresholds met",
    "max_iterations_reached": "Maximum iterations reached, using best result",
    "early_stopped_degradation": "Stopped due to quality degradation",
    "failed_schema_validation": "Schema validation failed",
    "failed_llm_error": "LLM API error after retries",
    "failed_invalid_json": "Correction produced invalid JSON",
    "failed_unexpected_error": "Unexpected error occurred",
}

console = Console()


# UnsupportedPublicationType is imported from steps.appraisal

# Alias for backward compatibility - delegate to steps.appraisal module
_get_appraisal_prompt_name = _get_appraisal_prompt_name_impl


# Aliases for backward compatibility - delegate to quality module
_extract_appraisal_metrics = extract_appraisal_metrics_as_dict
_extract_report_metrics = extract_report_metrics_as_dict
_extract_metrics = extract_extraction_metrics_as_dict

# Aliases for backward compatibility - delegate to step modules
is_quality_sufficient = _is_quality_sufficient
is_appraisal_quality_sufficient = _is_appraisal_quality_sufficient
is_report_quality_sufficient = _is_report_quality_sufficient
_detect_quality_degradation = _detect_quality_degradation_new


def _select_best_iteration(iterations: list[dict]) -> dict:
    """Select best extraction iteration. Delegates to iterative module."""
    return _select_best_iteration_new(iterations, MetricType.EXTRACTION)


def _select_best_appraisal_iteration(iterations: list[dict]) -> dict:
    """Select best appraisal iteration. Delegates to iterative module."""
    return _select_best_iteration_new(iterations, MetricType.APPRAISAL)


def _select_best_report_iteration(iterations: list[dict]) -> dict:
    """Select best report iteration. Delegates to iterative module."""
    return _select_best_iteration_new(iterations, MetricType.REPORT)


# Alias - delegates to steps.extraction module
_run_extraction_step = _run_extraction_step_impl


# Alias - delegates to steps.validation module
_run_validation_step = _run_validation_step_impl


# Alias - delegates to steps.validation module
_run_correction_step = _run_correction_step_impl


def _print_iteration_summary(
    file_manager: PipelineFileManager, iterations: list[dict], best_iteration: int
) -> None:
    """Print summary of all saved iterations with best selection."""
    console.print("\n[bold]Saved Extraction Iterations:[/bold]")
    for it_data in iterations:
        it_num = it_data["iteration_num"]
        extraction_file = file_manager.get_filename("extraction", iteration_number=it_num)
        status_symbol = "✅" if extraction_file.exists() else "⚠️"
        console.print(f"  {status_symbol} Iteration {it_num}: {extraction_file.name}")

    best_file = file_manager.get_filename("extraction", status="best")
    if best_file.exists():
        console.print(f"  🏆 Best: {best_file.name} (iteration {best_iteration})")


# Alias - delegates to steps.validation module
run_validation_with_correction = run_validation_with_correction_impl


def _should_run_step(step_name: str, steps_to_run: list[str] | None) -> bool:
    """
    Check if step should be executed based on steps_to_run filter.

    Args:
        step_name: Step to check ("classification", "extraction", "validation", "correction")
        steps_to_run: Optional list of steps to execute (None = run all steps)

    Returns:
        True if step should run, False if step should be skipped

    Example:
        >>> _should_run_step("validation", ["classification", "extraction"])
        False
        >>> _should_run_step("extraction", None)
        True
    """
    if steps_to_run is None:
        return True  # Backwards compatible: run all steps
    return step_name in steps_to_run


def _validate_step_dependencies(steps_to_run: list[str]) -> None:
    """
    Validate step dependencies to ensure required steps are included.

    Pipeline dependencies:
    - Validation requires extraction (cannot validate without data)
    - Correction requires validation (cannot correct without validation report)
    - Extraction requires classification (cannot extract without knowing type)
    - Appraisal requires classification + extraction (cannot appraise without data and type)

    Args:
        steps_to_run: List of steps to execute

    Raises:
        ValueError: If step dependencies are violated

    Example:
        >>> _validate_step_dependencies(["validation"])  # Missing extraction
        Traceback (most recent call last):
        ...
        ValueError: Validation step requires extraction step
    """
    if STEP_VALIDATION in steps_to_run and STEP_EXTRACTION not in steps_to_run:
        raise ValueError("Validation step requires extraction step")

    if STEP_CORRECTION in steps_to_run and STEP_VALIDATION not in steps_to_run:
        raise ValueError("Correction step requires validation step")

    if STEP_EXTRACTION in steps_to_run and STEP_CLASSIFICATION not in steps_to_run:
        raise ValueError("Extraction step requires classification step")

    if STEP_APPRAISAL in steps_to_run:
        if STEP_CLASSIFICATION not in steps_to_run:
            raise ValueError("Appraisal step requires classification step")
        if STEP_EXTRACTION not in steps_to_run:
            raise ValueError("Appraisal step requires extraction step")

    if STEP_PODCAST_GENERATION in steps_to_run:
        if STEP_APPRAISAL not in steps_to_run:
            raise ValueError("Podcast generation step requires appraisal step")
        if STEP_CLASSIFICATION not in steps_to_run:
            raise ValueError("Podcast generation step requires classification step")
        if STEP_EXTRACTION not in steps_to_run:
            raise ValueError("Podcast generation step requires extraction step")


def _get_next_scheduled_step(current_step: str, steps_to_run: list[str] | None) -> str | None:
    """
    Determine the next scheduled step after the current one.
    """
    try:
        idx = ALL_PIPELINE_STEPS.index(current_step)
    except ValueError:
        return None

    for step in ALL_PIPELINE_STEPS[idx + 1 :]:
        if _should_run_step(step, steps_to_run):
            return step
    return None


def _print_next_step_hint(current_step: str, steps_to_run: list[str] | None) -> None:
    """
    Print a subtle hint about the next step that will run (if any).
    """
    next_step = _get_next_scheduled_step(current_step, steps_to_run)
    if not next_step:
        return

    label = STEP_DISPLAY_NAMES.get(next_step, next_step.title())
    console.print(f"[dim]Next: {label}[/dim]")


def _resolve_primary_output_path(file_manager: PipelineFileManager, step_name: str) -> Path | None:
    """
    Try to resolve the most relevant output file for a step.
    """
    candidates: list[Path] = []
    if step_name == STEP_CLASSIFICATION:
        candidates.append(file_manager.get_filename(STEP_CLASSIFICATION))
    elif step_name == STEP_EXTRACTION:
        candidates.append(file_manager.get_filename("extraction", status="best"))
        candidates.append(file_manager.get_filename("extraction", iteration_number=0))
    elif step_name == STEP_VALIDATION_CORRECTION:
        candidates.append(file_manager.get_filename("validation", status="best"))
        candidates.append(file_manager.get_filename("validation", iteration_number=0))
    elif step_name == STEP_APPRAISAL:
        candidates.append(file_manager.get_filename("appraisal", status="best"))
        candidates.append(file_manager.get_filename("appraisal", iteration_number=0))
        candidates.append(file_manager.get_filename("appraisal"))
    elif step_name == STEP_REPORT_GENERATION:
        candidates.append(file_manager.get_filename("report", status="best"))
        candidates.append(file_manager.get_filename("report", iteration_number=0))
    else:
        candidates.append(file_manager.get_filename(step_name))

    for path in candidates:
        if path.exists():
            return path
    return None


def _format_step_status(step_name: str, results: dict[str, Any], expected_to_run: bool) -> str:
    """
    Convert stored metadata into a human-readable status label.
    """
    result = results.get(step_name)
    if not result:
        return "Skipped" if not expected_to_run else "Not run"

    if step_name == STEP_VALIDATION_CORRECTION:
        status = result.get("final_status", result.get("status", "completed"))
    elif "_pipeline_metadata" in result:
        status = result["_pipeline_metadata"].get("status", result.get("status", "completed"))
    else:
        status = result.get("status", "completed")

    return status.replace("_", " ").title()


def _print_pipeline_summary(
    results: dict[str, Any],
    file_manager: PipelineFileManager,
    steps_to_run: list[str] | None,
) -> None:
    """
    Print a compact summary of each pipeline step and its primary output file.
    """
    console.print("\n[bold green]Pipeline Summary[/bold green]")
    for step in ALL_PIPELINE_STEPS:
        expected = _should_run_step(step, steps_to_run)
        status = _format_step_status(step, results, expected)
        label = STEP_DISPLAY_NAMES.get(step, step.title())
        output_path = _resolve_primary_output_path(file_manager, step)
        if output_path:
            console.print(f"  {label}: {status} ({output_path.name})")
        else:
            console.print(f"  {label}: {status}")


def _finalize_pipeline_results(
    results: dict[str, Any],
    file_manager: PipelineFileManager,
    steps_to_run: list[str] | None,
) -> dict[str, Any]:
    """
    Print final summary before returning pipeline results.
    """
    _print_pipeline_summary(results, file_manager, steps_to_run)
    return results


# Alias - delegates to steps.classification module
_run_classification_step = _run_classification_step_impl


def run_single_step(
    step_name: str,
    pdf_path: Path,
    max_pages: int | None,
    llm_provider: str,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None = None,
    previous_results: dict[str, Any] | None = None,
    max_correction_iterations: int | None = None,
    quality_thresholds: dict[str, Any] | None = None,
    enable_iterative_correction: bool = True,
    report_language: str = "en",
    report_compile_pdf: bool = True,
    report_enable_figures: bool = True,
    report_renderer: str = "latex",
) -> dict[str, Any]:
    """
    Execute a single pipeline step with dependency validation.

    This is the public API for step-by-step pipeline execution. It enables
    running individual steps independently with UI updates between steps,
    supporting iterative workflows and better user feedback.

    Args:
        step_name: Step to execute:
            - "classification": Classify document type
            - "extraction": Extract structured data
            - "validation_correction": Iterative validation with automatic correction
            - "appraisal": Critical appraisal with iterative validation/correction
            - "report_generation": Generate structured report from extraction and appraisal
            - "validation": Legacy - Single validation run (backward compat)
            - "correction": Legacy - Single correction run (backward compat)
        pdf_path: Path to PDF file to process
        max_pages: Maximum pages to process (None = all pages)
        llm_provider: LLM provider name ("openai" or "claude")
        file_manager: File manager for saving step results
        progress_callback: Optional callback for progress updates (step_name, status, data)
        previous_results: Results from previous steps (required for dependent steps)
        max_correction_iterations: Max iterations for validation/appraisal correction loops
        quality_thresholds: Thresholds controlling iterative correction exit criteria
        enable_iterative_correction: Enable/disable iterative correction for appraisal
        report_language: Language to use for report generation ("en")

    Returns:
        Dictionary containing step result. Key depends on step:
        - classification: {"publication_type": str, "metadata": dict, ...}
        - extraction: {"data": dict, ...}
        - validation_correction: {"final_status": str, "best_extraction": dict,
                                  "best_validation": dict, "iterations": list, ...}
        - validation: {"verification_summary": dict, ...}
        - correction: {"extraction_corrected": dict, "validation_corrected": dict}

    Raises:
        ValueError: If step_name is invalid
        ValueError: If required dependencies are missing from previous_results
        PromptLoadError: If prompt file cannot be loaded
        SchemaLoadError: If schema file cannot be loaded
        LLMError: If LLM API call fails
        RuntimeError: If LLM support is not available

    Example:
        >>> # Step 1: Classification (no dependencies)
        >>> fm = PipelineFileManager(pdf_path)
        >>> result1 = run_single_step(
        ...     "classification",
        ...     pdf_path,
        ...     max_pages=10,
        ...     llm_provider="openai",
        ...     file_manager=fm,
        ... )
        >>> # Step 2: Extraction (requires classification)
        >>> result2 = run_single_step(
        ...     "extraction",
        ...     pdf_path,
        ...     max_pages=10,
        ...     llm_provider="openai",
        ...     file_manager=fm,
        ...     previous_results={"classification": result1},
        ... )
    """
    # Validate step name (allow both new and legacy steps)
    valid_steps = ALL_PIPELINE_STEPS + [STEP_VALIDATION, STEP_CORRECTION]
    if step_name not in valid_steps:
        raise ValueError(
            f"Invalid step_name '{step_name}'. Must be one of: {', '.join(valid_steps)}"
        )

    # Initialize previous_results if not provided
    if previous_results is None:
        previous_results = {}

    # Helper function to get result (from previous_results or load from disk)
    def _get_or_load_result(dep_step: str) -> dict[str, Any]:
        """
        Try to get step result from previous_results first, then load from disk.

        For extraction and validation steps, tries to load BEST files first (quality-selected),
        falling back to iteration 0 if no best file exists.

        Args:
            dep_step: Dependency step name to load

        Returns:
            Result dictionary from step

        Raises:
            ValueError: If result not found in memory or on disk
        """
        # Check if result already in previous_results (current run)
        if dep_step in previous_results:
            return previous_results[dep_step]

        # Try loading from disk (previous run)
        result = None

        # For extraction: try BEST file first, then fall back to extraction0
        if dep_step == "extraction":
            result = file_manager.load_json("extraction", status="best")
            if result:
                console.print("[yellow]📂 Loaded BEST extraction (quality-selected)[/yellow]")
                # Show metadata if available
                metadata = file_manager.load_json("extraction", status="best-metadata")
                if metadata:
                    console.print(
                        f"[dim]   Best iteration: {metadata.get('best_iteration_num')}, "
                        f"Quality: {metadata.get('overall_quality', 0):.2f}[/dim]"
                    )
                return result

            # Fallback: try extraction0
            console.print("[yellow]📂 No best extraction found, loading extraction0[/yellow]")
            result = file_manager.load_json("extraction", iteration_number=0)

        # For validation: try BEST file first, then fall back to validation0
        elif dep_step == "validation":
            result = file_manager.load_json("validation", status="best")
            if result:
                console.print("[yellow]📂 Loaded BEST validation (quality-selected)[/yellow]")
                return result

            # Fallback: try validation0
            console.print("[yellow]📂 No best validation found, loading validation0[/yellow]")
            result = file_manager.load_json("validation", iteration_number=0)

        # For appraisal: try BEST file first, then fall back to appraisal0
        elif dep_step == "appraisal":
            result = file_manager.load_json("appraisal", status="best")
            if result:
                console.print("[yellow]📂 Loaded BEST appraisal (quality-selected)[/yellow]")
                return result

            # Fallback: try appraisal0
            console.print("[yellow]📂 No best appraisal found, loading appraisal0[/yellow]")
            result = file_manager.load_json("appraisal", iteration_number=0)

        # For other steps: load normally
        else:
            result = file_manager.load_json(dep_step)

        if result is None:
            raise ValueError(
                f"{dep_step.title()} step result not found. "
                f"Please run {dep_step} step first or ensure "
                f"tmp/{file_manager.identifier}-{dep_step}.json exists."
            )

        if dep_step not in ["extraction", "validation", "appraisal"]:
            console.print(f"[yellow]📂 Loaded {dep_step} result from disk[/yellow]")

        return result

    # Validate dependencies based on step and load if needed
    if step_name == STEP_EXTRACTION:
        classification_result = _get_or_load_result("classification")
        previous_results[STEP_CLASSIFICATION] = classification_result  # Cache in memory

    elif step_name == STEP_VALIDATION:
        classification_result = _get_or_load_result("classification")
        extraction_result = _get_or_load_result("extraction")
        previous_results[STEP_CLASSIFICATION] = classification_result
        previous_results[STEP_EXTRACTION] = extraction_result

    elif step_name == STEP_CORRECTION:
        classification_result = _get_or_load_result("classification")
        extraction_result = _get_or_load_result("extraction")
        validation_result = _get_or_load_result("validation")
        previous_results[STEP_CLASSIFICATION] = classification_result
        previous_results[STEP_EXTRACTION] = extraction_result
        previous_results[STEP_VALIDATION] = validation_result

        # Check if correction is actually needed
        validation_status = validation_result.get("verification_summary", {}).get("overall_status")
        if validation_status == "passed":
            raise ValueError(
                "Correction step not needed - validation passed. "
                "Only run correction when validation status is not 'passed'."
            )

    elif step_name == STEP_REPORT_GENERATION:
        classification_result = _get_or_load_result("classification")
        extraction_result = _get_or_load_result("extraction")
        appraisal_result = _get_or_load_result("appraisal")

        # Try to use best results from validation_correction and appraisal if available
        try:
            validation_correction_result = _get_or_load_result("validation_correction")
            if validation_correction_result and validation_correction_result.get("best_extraction"):
                extraction_result = validation_correction_result["best_extraction"]
        except (ValueError, FileNotFoundError):
            pass

        # Try to use best_appraisal if available (from iterative appraisal)
        if isinstance(appraisal_result, dict) and appraisal_result.get("best_appraisal"):
            appraisal_result = appraisal_result["best_appraisal"]

        previous_results[STEP_CLASSIFICATION] = classification_result
        previous_results[STEP_EXTRACTION] = extraction_result
        previous_results[STEP_APPRAISAL] = appraisal_result

    elif step_name == STEP_PODCAST_GENERATION:
        classification_result = _get_or_load_result("classification")
        extraction_result = _get_or_load_result("extraction")
        appraisal_result = _get_or_load_result("appraisal")
        previous_results[STEP_CLASSIFICATION] = classification_result
        previous_results[STEP_EXTRACTION] = extraction_result
        previous_results[STEP_APPRAISAL] = appraisal_result

    elif step_name == STEP_VALIDATION_CORRECTION:
        classification_result = _get_or_load_result("classification")
        extraction_result = _get_or_load_result("extraction")
        previous_results[STEP_CLASSIFICATION] = classification_result
        previous_results[STEP_EXTRACTION] = extraction_result

    elif step_name == STEP_APPRAISAL:
        classification_result = _get_or_load_result("classification")
        extraction_result = _get_or_load_result("extraction")

        # Try to use best_extraction from validation_correction if available
        # This is optional - if validation_correction was not run, use original extraction
        try:
            validation_correction_result = _get_or_load_result("validation_correction")
            if validation_correction_result and validation_correction_result.get("best_extraction"):
                extraction_result = validation_correction_result["best_extraction"]
        except (ValueError, FileNotFoundError):
            # validation_correction not available, use original extraction
            pass

        previous_results[STEP_CLASSIFICATION] = classification_result
        previous_results[STEP_EXTRACTION] = extraction_result

    elif step_name == STEP_REPORT_GENERATION:
        classification_result = _get_or_load_result("classification")
        extraction_result = _get_or_load_result("extraction")
        appraisal_result = _get_or_load_result("appraisal")

        # Try to use best results from validation_correction and appraisal if available
        try:
            validation_correction_result = _get_or_load_result("validation_correction")
            if validation_correction_result and validation_correction_result.get("best_extraction"):
                extraction_result = validation_correction_result["best_extraction"]
        except (ValueError, FileNotFoundError):
            pass

        # Try to use best_appraisal if available (from iterative appraisal)
        if isinstance(appraisal_result, dict) and appraisal_result.get("best_appraisal"):
            appraisal_result = appraisal_result["best_appraisal"]

        previous_results[STEP_CLASSIFICATION] = classification_result
        previous_results[STEP_EXTRACTION] = extraction_result
        previous_results[STEP_APPRAISAL] = appraisal_result

    # Check LLM support availability
    try:
        from ..llm import get_llm_provider

        have_llm_support = True
    except ImportError:
        have_llm_support = False

    # Dispatch to appropriate step function
    if step_name == STEP_CLASSIFICATION:
        return _run_classification_step(
            pdf_path=pdf_path,
            max_pages=max_pages,
            llm_provider=llm_provider,
            file_manager=file_manager,
            progress_callback=progress_callback,
            have_llm_support=have_llm_support,
        )

    elif step_name == STEP_EXTRACTION:
        classification_result = previous_results[STEP_CLASSIFICATION]
        llm = get_llm_provider(llm_provider)

        return _run_extraction_step(
            pdf_path=pdf_path,
            max_pages=max_pages,
            classification_result=classification_result,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )

    elif step_name == STEP_VALIDATION:
        classification_result = previous_results[STEP_CLASSIFICATION]
        extraction_result = previous_results[STEP_EXTRACTION]
        llm = get_llm_provider(llm_provider)

        return _run_validation_step(
            extraction_result=extraction_result,
            pdf_path=pdf_path,
            max_pages=max_pages,
            classification_result=classification_result,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )

    elif step_name == STEP_CORRECTION:
        classification_result = previous_results[STEP_CLASSIFICATION]
        extraction_result = previous_results[STEP_EXTRACTION]
        validation_result = previous_results[STEP_VALIDATION]
        publication_type = classification_result.get("publication_type")
        llm = get_llm_provider(llm_provider)

        corrected_extraction, final_validation = _run_correction_step(
            extraction_result=extraction_result,
            validation_result=validation_result,
            pdf_path=pdf_path,
            max_pages=max_pages,
            publication_type=publication_type,
            llm=llm,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )

        # Save corrected extraction and post-correction validation (4-step pipeline, iteration 1)
        corrected_file = file_manager.save_json(
            corrected_extraction, "extraction", iteration_number=1
        )
        console.print(f"[green]✅ Correctie opgeslagen: {corrected_file}[/green]")

        validation_file = file_manager.save_json(final_validation, "validation", iteration_number=1)
        console.print(f"[green]✅ Finale validatie opgeslagen: {validation_file}[/green]")

        # Return both corrected extraction and final validation
        return {
            "extraction_corrected": corrected_extraction,
            "validation_corrected": final_validation,
        }

    elif step_name == STEP_VALIDATION_CORRECTION:
        classification_result = previous_results[STEP_CLASSIFICATION]
        extraction_result = previous_results[STEP_EXTRACTION]

        return run_validation_with_correction(
            pdf_path=pdf_path,
            extraction_result=extraction_result,
            classification_result=classification_result,
            llm_provider=llm_provider,
            file_manager=file_manager,
            max_iterations=max_correction_iterations or 3,
            quality_thresholds=quality_thresholds,  # Falls back inside helper
            progress_callback=progress_callback,
        )

    elif step_name == STEP_APPRAISAL:
        classification_result = previous_results[STEP_CLASSIFICATION]

        # Use best_extraction from validation_correction if available, otherwise use original extraction
        validation_correction_result = previous_results.get(STEP_VALIDATION_CORRECTION)
        if validation_correction_result:
            # Check for failed validation status - do not proceed with appraisal
            final_status = validation_correction_result.get("final_status", "")
            if final_status.startswith("failed"):
                error_msg = validation_correction_result.get(
                    "error", f"Validation failed with status: {final_status}"
                )
                raise ValueError(
                    f"Cannot run appraisal: {error_msg}. "
                    f"Quality score was below minimum threshold."
                )
            if validation_correction_result.get("best_extraction"):
                extraction_result = validation_correction_result["best_extraction"]
            else:
                extraction_result = previous_results[STEP_EXTRACTION]
        else:
            extraction_result = previous_results[STEP_EXTRACTION]

        if enable_iterative_correction:
            return run_appraisal_with_correction(
                extraction_result=extraction_result,
                classification_result=classification_result,
                llm_provider=llm_provider,
                file_manager=file_manager,
                max_iterations=max_correction_iterations or 3,
                quality_thresholds=quality_thresholds,
                progress_callback=progress_callback,
            )

        return run_appraisal_single_pass(
            extraction_result=extraction_result,
            classification_result=classification_result,
            llm_provider=llm_provider,
            file_manager=file_manager,
            quality_thresholds=quality_thresholds,
            progress_callback=progress_callback,
        )

    elif step_name == STEP_REPORT_GENERATION:
        classification_result = previous_results[STEP_CLASSIFICATION]
        extraction_result = previous_results[STEP_EXTRACTION]
        appraisal_result = previous_results[STEP_APPRAISAL]

        if enable_iterative_correction:
            # Phase 3: Iterative validation & correction loop
            return run_report_with_correction(
                extraction_result=extraction_result,
                appraisal_result=appraisal_result,
                classification_result=classification_result,
                llm_provider=llm_provider,
                file_manager=file_manager,
                language=report_language,
                max_iterations=max_correction_iterations or 3,
                quality_thresholds=quality_thresholds,
                compile_pdf=report_compile_pdf,
                enable_figures=report_enable_figures,
                renderer=report_renderer,
                progress_callback=progress_callback,
            )
        else:
            # Phase 2: Single-pass generation (fallback)
            return run_report_generation(
                extraction_result=extraction_result,
                appraisal_result=appraisal_result,
                classification_result=classification_result,
                llm_provider=llm_provider,
                file_manager=file_manager,
                progress_callback=progress_callback,
                language=report_language or "en",
            )

    elif step_name == STEP_PODCAST_GENERATION:
        classification_result = previous_results[STEP_CLASSIFICATION]
        extraction_result = previous_results[STEP_EXTRACTION]
        appraisal_result = previous_results[STEP_APPRAISAL]

        # Use corrected extraction if available
        if STEP_CORRECTION in previous_results:
            extraction_result = previous_results[STEP_CORRECTION]["extraction_corrected"]
        elif STEP_VALIDATION_CORRECTION in previous_results:
            if previous_results[STEP_VALIDATION_CORRECTION].get("best_extraction"):
                extraction_result = previous_results[STEP_VALIDATION_CORRECTION]["best_extraction"]

        return run_podcast_generation(
            extraction_result=extraction_result,
            appraisal_result=appraisal_result,
            classification_result=classification_result,
            llm_provider=llm_provider,
            file_manager=file_manager,
            progress_callback=progress_callback,
        )

    else:
        # Should never reach here due to validation above
        raise ValueError(f"Unknown step: {step_name}")


def run_full_pipeline(
    pdf_path: Path,
    max_pages: int | None = None,
    llm_provider: str = "openai",
    breakpoint_after_step: str | None = None,
    have_llm_support: bool = True,
    steps_to_run: list[str] | None = None,
    report_language: str = "en",
    report_renderer: str = "latex",
    report_compile_pdf: bool = True,
    report_enable_figures: bool = True,
    progress_callback: Callable[[str, str, dict], None] | None = None,
) -> dict[str, Any]:
    """
    Full extraction-and-appraisal pipeline with optional step filtering.

    Coordinates the full pipeline from PDF to validated evidence outputs:
    1. Classification - Identify publication type + extract metadata
    2. Extraction - Detailed data extraction based on classified type
    3. Validation & Correction - Iterative quality control with automatic fixes
    4. Appraisal - Critical appraisal (RoB, GRADE, applicability)
    5. Report Generation - Compose structured report JSON (optional)
    6. Podcast Generation - Generate audio script (optional)

    Args:
        pdf_path: Path to PDF file to process
        max_pages: Maximum pages to process (None = all pages, max 100)
        llm_provider: LLM provider to use ("openai" or "claude")
        breakpoint_after_step: Step name to pause after (for testing)
        have_llm_support: Whether LLM modules are available
        steps_to_run: Optional list of steps to execute.
            None = run all steps (default).
            Dependencies are validated automatically.
        report_language: Language for report generation ("en")
        report_renderer: Renderer for reports ("latex" or "weasyprint")
        report_compile_pdf: Compile PDF when renderer supports it (LaTeX)
        report_enable_figures: Enable/disable figure generation in reports
        progress_callback: Optional callback for progress updates.
            Signature: callback(step_name: str, status: str, data: dict)
            - step_name: "classification" | "extraction" | "validation_correction" | "appraisal"
            - status: "starting" | "completed" | "failed" | "skipped"
            - data: dict with step-specific info (results, errors, timing, file_path)

    Returns:
        Dictionary with results from each completed step:
        {
            "classification": {...},
            "extraction": {...},
            "validation": {...},
            "extraction_corrected": {...},  # Only if correction ran
            "validation_corrected": {...},  # Only if correction ran
            "report_generation": {...},     # Only if report step executed
        }

    Raises:
        RuntimeError: If LLM support not available
        ValueError: If step dependencies are violated in steps_to_run
        LLMError: If LLM API calls fail
        SchemaLoadError: If schemas cannot be loaded
        PromptLoadError: If prompts cannot be loaded

    Example:
        >>> from pathlib import Path
        >>> # Basic usage
        >>> results = run_full_pipeline(
        ...     pdf_path=Path("paper.pdf"),
        ...     max_pages=20,
        ...     llm_provider="openai"
        ... )
        >>> results["classification"]["publication_type"]
        'interventional_trial'
        >>>
        >>> # With step filtering
        >>> results = run_full_pipeline(
        ...     pdf_path=Path("paper.pdf"),
        ...     steps_to_run=["classification", "extraction"]
        ... )
        >>>
        >>> # With progress callback
        >>> def my_callback(step, status, data):
        ...     print(f"{step}: {status}")
        >>> results = run_full_pipeline(
        ...     pdf_path=Path("paper.pdf"),
        ...     progress_callback=my_callback
        ... )
    """
    file_manager = PipelineFileManager(pdf_path)
    results = {}

    # Validate step dependencies if step filtering is enabled
    if steps_to_run is not None:
        _validate_step_dependencies(steps_to_run)

    # Define all steps in order
    all_steps = ALL_PIPELINE_STEPS

    # Execute each step using run_single_step()
    for step_name in all_steps:
        # Check if step should run
        if not _should_run_step(step_name, steps_to_run):
            _call_progress_callback(progress_callback, step_name, "skipped", {})
            console.print(f"[yellow]⏭️  {step_name.title()} skipped (not in steps_to_run)[/yellow]")

            # Classification cannot be skipped - it's required for all other steps
            if step_name == STEP_CLASSIFICATION:
                raise RuntimeError(
                    "Classification cannot be skipped - required for all other steps"
                )

            continue

        # Special handling for correction - skip if validation passed
        if step_name == STEP_CORRECTION:
            validation_result = results.get(STEP_VALIDATION)
            if validation_result:
                validation_status = validation_result.get("verification_summary", {}).get(
                    "overall_status"
                )
                if validation_status == "passed":
                    _call_progress_callback(
                        progress_callback,
                        STEP_CORRECTION,
                        "skipped",
                        {"reason": "validation_passed", "validation_status": validation_status},
                    )
                    console.print("[green]✅ Correction not needed - validation passed[/green]")
                    continue

        # Special handling for appraisal - skip if validation_correction failed
        if step_name == STEP_APPRAISAL:
            validation_correction_result = results.get(STEP_VALIDATION_CORRECTION)
            if validation_correction_result:
                final_status = validation_correction_result.get("final_status", "")
                if final_status.startswith("failed"):
                    error_msg = validation_correction_result.get(
                        "error", "Schema validation failed"
                    )
                    _call_progress_callback(
                        progress_callback,
                        STEP_APPRAISAL,
                        "skipped",
                        {
                            "reason": "extraction_validation_failed",
                            "final_status": final_status,
                            "error": error_msg,
                        },
                    )
                    console.print(
                        f"[red]⏭️  Appraisal skipped - extraction validation failed: {error_msg}[/red]"
                    )
                    continue

        try:
            # Run single step with previous results
            step_result = run_single_step(
                step_name=step_name,
                pdf_path=pdf_path,
                max_pages=max_pages,
                llm_provider=llm_provider,
                file_manager=file_manager,
                progress_callback=progress_callback,
                previous_results=results,
                report_language=report_language,
                report_renderer=report_renderer,
                report_compile_pdf=report_compile_pdf,
                report_enable_figures=report_enable_figures,
            )

            # Store result
            if step_name == STEP_CORRECTION:
                # Correction returns dict with extraction_corrected and validation_corrected
                # Strip metadata (including correction_notes) from corrected extraction
                results["extraction_corrected"] = _strip_metadata_for_pipeline(
                    step_result["extraction_corrected"]
                )
                results["validation_corrected"] = step_result["validation_corrected"]
            else:
                results[step_name] = step_result

        except Exception:
            # Error already handled in run_single_step() via progress callback
            raise

        # Check for breakpoint after this step
        if check_breakpoint(step_name, results, file_manager, breakpoint_after_step):
            return _finalize_pipeline_results(results, file_manager, steps_to_run)

        # Check for publication_type == "overig" after classification
        if step_name == STEP_CLASSIFICATION:
            if step_result.get("publication_type") == "overig":
                console.print(
                    "[yellow]⚠️ Publication type 'overig' - "
                    "no specialized extraction available[/yellow]"
                )
                return _finalize_pipeline_results(results, file_manager, steps_to_run)

        _print_next_step_hint(step_name, steps_to_run)

    return _finalize_pipeline_results(results, file_manager, steps_to_run)
