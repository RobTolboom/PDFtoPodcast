# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Four-step PDF extraction + appraisal pipeline orchestration.

This module contains the main pipeline orchestration logic that coordinates
the four primary steps: Classification → Extraction → Validation & Correction → Appraisal.

Pipeline Steps:
    1. Classification - Identify publication type and extract metadata
    2. Extraction - Schema-based structured data extraction
    3. Validation & Correction - Iterative validation with automatic correction
    4. Appraisal - Critical appraisal (risk of bias, GRADE, applicability)

Public APIs:
    - run_single_step(): Execute individual pipeline steps with dependency validation
      Enables step-by-step execution with UI updates between steps.

    - run_four_step_pipeline(): Execute all four steps sequentially (legacy API)
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

import copy
import json
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from ..llm import LLMError, get_llm_provider
from ..prompts import (
    PromptLoadError,
    load_appraisal_correction_prompt,
    load_appraisal_prompt,
    load_appraisal_validation_prompt,
    load_classification_prompt,
    load_correction_prompt,
    load_extraction_prompt,
    load_report_correction_prompt,
    load_report_generation_prompt,
    load_report_validation_prompt,
)
from ..rendering.latex_renderer import LatexRenderError, render_report_to_pdf
from ..rendering.markdown_renderer import render_report_to_markdown
from ..rendering.weasy_renderer import WeasyRendererError, render_report_with_weasyprint
from ..schemas_loader import SchemaLoadError, load_schema, validate_schema_compatibility
from .file_manager import PipelineFileManager
from .utils import check_breakpoint
from .validation_runner import run_dual_validation

# Pipeline step name constants
STEP_CLASSIFICATION = "classification"
STEP_EXTRACTION = "extraction"
STEP_VALIDATION = "validation"
STEP_CORRECTION = "correction"
STEP_VALIDATION_CORRECTION = "validation_correction"
STEP_APPRAISAL = "appraisal"
STEP_APPRAISAL_VALIDATION = "appraisal_validation"
STEP_REPORT_GENERATION = "report_generation"

# Default pipeline steps (validation_correction replaces separate validation+correction)
ALL_PIPELINE_STEPS = [
    STEP_CLASSIFICATION,
    STEP_EXTRACTION,
    STEP_VALIDATION_CORRECTION,
    STEP_APPRAISAL,  # Critical appraisal after extraction validation
    STEP_REPORT_GENERATION,  # Report generation after appraisal
]
# Note: STEP_VALIDATION and STEP_CORRECTION remain available for CLI backward compatibility

STEP_DISPLAY_NAMES = {
    STEP_CLASSIFICATION: "Step 1 - Classification",
    STEP_EXTRACTION: "Step 2 - Extraction",
    STEP_VALIDATION_CORRECTION: "Step 3 - Validation & Correction",
    STEP_APPRAISAL: "Step 4 - Appraisal",
    STEP_REPORT_GENERATION: "Step 5 - Report Generation",
}

_PIPELINE_VERSION_CACHE: str | None = None


def _get_pipeline_version() -> str:
    """
    Retrieve pipeline version from installed package or pyproject.toml.
    """
    global _PIPELINE_VERSION_CACHE
    if _PIPELINE_VERSION_CACHE:
        return _PIPELINE_VERSION_CACHE

    try:
        from importlib.metadata import PackageNotFoundError, version

        _PIPELINE_VERSION_CACHE = version("pdftopodcast")
        return _PIPELINE_VERSION_CACHE
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


class UnsupportedPublicationType(ValueError):
    """
    Exception raised when a publication type has no appraisal support.

    This occurs when attempting to run appraisal on publication types
    that don't have corresponding appraisal prompts (e.g., 'overig').

    Attributes:
        publication_type: The unsupported publication type
        message: Human-readable error message
    """

    def __init__(self, publication_type: str, message: str | None = None):
        self.publication_type = publication_type
        if message is None:
            message = (
                f"Appraisal not supported for publication type '{publication_type}'. "
                f"Supported types: interventional_trial, observational_analytic, "
                f"evidence_synthesis, prediction_prognosis, diagnostic, editorials_opinion."
            )
        super().__init__(message)


def _call_progress_callback(
    callback: Callable[[str, str, dict], None] | None,
    step_name: str,
    status: str,
    data: dict,
) -> None:
    """
    Safely call progress callback if provided.

    Wraps callback in try/except to prevent callback errors from breaking pipeline.
    Logs callback errors but does not propagate them.

    Args:
        callback: Optional callback function (None = no callback)
        step_name: Step identifier ("classification", "extraction", "validation", "correction")
        status: Step status ("starting", "running", "completed", "failed", "skipped")
        data: Dictionary with step-specific information (results, errors, timing, etc.)

    Example:
        >>> _call_progress_callback(my_callback, "classification", "starting", {"pdf_path": "..."})
    """
    if callback is None:
        return

    try:
        callback(step_name, status, data)
    except Exception as e:
        # Log but don't propagate - callback errors shouldn't break pipeline
        console.print(f"[yellow]⚠️  Progress callback error in {step_name}: {e}[/yellow]")


def _strip_metadata_for_pipeline(data: dict) -> dict:
    """
    Remove metadata fields before passing data to next pipeline step.

    Strips fields that contain execution metadata but are not part of
    the schema-defined data structure:

    - usage: LLM token usage (input/output/cached tokens)
    - _metadata: LLM API response metadata (response_id, model, etc.)
    - _pipeline_metadata: Pipeline execution metadata (timestamp, duration, etc.)
    - correction_notes: Notes added by correction step (not part of extraction schema)

    This ensures:
    1. Schema validation doesn't fail on unexpected fields
    2. LLM prompts don't receive metadata clutter
    3. Step dependencies only see clean, schema-valid data

    Args:
        data: Dictionary containing step results with potential metadata

    Returns:
        Deep copy of data with metadata fields removed. Deep copy ensures
        modifications to nested objects don't affect the original data.

    Example:
        >>> result = {
        ...     "publication_type": "interventional_trial",
        ...     "usage": {"input_tokens": 1000},
        ...     "_metadata": {"response_id": "resp_123"}
        ... }
        >>> clean = _strip_metadata_for_pipeline(result)
        >>> clean
        {'publication_type': 'interventional_trial'}
    """
    clean_data = copy.deepcopy(data)
    clean_data.pop("usage", None)
    clean_data.pop("_metadata", None)
    clean_data.pop("_pipeline_metadata", None)
    clean_data.pop("correction_notes", None)
    return clean_data


def _get_provider_name(llm: Any) -> str:
    """
    Get provider name from LLM instance class name.

    Determines which LLM provider is being used by inspecting the
    class name of the LLM instance. Used for pipeline metadata tracking.

    Args:
        llm: LLM provider instance (OpenAIProvider or ClaudeProvider)

    Returns:
        Provider name: "openai", "claude", or "unknown"

    Example:
        >>> from src.llm import get_llm_provider
        >>> llm = get_llm_provider("openai")
        >>> _get_provider_name(llm)
        'openai'
    """
    class_name = llm.__class__.__name__
    if "OpenAI" in class_name:
        return "openai"
    elif "Claude" in class_name:
        return "claude"
    return "unknown"


def _get_appraisal_prompt_name(publication_type: str) -> str:
    """
    Map publication type to corresponding appraisal prompt filename.

    This function routes each publication type to its appropriate critical
    appraisal prompt based on the methodology (RoB 2, ROBINS-I, PROBAST, etc.).

    Args:
        publication_type: Classification result publication type

    Returns:
        Prompt filename without .txt extension (e.g., "Appraisal-interventional")

    Raises:
        UnsupportedPublicationType: If publication type has no appraisal support

    Mapping:
        - interventional_trial → Appraisal-interventional (RoB 2)
        - observational_analytic → Appraisal-observational (ROBINS-I/E)
        - evidence_synthesis → Appraisal-evidence-synthesis (AMSTAR 2 + ROBIS)
        - prediction_prognosis → Appraisal-prediction (PROBAST)
        - diagnostic → Appraisal-prediction (QUADAS-2/C, shared with PROBAST)
        - editorials_opinion → Appraisal-editorials (Argument quality)

    Note:
        The 'diagnostic' type shares the prediction prompt because PROBAST
        and QUADAS tools have similar structure (Risk of Bias + Applicability
        across multiple domains, plus performance evaluation).

    Example:
        >>> _get_appraisal_prompt_name("interventional_trial")
        'Appraisal-interventional'
        >>> _get_appraisal_prompt_name("diagnostic")
        'Appraisal-prediction'  # Shared prompt
        >>> _get_appraisal_prompt_name("overig")
        UnsupportedPublicationType: ...
    """
    prompt_mapping = {
        "interventional_trial": "Appraisal-interventional",
        "observational_analytic": "Appraisal-observational",
        "evidence_synthesis": "Appraisal-evidence-synthesis",
        "prediction_prognosis": "Appraisal-prediction",
        "diagnostic": "Appraisal-prediction",  # Shared prompt (PROBAST/QUADAS)
        "editorials_opinion": "Appraisal-editorials",
    }

    if publication_type not in prompt_mapping:
        raise UnsupportedPublicationType(publication_type)

    return prompt_mapping[publication_type]


def _extract_appraisal_metrics(validation_result: dict) -> dict:
    """
    Extract key metrics from appraisal validation result for comparison.

    Used for:
    - Best iteration selection (_select_best_appraisal_iteration)
    - Quality degradation detection (_detect_quality_degradation)
    - Progress tracking and UI display

    Returns dict with individual scores + computed 'quality_score':
        - 35% logical_consistency (overall = worst domain, GRADE alignment)
        - 25% completeness (all domains, all outcomes)
        - 25% evidence_support (rationales match extraction)
        - 15% schema_compliance (enums, required fields)

    Note:
        Unlike extraction validation, appraisal uses the validation_summary
        field instead of verification_summary to differentiate the two processes.

    Example:
        >>> validation = {
        ...     'validation_summary': {
        ...         'logical_consistency_score': 0.95,
        ...         'completeness_score': 0.90,
        ...         'evidence_support_score': 0.92,
        ...         'schema_compliance_score': 1.0,
        ...         'critical_issues': 0,
        ...         'quality_score': 0.94
        ...     }
        ... }
        >>> metrics = _extract_appraisal_metrics(validation)
        >>> metrics['quality_score']
        0.94
    """
    summary = validation_result.get("validation_summary", {})

    return {
        "logical_consistency_score": summary.get("logical_consistency_score", 0),
        "completeness_score": summary.get("completeness_score", 0),
        "evidence_support_score": summary.get("evidence_support_score", 0),
        "schema_compliance_score": summary.get("schema_compliance_score", 0),
        "critical_issues": summary.get("critical_issues", 0),
        "overall_status": summary.get("overall_status", "unknown"),
        # Quality score computed by validation prompt (weighted composite)
        # If not present, compute it here as fallback
        "quality_score": summary.get(
            "quality_score",
            (
                summary.get("logical_consistency_score", 0) * 0.35
                + summary.get("completeness_score", 0) * 0.25
                + summary.get("evidence_support_score", 0) * 0.25
                + summary.get("schema_compliance_score", 0) * 0.15
            ),
        ),
    }


def _extract_report_metrics(validation_result: dict) -> dict:
    """
    Extract key metrics from report validation result for comparison.

    Used for:
    - Best iteration selection (_select_best_report_iteration)
    - Quality degradation detection (_detect_quality_degradation)
    - Progress tracking and UI display

    Returns dict with individual scores + computed 'quality_score':
        - 35% accuracy (data correctness paramount)
        - 30% completeness (all core sections present)
        - 10% cross_reference_consistency (table/figure refs valid)
        - 10% data_consistency (bottom-line matches results)
        - 15% schema_compliance (enums, required fields)

    Note:
        Report validation emphasizes accuracy (35%) over other dimensions because
        data correctness is critical for clinical decision-making.

    Example:
        >>> validation = {
        ...     'validation_summary': {
        ...         'completeness_score': 0.90,
        ...         'accuracy_score': 0.95,
        ...         'cross_reference_consistency_score': 0.92,
        ...         'data_consistency_score': 0.88,
        ...         'schema_compliance_score': 1.0,
        ...         'critical_issues': 0,
        ...         'quality_score': 0.93
        ...     }
        ... }
        >>> metrics = _extract_report_metrics(validation)
        >>> metrics['quality_score']
        0.93
    """
    summary = validation_result.get("validation_summary", {})

    return {
        "completeness_score": summary.get("completeness_score", 0),
        "accuracy_score": summary.get("accuracy_score", 0),
        "cross_reference_consistency_score": summary.get("cross_reference_consistency_score", 0),
        "data_consistency_score": summary.get("data_consistency_score", 0),
        "schema_compliance_score": summary.get("schema_compliance_score", 0),
        "critical_issues": summary.get("critical_issues", 0),
        "overall_status": summary.get("overall_status", "unknown"),
        # Quality score computed by validation prompt (weighted composite)
        # If not present, compute it here as fallback
        "quality_score": summary.get(
            "quality_score",
            (
                summary.get("accuracy_score", 0) * 0.35
                + summary.get("completeness_score", 0) * 0.30
                + summary.get("cross_reference_consistency_score", 0) * 0.10
                + summary.get("data_consistency_score", 0) * 0.10
                + summary.get("schema_compliance_score", 0) * 0.15
            ),
        ),
    }


def is_quality_sufficient(validation_result: dict | None, thresholds: dict | None = None) -> bool:
    """
    Check if validation quality meets thresholds for stopping iteration.

    Args:
        validation_result: Validation JSON with verification_summary (can be None)
        thresholds: Quality thresholds to check against (defaults to DEFAULT_QUALITY_THRESHOLDS)

    Returns:
        bool: True if ALL thresholds are met, False otherwise

    Edge Cases:
        - validation_result is None → False
        - verification_summary missing → False
        - Any score is None → treated as 0 (fails threshold)
        - Empty dict → False (all scores default to 0)

    Example:
        >>> validation = {
        ...     'verification_summary': {
        ...         'completeness_score': 0.92,
        ...         'accuracy_score': 0.98,
        ...         'schema_compliance_score': 0.97,
        ...         'critical_issues': 0
        ...     }
        ... }
        >>> is_quality_sufficient(validation)  # True
        >>> is_quality_sufficient(None)  # False
        >>> is_quality_sufficient({})  # False
    """
    # Use default thresholds if not provided
    if thresholds is None:
        thresholds = DEFAULT_QUALITY_THRESHOLDS

    # Handle None validation_result
    if validation_result is None:
        return False

    summary = validation_result.get("verification_summary", {})

    # Handle missing or empty summary
    if not summary:
        return False

    # Helper to safely extract numeric scores (handle None values)
    def safe_score(key: str, default: float = 0.0) -> float:
        val = summary.get(key, default)
        return val if isinstance(val, int | float) else default

    # Check all thresholds
    return (
        safe_score("completeness_score") >= thresholds["completeness_score"]
        and safe_score("accuracy_score") >= thresholds["accuracy_score"]
        and safe_score("schema_compliance_score") >= thresholds["schema_compliance_score"]
        and safe_score("critical_issues", 999) <= thresholds["critical_issues"]
    )


def _extract_metrics(validation_result: dict) -> dict:
    """
    Extract key metrics from validation result for comparison.

    Used for:
    - Best iteration selection (_select_best_iteration)
    - Quality degradation detection (_detect_quality_degradation)
    - Progress tracking and UI display

    Returns dict with individual scores + computed 'overall_quality':
        - 40% completeness (coverage of PDF data)
        - 40% accuracy (correctness, no hallucinations)
        - 20% schema compliance (structural correctness)
    """
    summary = validation_result.get("verification_summary", {})

    return {
        "completeness_score": summary.get("completeness_score", 0),
        "accuracy_score": summary.get("accuracy_score", 0),
        "schema_compliance_score": summary.get("schema_compliance_score", 0),
        "critical_issues": summary.get("critical_issues", 0),
        "total_issues": summary.get("total_issues", 0),
        "overall_status": summary.get("overall_status", "unknown"),
        # Derived composite score (used by ranking and degradation detection)
        "overall_quality": (
            summary.get("completeness_score", 0) * 0.4
            + summary.get("accuracy_score", 0) * 0.4
            + summary.get("schema_compliance_score", 0) * 0.2
        ),
    }


def _detect_quality_degradation(iterations: list[dict], window: int = 2) -> bool:
    """
    Detect if quality has been degrading for the last N iterations.

    Early stopping prevents wasted LLM calls when corrections are making things worse.

    Works with both extraction and appraisal iterations by checking for either
    'overall_quality' (extraction) or 'quality_score' (appraisal) in metrics.

    Args:
        iterations: List of all iteration data (each with 'metrics' dict)
        window: Number of consecutive degrading iterations to trigger stop (default: 2)

    Returns:
        True if quality degraded for 'window' consecutive iterations

    Logic:
        - Need at least (window + 1) iterations to detect trend
        - Compare last 'window' iterations against the OVERALL best score seen so far
        - Degradation = all iterations in window are worse than the peak quality
        - This catches systematic degradation, not transient noise

    Example:
        iterations = [
            {'metrics': {'overall_quality': 0.85}},  # iter 0
            {'metrics': {'overall_quality': 0.88}},  # iter 1 (BEST - peak quality)
            {'metrics': {'overall_quality': 0.86}},  # iter 2 (degraded from 0.88)
            {'metrics': {'overall_quality': 0.84}}   # iter 3 (degraded again)
        ]
        _detect_quality_degradation(iterations, window=2) → True
        # Last 2 iterations (0.86, 0.84) are BOTH worse than peak (0.88)
        # This indicates systematic degradation → stop and use iteration 1
    """
    if len(iterations) < window + 1:
        return False

    # Get quality scores - check for both extraction and appraisal metrics
    # Extraction uses 'overall_quality', appraisal uses 'quality_score'
    scores = []
    for it in iterations:
        metrics = it["metrics"]
        # Try quality_score first (appraisal), fallback to overall_quality (extraction)
        score = metrics.get("quality_score", metrics.get("overall_quality", 0))
        scores.append(score)

    # Find OVERALL peak quality (not just before window)
    # This is the best score we've achieved across all iterations
    peak_quality = max(scores)

    # Check if last 'window' iterations are ALL worse than peak
    # This indicates systematic degradation, not just a single bad iteration
    window_scores = scores[-window:]
    all_degraded = all(score < peak_quality for score in window_scores)

    return all_degraded


def _select_best_iteration(iterations: list[dict]) -> dict:
    """
    Select best iteration when max iterations reached but quality insufficient.

    Selection strategy:
        1. Priority 1: No critical issues (mandatory)
        2. Priority 2: Highest weighted quality score (40% completeness + 40% accuracy + 20% schema)
        3. Priority 3: If tied, prefer higher completeness
        4. Usually selects last iteration due to progressive improvement

    Args:
        iterations: List of iteration data dicts

    Returns:
        dict: Best iteration data with reason

    Example:
        >>> iterations = [
        ...     {'iteration_num': 0, 'metrics': {'overall_quality': 0.85, 'critical_issues': 0}},
        ...     {'iteration_num': 1, 'metrics': {'overall_quality': 0.92, 'critical_issues': 0}},
        ...     {'iteration_num': 2, 'metrics': {'overall_quality': 0.89, 'critical_issues': 1}},
        ... ]
        >>> best = _select_best_iteration(iterations)
        >>> best['iteration_num']  # 1 (highest quality, no critical issues)
    """
    if not iterations:
        raise ValueError("No iterations to select from")

    # Get last iteration
    last = iterations[-1]

    # Check if last is acceptable (no regression)
    if len(iterations) == 1:
        return {**last, "selection_reason": "only_iteration"}

    # Priority ranking for selection
    def quality_rank(iteration: dict) -> tuple:
        """
        Create sortable quality tuple using weighted composite score.
        Returns: (critical_ok, overall_quality, completeness_tiebreaker)

        Overall quality = weighted average:
        - 40% completeness (how much PDF data extracted)
        - 40% accuracy (correctness, no hallucinations)
        - 20% schema compliance (structural correctness)
        """
        metrics = iteration["metrics"]
        overall_quality = (
            metrics.get("completeness_score", 0) * 0.40
            + metrics.get("accuracy_score", 0) * 0.40
            + metrics.get("schema_compliance_score", 0) * 0.20
        )
        return (
            metrics.get("critical_issues", 999) == 0,  # Priority 1: No critical issues
            overall_quality,  # Priority 2: Composite quality
            metrics.get("completeness_score", 0),  # Priority 3: Completeness as tiebreaker
        )

    # Sort all iterations by quality (best first)
    sorted_iterations = sorted(iterations, key=quality_rank, reverse=True)

    best = sorted_iterations[0]

    # Determine reason
    if best["iteration_num"] == last["iteration_num"]:
        reason = "final_iteration_best"
    else:
        reason = f"quality_peaked_at_iteration_{best['iteration_num']}"

    return {**best, "selection_reason": reason}


def is_appraisal_quality_sufficient(
    validation_result: dict | None, thresholds: dict | None = None
) -> bool:
    """
    Check if appraisal validation quality meets thresholds for stopping iteration.

    Args:
        validation_result: Appraisal validation JSON with validation_summary (can be None)
        thresholds: Quality thresholds to check against (defaults to APPRAISAL_QUALITY_THRESHOLDS)

    Returns:
        bool: True if ALL thresholds are met, False otherwise

    Edge Cases:
        - validation_result is None → False
        - validation_summary missing → False
        - Any score is None → treated as 0 (fails threshold)
        - Empty dict → False (all scores default to 0)

    Example:
        >>> validation = {
        ...     'validation_summary': {
        ...         'logical_consistency_score': 0.95,
        ...         'completeness_score': 0.90,
        ...         'evidence_support_score': 0.92,
        ...         'schema_compliance_score': 1.0,
        ...         'critical_issues': 0
        ...     }
        ... }
        >>> is_appraisal_quality_sufficient(validation)  # True
        >>> is_appraisal_quality_sufficient(None)  # False
        >>> is_appraisal_quality_sufficient({})  # False
    """
    # Use default appraisal thresholds if not provided
    if thresholds is None:
        thresholds = APPRAISAL_QUALITY_THRESHOLDS

    # Handle None validation_result
    if validation_result is None:
        return False

    summary = validation_result.get("validation_summary", {})

    # Handle missing or empty summary
    if not summary:
        return False

    # Helper to safely extract numeric scores (handle None values)
    def safe_score(key: str, default: float = 0.0) -> float:
        val = summary.get(key, default)
        return val if isinstance(val, int | float) else default

    # Check all appraisal thresholds
    return (
        safe_score("logical_consistency_score") >= thresholds["logical_consistency_score"]
        and safe_score("completeness_score") >= thresholds["completeness_score"]
        and safe_score("evidence_support_score") >= thresholds["evidence_support_score"]
        and safe_score("schema_compliance_score") >= thresholds["schema_compliance_score"]
        and safe_score("critical_issues", 999) <= thresholds["critical_issues"]
    )


def _select_best_appraisal_iteration(iterations: list[dict]) -> dict:
    """
    Select best appraisal iteration when max iterations reached but quality insufficient.

    Selection strategy (prioritized):
        1. Priority 1: No critical issues (mandatory filter)
        2. Priority 2: Highest quality_score (weighted composite from validation)
        3. Priority 3: If tied, prefer higher completeness_score
        4. Priority 4: If still tied, prefer lowest iteration number (earlier success)

    Quality score composition (computed by validation prompt):
        - 35% logical_consistency (overall = worst domain, GRADE alignment)
        - 25% completeness (all domains, all outcomes)
        - 25% evidence_support (rationales match extraction)
        - 15% schema_compliance (enums, required fields)

    Args:
        iterations: List of appraisal iteration data dicts

    Returns:
        dict: Best iteration data with selection_reason

    Example:
        >>> iterations = [
        ...     {'iteration_num': 0, 'metrics': {'quality_score': 0.85, 'critical_issues': 0}},
        ...     {'iteration_num': 1, 'metrics': {'quality_score': 0.92, 'critical_issues': 0}},
        ...     {'iteration_num': 2, 'metrics': {'quality_score': 0.89, 'critical_issues': 1}},
        ... ]
        >>> best = _select_best_appraisal_iteration(iterations)
        >>> best['iteration_num']  # 1 (highest quality_score, no critical issues)
    """
    if not iterations:
        raise ValueError("No iterations to select from")

    # Get last iteration
    last = iterations[-1]

    # Check if only one iteration
    if len(iterations) == 1:
        return {**last, "selection_reason": "only_iteration"}

    # Priority ranking for selection
    def quality_rank(iteration: dict) -> tuple:
        """
        Create sortable quality tuple using validation quality_score.

        Returns: (critical_ok, quality_score, completeness_tiebreaker, neg_iteration)

        Note: quality_score already incorporates weighted composite from validation,
        unlike extraction which computes it here. We use the validated score directly.
        """
        metrics = iteration["metrics"]
        quality_score = metrics.get("quality_score", 0)

        return (
            metrics.get("critical_issues", 999) == 0,  # Priority 1: No critical issues
            quality_score,  # Priority 2: Quality score (from validation)
            metrics.get("completeness_score", 0),  # Priority 3: Completeness tiebreaker
            -iteration["iteration_num"],  # Priority 4: Prefer earlier iterations (lower num)
        )

    # Sort all iterations by quality (best first)
    sorted_iterations = sorted(iterations, key=quality_rank, reverse=True)

    best = sorted_iterations[0]

    # Determine reason
    if best["iteration_num"] == last["iteration_num"]:
        reason = "final_iteration_best"
    else:
        reason = f"quality_peaked_at_iteration_{best['iteration_num']}"

    return {**best, "selection_reason": reason}


def is_report_quality_sufficient(
    validation_result: dict | None, thresholds: dict | None = None
) -> bool:
    """
    Check if report validation quality meets thresholds for stopping iteration.

    Args:
        validation_result: Report validation JSON with validation_summary (can be None)
        thresholds: Quality thresholds to check against (defaults to REPORT_QUALITY_THRESHOLDS)

    Returns:
        bool: True if ALL thresholds are met, False otherwise

    Edge Cases:
        - validation_result is None → False
        - validation_summary missing → False
        - Any score is None → treated as 0 (fails threshold)
        - Empty dict → False (all scores default to 0)

    Example:
        >>> validation = {
        ...     'validation_summary': {
        ...         'completeness_score': 0.90,
        ...         'accuracy_score': 0.95,
        ...         'cross_reference_consistency_score': 0.92,
        ...         'data_consistency_score': 0.88,
        ...         'schema_compliance_score': 1.0,
        ...         'critical_issues': 0
        ...     }
        ... }
        >>> is_report_quality_sufficient(validation)  # True
        >>> is_report_quality_sufficient(None)  # False
        >>> is_report_quality_sufficient({})  # False
    """
    # Use default report thresholds if not provided
    if thresholds is None:
        thresholds = REPORT_QUALITY_THRESHOLDS

    # Handle None validation_result
    if validation_result is None:
        return False

    summary = validation_result.get("validation_summary", {})

    # Handle missing or empty summary
    if not summary:
        return False

    # Helper to safely extract numeric scores (handle None values)
    def safe_score(key: str, default: float = 0.0) -> float:
        val = summary.get(key, default)
        return val if isinstance(val, int | float) else default

    # Check all report thresholds
    return (
        safe_score("completeness_score") >= thresholds["completeness_score"]
        and safe_score("accuracy_score") >= thresholds["accuracy_score"]
        and safe_score("cross_reference_consistency_score")
        >= thresholds["cross_reference_consistency_score"]
        and safe_score("data_consistency_score") >= thresholds["data_consistency_score"]
        and safe_score("schema_compliance_score") >= thresholds["schema_compliance_score"]
        and safe_score("critical_issues", 999) <= thresholds["critical_issues"]
    )


def _select_best_report_iteration(iterations: list[dict]) -> dict:
    """
    Select best report iteration when max iterations reached but quality insufficient.

    Selection strategy (prioritized):
        1. Priority 1: No critical issues (mandatory filter)
        2. Priority 2: Highest quality_score (weighted composite from validation)
        3. Priority 3: If tied, prefer higher accuracy_score (data correctness paramount)
        4. Priority 4: If still tied, prefer lowest iteration number (earlier success)

    Quality score composition (computed by validation prompt):
        - 35% accuracy (data correctness paramount)
        - 30% completeness (all core sections present)
        - 10% cross_reference_consistency (table/figure refs valid)
        - 10% data_consistency (bottom-line matches results)
        - 15% schema_compliance (enums, required fields)

    Args:
        iterations: List of report iteration data dicts

    Returns:
        dict: Best iteration data with selection_reason

    Example:
        >>> iterations = [
        ...     {'iteration_num': 0, 'metrics': {'quality_score': 0.85, 'critical_issues': 0}},
        ...     {'iteration_num': 1, 'metrics': {'quality_score': 0.92, 'critical_issues': 0}},
        ...     {'iteration_num': 2, 'metrics': {'quality_score': 0.89, 'critical_issues': 1}},
        ... ]
        >>> best = _select_best_report_iteration(iterations)
        >>> best['iteration_num']  # 1 (highest quality_score, no critical issues)
    """
    if not iterations:
        raise ValueError("No iterations to select from")

    # Get last iteration
    last = iterations[-1]

    # Check if only one iteration
    if len(iterations) == 1:
        return {**last, "selection_reason": "only_iteration"}

    # Priority ranking for selection
    def quality_rank(iteration: dict) -> tuple:
        """
        Create sortable quality tuple using validation quality_score.

        Returns: (critical_ok, quality_score, accuracy_tiebreaker, neg_iteration)

        Note: For reports, accuracy is the primary tiebreaker (not completeness)
        because data correctness is critical for clinical decision-making.
        """
        metrics = iteration["metrics"]
        quality_score = metrics.get("quality_score", 0)

        return (
            metrics.get("critical_issues", 999) == 0,  # Priority 1: No critical issues
            quality_score,  # Priority 2: Quality score (from validation)
            metrics.get("accuracy_score", 0),  # Priority 3: Accuracy tiebreaker
            -iteration["iteration_num"],  # Priority 4: Prefer earlier iterations (lower num)
        )

    # Sort all iterations by quality (best first)
    sorted_iterations = sorted(iterations, key=quality_rank, reverse=True)

    best = sorted_iterations[0]

    # Determine reason
    if best["iteration_num"] == last["iteration_num"]:
        reason = "final_iteration_best"
    else:
        reason = f"quality_peaked_at_iteration_{best['iteration_num']}"

    return {**best, "selection_reason": reason}


def _run_extraction_step(
    pdf_path: Path,
    max_pages: int | None,
    classification_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """
    Run extraction step of the pipeline.

    Performs schema-based structured data extraction from PDF based on
    the publication type identified in classification step.

    Args:
        pdf_path: Path to the PDF file to extract from
        max_pages: Maximum number of pages to process (None = all pages)
        classification_result: Result from classification step containing publication_type
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates
        banner_label: Optional custom label for console banner (defaults to "VALIDATION")

    Returns:
        Dictionary containing extracted structured data

    Raises:
        SchemaLoadError: If schema file cannot be loaded
        PromptLoadError: If prompt file cannot be loaded
        LLMError: If LLM API call fails
    """
    console.print("\n[bold magenta]═══ STEP 2: DATA EXTRACTION (SCHEMA-BASED) ═══[/bold magenta]\n")

    start_time = time.time()

    # Strip metadata from classification before using
    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")

    _call_progress_callback(
        progress_callback,
        "extraction",
        "starting",
        {"publication_type": publication_type},
    )

    try:
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
            f"[cyan]⚙️  Extraction prompt: {publication_type} schema (~{compatibility['estimated_tokens']} tokens)[/cyan]"
        )
        console.print("[dim]Uploading PDF for extraction...[/dim]")

        # Run schema-based extraction with direct PDF upload
        extraction_result = llm.generate_json_with_pdf(
            pdf_path=pdf_path,
            schema=extraction_schema,
            system_prompt=extraction_prompt,
            max_pages=max_pages,
            schema_name=f"{publication_type}_extraction",
        )

        console.print("[green]✅ Schema-conforming extraction completed[/green]")

        # Add pipeline metadata
        elapsed = time.time() - start_time
        extraction_result["_pipeline_metadata"] = {
            "step": "extraction",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed,
            "llm_provider": _get_provider_name(llm),
            "model_used": extraction_result.get("_metadata", {}).get("model"),
            "max_pages": max_pages,
            "pdf_filename": pdf_path.name,
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
            "publication_type": publication_type,
        }

        # Display extraction summary
        model_used = extraction_result.get("_metadata", {}).get("model", _get_provider_name(llm))

        console.print("\n[bold]Extraction Summary:[/bold]")
        console.print(f"  Publication Type: [cyan]{publication_type}[/cyan]")
        console.print(f"  Model: [dim]{model_used}[/dim]")
        console.print(f"  Duration: [dim]{elapsed:.1f}s[/dim]\n")

        # Save extraction result (iteration 0)
        extraction_file = file_manager.save_json(
            extraction_result, "extraction", iteration_number=0
        )
        console.print(f"[dim]Saved: {extraction_file.name}[/dim]")
        console.print("[green]✅ Extraction complete[/green]")

        # Extraction completed successfully
        elapsed = time.time() - start_time
        _call_progress_callback(
            progress_callback,
            "extraction",
            "completed",
            {
                "result": extraction_result,
                "elapsed_seconds": elapsed,
                "file_path": str(extraction_file),
                "publication_type": publication_type,
            },
        )

        return extraction_result

    except (SchemaLoadError, PromptLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Extraction error: {e}[/red]")

        # Save error metadata (best effort)
        error_data = {
            "_pipeline_metadata": {
                "step": "extraction",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": elapsed,
                "llm_provider": _get_provider_name(llm),
                "model_used": None,
                "max_pages": max_pages,
                "pdf_filename": pdf_path.name,
                "execution_mode": "streamlit" if progress_callback else "cli",
                "status": "failed",
                "error_message": str(e),
                "error_type": type(e).__name__,
                "publication_type": publication_type,
            }
        }
        try:
            file_manager.save_json(error_data, "extraction", "failed")
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to save error metadata: {e}[/yellow]")

        _call_progress_callback(
            progress_callback,
            "extraction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def _run_validation_step(
    extraction_result: dict[str, Any],
    pdf_path: Path,
    max_pages: int | None,
    classification_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
    banner_label: str | None = None,
) -> dict[str, Any]:
    """
    Run validation step of the pipeline.

    Performs dual validation (schema + conditional LLM semantic) on the
    extracted data to identify quality issues and errors.

    Args:
        extraction_result: Result from extraction step to validate
        pdf_path: Path to original PDF file for LLM validation
        max_pages: Maximum number of pages to process (None = all pages)
        classification_result: Result from classification step containing publication_type
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates

    Returns:
        Dictionary containing validation results with verification_summary

    Raises:
        LLMError: If LLM API call fails during semantic validation
    """
    start_time = time.time()
    _call_progress_callback(progress_callback, STEP_VALIDATION, "starting", {})

    # Strip metadata from dependencies before using
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)
    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")

    # Run dual validation (schema + conditional LLM) with clean data
    label = banner_label or "VALIDATION"
    validation_result = run_dual_validation(
        extraction_result=extraction_clean,
        pdf_path=pdf_path,
        max_pages=max_pages,
        publication_type=publication_type,
        llm=llm,
        console=console,
        banner_label=label,
    )

    # Add pipeline metadata
    elapsed = time.time() - start_time
    validation_result["_pipeline_metadata"] = {
        "step": "validation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": elapsed,
        "llm_provider": _get_provider_name(llm),
        "model_used": validation_result.get("_metadata", {}).get("model"),
        "max_pages": max_pages,
        "pdf_filename": pdf_path.name,
        "execution_mode": "streamlit" if progress_callback else "cli",
        "status": "success",
        "validation_passed": validation_result.get("is_valid", False),
    }

    validation_file = file_manager.save_json(validation_result, "validation", iteration_number=0)
    console.print(f"[green]✅ Validation saved: {validation_file}[/green]")

    # Validation completed
    elapsed = time.time() - start_time
    _call_progress_callback(
        progress_callback,
        "validation",
        "completed",
        {
            "result": validation_result,
            "elapsed_seconds": elapsed,
            "file_path": str(validation_file),
            "validation_status": validation_result.get("verification_summary", {}).get(
                "overall_status"
            ),
        },
    )

    return validation_result


def _run_correction_step(
    extraction_result: dict[str, Any],
    validation_result: dict[str, Any],
    pdf_path: Path,
    max_pages: int | None,
    publication_type: str,
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
    banner_label: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run correction step of the pipeline.

    Applies LLM-based corrections to extraction results based on validation
    feedback, then re-validates the corrected extraction.

    Args:
        extraction_result: Original extraction result to correct
        validation_result: Validation result containing issues to fix
        pdf_path: Path to original PDF file for LLM correction
        max_pages: Maximum number of pages to process (None = all pages)
        publication_type: Publication type from classification (for schema)
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates
        banner_label: Optional custom label for console banner (defaults to "CORRECTION")

    Returns:
        Tuple of (corrected_extraction, final_validation)

    Raises:
        PromptLoadError: If correction prompt cannot be loaded
        SchemaLoadError: If extraction schema cannot be loaded
        LLMError: If LLM API call fails
    """
    title = banner_label or "CORRECTION"
    console.print(f"\n[bold magenta]═══ {title} ═══[/bold magenta]\n")

    start_time = time.time()

    # Display pre-correction quality
    pre_summary = validation_result.get("verification_summary", {})
    console.print("[bold]Pre-Correction Quality:[/bold]")
    console.print(f"  Completeness:      {pre_summary.get('completeness_score', 0):.1%}")
    console.print(f"  Accuracy:          {pre_summary.get('accuracy_score', 0):.1%}")
    console.print(f"  Schema Compliance: {pre_summary.get('schema_compliance_score', 0):.1%}")
    console.print(f"  Critical Issues:   {pre_summary.get('critical_issues', 0)}")
    console.print(f"  Total Issues:      {pre_summary.get('total_issues', 0)}\n")

    validation_status = pre_summary.get("overall_status")

    _call_progress_callback(
        progress_callback,
        "correction",
        "starting",
        {"validation_status": validation_status},
    )

    try:
        # Strip metadata from dependencies before using in prompts
        extraction_clean = _strip_metadata_for_pipeline(extraction_result)
        validation_clean = _strip_metadata_for_pipeline(validation_result)

        # Load correction prompt and extraction schema
        correction_prompt = load_correction_prompt()
        extraction_schema = load_schema(publication_type)

        # Prepare correction context with clean extraction and validation feedback
        correction_context = f"""
ORIGINAL_EXTRACTION: {json.dumps(extraction_clean, indent=2)}

VALIDATION_REPORT: {json.dumps(validation_clean, indent=2)}

Systematically address all identified issues and produce corrected, complete,\
 schema-compliant JSON extraction.
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

        # Add pipeline metadata to corrected extraction
        elapsed_extraction = time.time() - start_time
        corrected_extraction["_pipeline_metadata"] = {
            "step": "correction",
            "sub_step": "extraction",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed_extraction,
            "llm_provider": _get_provider_name(llm),
            "model_used": corrected_extraction.get("_metadata", {}).get("model"),
            "max_pages": max_pages,
            "pdf_filename": pdf_path.name,
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
        }

        # Final validation of corrected extraction - use same dual validation approach
        console.print("[dim]Running final validation on corrected extraction...[/dim]")

        # Strip metadata from corrected extraction before validation
        corrected_extraction_clean = _strip_metadata_for_pipeline(corrected_extraction)

        # Re-run dual validation on clean corrected extraction
        final_validation = run_dual_validation(
            extraction_result=corrected_extraction_clean,
            pdf_path=pdf_path,
            max_pages=max_pages,
            publication_type=publication_type,
            llm=llm,
            console=console,
        )

        # Add pipeline metadata to final validation
        elapsed_validation = time.time() - start_time
        final_validation["_pipeline_metadata"] = {
            "step": "correction",
            "sub_step": "validation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed_validation - elapsed_extraction,
            "llm_provider": _get_provider_name(llm),
            "model_used": final_validation.get("_metadata", {}).get("model"),
            "max_pages": max_pages,
            "pdf_filename": pdf_path.name,
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
        }

        # Display post-correction quality and improvement
        post_summary = final_validation.get("verification_summary", {})
        console.print("\n[bold]Post-Correction Quality:[/bold]")

        # Calculate and display deltas for each metric
        for metric_key, metric_name in [
            ("completeness_score", "Completeness"),
            ("accuracy_score", "Accuracy"),
            ("schema_compliance_score", "Schema Compliance"),
        ]:
            pre_val = pre_summary.get(metric_key, 0)
            post_val = post_summary.get(metric_key, 0)
            delta = post_val - pre_val

            # Color code the delta
            if delta > 0:
                color = "green"
            elif delta < 0:
                color = "red"
            else:
                color = "yellow"

            console.print(f"  {metric_name:18} {post_val:.1%} [{color}]({delta:+.1%})[/{color}]")

        # Display issue counts with deltas
        pre_critical = pre_summary.get("critical_issues", 0)
        post_critical = post_summary.get("critical_issues", 0)
        delta_critical = post_critical - pre_critical
        console.print(f"  Critical Issues:   {post_critical} ({delta_critical:+d})")

        pre_total = pre_summary.get("total_issues", 0)
        post_total = post_summary.get("total_issues", 0)
        delta_total = post_total - pre_total
        console.print(f"  Total Issues:      {post_total} ({delta_total:+d})")

        # Overall improvement message
        pre_metrics = _extract_metrics(validation_result)
        post_metrics = _extract_metrics(final_validation)
        delta_overall = post_metrics["overall_quality"] - pre_metrics["overall_quality"]

        if delta_overall > 0:
            console.print(
                f"\n[green]✅ Correction improved quality by {delta_overall:+.1%}[/green]"
            )
        elif delta_overall < 0:
            console.print(f"\n[yellow]⚠️  Quality degraded by {delta_overall:.1%}[/yellow]")
        else:
            console.print("\n[yellow]→ No significant quality change[/yellow]")

        # Correction completed successfully
        elapsed = time.time() - start_time
        _call_progress_callback(
            progress_callback,
            "correction",
            "completed",
            {
                "result": corrected_extraction,
                "elapsed_seconds": elapsed,
                "extraction_file_path": None,  # Files will be saved by calling function
                "validation_file_path": None,  # Files will be saved by calling function
                "final_validation_status": final_validation.get("verification_summary", {}).get(
                    "overall_status"
                ),
            },
        )

        return corrected_extraction, final_validation

    except (PromptLoadError, LLMError, SchemaLoadError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Correction error: {e}[/red]")

        # Save error metadata (best effort)
        error_data = {
            "_pipeline_metadata": {
                "step": "correction",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": elapsed,
                "llm_provider": _get_provider_name(llm),
                "model_used": None,
                "max_pages": max_pages,
                "pdf_filename": pdf_path.name,
                "execution_mode": "streamlit" if progress_callback else "cli",
                "status": "failed",
                "error_message": str(e),
                "error_type": type(e).__name__,
            }
        }
        try:
            file_manager.save_json(error_data, "correction", "failed")
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to save error metadata: {e}[/yellow]")

        _call_progress_callback(
            progress_callback,
            "correction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


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


def run_validation_with_correction(
    pdf_path: Path,
    extraction_result: dict,
    classification_result: dict,
    llm_provider: str,
    file_manager: PipelineFileManager,
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    progress_callback: Callable | None = None,
) -> dict:
    """
    Run validation with automatic iterative correction until quality is sufficient.

    Workflow:
        1. Validate extraction (schema + LLM)
        2. If quality insufficient and iterations < max:
           - Run correction
           - Validate corrected output
           - Repeat until quality OK or max iterations reached
        3. Select best iteration based on quality metrics
        4. Return best extraction + validation + iteration history

    Args:
        pdf_path: Path to source PDF
        extraction_result: Initial extraction JSON
        classification_result: Classification result (for publication type)
        llm_provider: LLM provider name ("openai" | "claude")
        file_manager: File manager for saving iterations
        max_iterations: Maximum correction attempts (default: 3)
            IMPORTANT: Total iterations = initial validation + max_iterations corrections
            Example: max_iterations=3 means up to 4 total iterations (iter 0,1,2,3)
            Rationale: Naming reflects "corrections" not "total validations" for clarity
        quality_thresholds: Custom thresholds, defaults to:
            {
                'completeness_score': 0.90,
                'accuracy_score': 0.95,
                'schema_compliance_score': 0.95,
                'critical_issues': 0
            }
        progress_callback: Optional callback for progress updates

    Returns:
        dict: {
            'best_extraction': dict,  # Best extraction result
            'best_validation': dict,  # Validation of best extraction
            'iterations': list[dict],  # All iteration history with metrics
            'final_status': str,  # "passed" | "max_iterations_reached" | "failed"
            'iteration_count': int,  # Total iterations performed
            'improvement_trajectory': list[float],  # Quality scores per iteration
        }

    Raises:
        ValueError: If schema validation fails on any iteration
        LLMError: If LLM calls fail

    Example:
        >>> result = run_validation_with_correction(
        ...     pdf_path=Path("paper.pdf"),
        ...     extraction_result=extraction,
        ...     classification_result=classification,
        ...     llm_provider="openai",
        ...     file_manager=fm,
        ...     max_iterations=3
        ... )
        >>> result['final_status']  # "passed"
        >>> len(result['iterations'])  # 2 (initial + 1 correction)
        >>> result['best_extraction']  # Best quality extraction
    """
    # Initialize
    iterations = []
    current_extraction = extraction_result
    current_validation = None  # Will be set after first validation or from post-correction
    iteration_num = 0

    # Default thresholds
    if quality_thresholds is None:
        quality_thresholds = DEFAULT_QUALITY_THRESHOLDS

    # Extract publication_type for correction step
    publication_type = classification_result.get("publication_type", "unknown")

    # Display header and configuration
    console.print(
        "\n[bold magenta]═══ STEP 3: ITERATIVE VALIDATION & CORRECTION ═══[/bold magenta]\n"
    )
    console.print(f"[blue]Publication type: {publication_type}[/blue]")
    console.print(f"[blue]Max iterations: {max_iterations}[/blue]")
    console.print(
        f"[blue]Quality thresholds: Completeness ≥{quality_thresholds['completeness_score']:.0%}, "
        f"Accuracy ≥{quality_thresholds['accuracy_score']:.0%}, "
        f"Schema ≥{quality_thresholds['schema_compliance_score']:.0%}, "
        f"Critical issues = {quality_thresholds['critical_issues']}[/blue]\n"
    )

    # Get LLM instance
    llm = get_llm_provider(llm_provider)

    while iteration_num <= max_iterations:
        # Display iteration header
        console.print(f"\n[bold cyan]─── Iteration {iteration_num} ───[/bold cyan]")

        try:
            # Progress callback
            _call_progress_callback(
                progress_callback,
                STEP_VALIDATION_CORRECTION,
                "starting",
                {"iteration": iteration_num, "step": "validation"},
            )

            # STEP 1: Validate current extraction (only if not already validated)
            # After correction, we reuse the post-correction validation to avoid file overwrite
            if current_validation is None:
                validation_result = _run_validation_step(
                    extraction_result=current_extraction,
                    pdf_path=pdf_path,
                    max_pages=None,
                    classification_result=classification_result,
                    llm=llm,
                    file_manager=file_manager,
                    progress_callback=progress_callback,
                    banner_label=f"Iter {iteration_num} - VALIDATION",
                )

                # Check schema validation failure (critical error)
                schema_validation = validation_result.get("schema_validation", {})
                quality_score = schema_validation.get("quality_score", 0)

                if quality_score < 0.5:  # Schema quality threshold
                    # CRITICAL: Schema validation failed - STOP
                    return {
                        "best_extraction": None,
                        "best_validation": validation_result,
                        "iterations": iterations,
                        "final_status": "failed_schema_validation",
                        "iteration_count": iteration_num + 1,
                        "error": f"Schema validation failed (quality: {quality_score:.2f}). Cannot proceed with correction.",
                        "failed_at_iteration": iteration_num,
                    }

                # Save validation with iteration number
                validation_file = file_manager.save_json(
                    validation_result, "validation", iteration_number=iteration_num
                )
                console.print(f"[dim]Saved validation: {validation_file}[/dim]")
            else:
                # Reuse validation from previous correction step
                validation_result = current_validation
                console.print(
                    f"[dim]Reusing post-correction validation for iteration {iteration_num}[/dim]"
                )

            # Store iteration data
            metrics = _extract_metrics(validation_result)
            iteration_data = {
                "iteration_num": iteration_num,
                "extraction": current_extraction,
                "validation": validation_result,
                "metrics": metrics,
                "timestamp": datetime.now().isoformat(),
            }
            iterations.append(iteration_data)

            # Display quality scores
            console.print(f"\n[bold]Quality Scores (Iteration {iteration_num}):[/bold]")
            console.print(f"  [bold]Overall Quality:   {metrics['overall_quality']:.1%}[/bold]")
            status = validation_result.get("verification_summary", {}).get(
                "overall_status", "unknown"
            )
            console.print(f"  Validation Status: {status.title() if status else '—'}")

            # Display improvement tracking (if not first iteration)
            if len(iterations) > 1:
                prev_quality = iterations[-2]["metrics"]["overall_quality"]
                delta = metrics["overall_quality"] - prev_quality
                if delta > 0:
                    symbol, color = "↑", "green"
                elif delta < 0:
                    symbol, color = "↓", "red"
                else:
                    symbol, color = "→", "yellow"
                console.print(
                    f"  [{color}]Improvement: {symbol} {delta:+.3f} (prev: {prev_quality:.1%})[/{color}]"
                )

            # STEP 2: Check quality
            if is_quality_sufficient(validation_result, quality_thresholds):
                # SUCCESS: Quality is sufficient

                # Save best extraction + validation (current iteration is best)
                best_extraction_file = file_manager.save_json(
                    current_extraction, "extraction", status="best"
                )
                console.print(f"[green]✅ Best extraction saved: {best_extraction_file}[/green]")

                best_validation_file = file_manager.save_json(
                    validation_result, "validation", status="best"
                )
                console.print(f"[green]✅ Best validation saved: {best_validation_file}[/green]")

                # Save metadata
                metrics = _extract_metrics(validation_result)
                selection_metadata = {
                    "best_iteration_num": iteration_num,
                    "overall_quality": metrics["overall_quality"],
                    "completeness_score": metrics.get("completeness_score", 0),
                    "accuracy_score": metrics.get("accuracy_score", 0),
                    "schema_compliance_score": metrics.get("schema_compliance_score", 0),
                    "selection_reason": "passed",
                    "total_iterations": iteration_num + 1,
                    "timestamp": datetime.now().isoformat(),
                }
                file_manager.save_json(selection_metadata, "extraction", status="best-metadata")
                console.print("[dim]Saved best iteration metadata[/dim]")

                # Display success message and iteration summary
                console.print(
                    f"\n[green]✅ Quality sufficient at iteration {iteration_num}! Stopping.[/green]"
                )
                _print_iteration_summary(file_manager, iterations, iteration_num)

                _call_progress_callback(
                    progress_callback,
                    STEP_VALIDATION_CORRECTION,
                    "completed",
                    {
                        "final_status": "passed",
                        "iterations": iteration_num + 1,
                        "reason": "quality_sufficient",
                    },
                )

                return {
                    "best_extraction": current_extraction,
                    "best_validation": validation_result,
                    "iterations": iterations,
                    "final_status": "passed",
                    "iteration_count": iteration_num + 1,
                    "best_iteration": iteration_num,
                    "improvement_trajectory": [
                        it["metrics"]["overall_quality"] for it in iterations
                    ],
                }

            # STEP 3A: Check for quality degradation (early stopping)
            if iteration_num >= 2:  # Need at least 3 iterations to detect trend
                if _detect_quality_degradation(iterations, window=2):
                    # EARLY STOP: Quality is degrading
                    best = _select_best_iteration(iterations)

                    # Save best extraction + validation
                    best_extraction_file = file_manager.save_json(
                        best["extraction"], "extraction", status="best"
                    )
                    console.print(
                        f"[green]✅ Best extraction saved: {best_extraction_file}[/green]"
                    )

                    best_validation_file = file_manager.save_json(
                        best["validation"], "validation", status="best"
                    )
                    console.print(
                        f"[green]✅ Best validation saved: {best_validation_file}[/green]"
                    )

                    # Save metadata
                    selection_metadata = {
                        "best_iteration_num": best["iteration_num"],
                        "overall_quality": best["metrics"]["overall_quality"],
                        "completeness_score": best["metrics"].get("completeness_score", 0),
                        "accuracy_score": best["metrics"].get("accuracy_score", 0),
                        "schema_compliance_score": best["metrics"].get(
                            "schema_compliance_score", 0
                        ),
                        "selection_reason": "early_stopped_degradation",
                        "total_iterations": len(iterations),
                        "timestamp": datetime.now().isoformat(),
                    }
                    file_manager.save_json(selection_metadata, "extraction", status="best-metadata")
                    console.print("[dim]Saved best iteration metadata[/dim]")

                    # Display early stop message and iteration summary
                    console.print(
                        "\n[yellow]⚠️  Quality degrading - stopping early and selecting best[/yellow]"
                    )
                    console.print(
                        f"[yellow]Selected iteration {best['iteration_num']} as best (reason: quality degradation)[/yellow]"
                    )
                    _print_iteration_summary(file_manager, iterations, best["iteration_num"])

                    _call_progress_callback(
                        progress_callback,
                        STEP_VALIDATION_CORRECTION,
                        "completed",
                        {
                            "final_status": "early_stopped_degradation",
                            "iterations": len(iterations),
                            "best_iteration": best["iteration_num"],
                            "reason": "quality_degradation",
                        },
                    )

                    return {
                        "best_extraction": best["extraction"],
                        "best_validation": best["validation"],
                        "iterations": iterations,
                        "final_status": "early_stopped_degradation",
                        "iteration_count": len(iterations),
                        "best_iteration": best["iteration_num"],
                        "improvement_trajectory": [
                            it["metrics"]["overall_quality"] for it in iterations
                        ],
                        "warning": f'Early stopping triggered: quality degraded for 2 consecutive iterations. Using best result (iteration {best["iteration_num"]}).',
                    }

            # STEP 3B: Check if we can do another correction
            if iteration_num >= max_iterations:
                # MAX REACHED: Select best iteration
                best = _select_best_iteration(iterations)

                # Save best extraction + validation
                best_extraction_file = file_manager.save_json(
                    best["extraction"], "extraction", status="best"
                )
                console.print(f"[green]✅ Best extraction saved: {best_extraction_file}[/green]")

                best_validation_file = file_manager.save_json(
                    best["validation"], "validation", status="best"
                )
                console.print(f"[green]✅ Best validation saved: {best_validation_file}[/green]")

                # Save metadata
                selection_metadata = {
                    "best_iteration_num": best["iteration_num"],
                    "overall_quality": best["metrics"]["overall_quality"],
                    "completeness_score": best["metrics"].get("completeness_score", 0),
                    "accuracy_score": best["metrics"].get("accuracy_score", 0),
                    "schema_compliance_score": best["metrics"].get("schema_compliance_score", 0),
                    "selection_reason": "max_iterations_reached",
                    "total_iterations": len(iterations),
                    "timestamp": datetime.now().isoformat(),
                }
                file_manager.save_json(selection_metadata, "extraction", status="best-metadata")
                console.print("[dim]Saved best iteration metadata[/dim]")

                # Display max iterations message and iteration summary
                console.print(
                    f"\n[yellow]⚠️  Max iterations ({max_iterations}) reached - selecting best[/yellow]"
                )
                console.print(
                    f"[yellow]Selected iteration {best['iteration_num']} as best (reason: max iterations)[/yellow]"
                )
                _print_iteration_summary(file_manager, iterations, best["iteration_num"])

                _call_progress_callback(
                    progress_callback,
                    STEP_VALIDATION_CORRECTION,
                    "completed",
                    {
                        "final_status": "max_iterations_reached",
                        "iterations": len(iterations),
                        "best_iteration": best["iteration_num"],
                        "reason": "max_iterations",
                    },
                )

                return {
                    "best_extraction": best["extraction"],
                    "best_validation": best["validation"],
                    "iterations": iterations,
                    "final_status": "max_iterations_reached",
                    "iteration_count": len(iterations),
                    "best_iteration": best["iteration_num"],
                    "improvement_trajectory": [
                        it["metrics"]["overall_quality"] for it in iterations
                    ],
                    "warning": f'Maximum iterations ({max_iterations}) reached. Using best result (iteration {best["iteration_num"]}).',
                }

            # STEP 4: Run correction for next iteration
            console.print(
                f"\n[yellow]Quality insufficient (iteration {iteration_num}). Running correction...[/yellow]"
            )
            iteration_num += 1

            _call_progress_callback(
                progress_callback,
                STEP_VALIDATION_CORRECTION,
                "starting",
                {"iteration": iteration_num, "step": "correction"},
            )

            # Call correction step - returns tuple (corrected_extraction, final_validation)
            corrected_extraction, final_validation = _run_correction_step(
                extraction_result=current_extraction,
                validation_result=validation_result,
                pdf_path=pdf_path,
                max_pages=None,
                publication_type=publication_type,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
                banner_label=f"Iter {iteration_num} - CORRECTION",
            )

            # Save corrected extraction with iteration number
            corrected_file = file_manager.save_json(
                corrected_extraction, "extraction", iteration_number=iteration_num
            )
            console.print(f"[dim]Saved corrected extraction: {corrected_file}[/dim]")

            # Save post-correction validation with iteration number
            validation_file = file_manager.save_json(
                final_validation, "validation", iteration_number=iteration_num
            )
            console.print(f"[dim]Saved post-correction validation: {validation_file}[/dim]")

            # Update current extraction and validation for next iteration
            # Strip metadata (including correction_notes) to prevent leakage
            current_extraction = _strip_metadata_for_pipeline(corrected_extraction)
            # Reuse post-correction validation for next iteration to avoid re-validating and file overwrite
            current_validation = final_validation

            # Loop continues...

        except LLMError as e:
            # LLM API failure - retry with exponential backoff
            max_retries = 3
            retry_successful = False

            for retry in range(max_retries):
                wait_time = 2**retry  # 1s, 2s, 4s
                console.print(
                    f"[yellow]⚠️  LLM call failed, retrying in {wait_time}s... (attempt {retry+1}/{max_retries})[/yellow]"
                )
                time.sleep(wait_time)

                try:
                    # Retry the current step based on iteration stage
                    if iteration_num == len(iterations):
                        # Failed during validation - retry validation
                        validation_result = _run_validation_step(
                            extraction_result=current_extraction,
                            pdf_path=pdf_path,
                            max_pages=None,
                            classification_result=classification_result,
                            llm=llm,
                            file_manager=file_manager,
                            progress_callback=progress_callback,
                            banner_label=f"Iter {iteration_num} - VALIDATION",
                        )
                        retry_successful = True
                        break
                    else:
                        # Failed during correction - retry correction
                        corrected_extraction, final_validation = _run_correction_step(
                            extraction_result=current_extraction,
                            validation_result=validation_result,
                            pdf_path=pdf_path,
                            max_pages=None,
                            publication_type=publication_type,
                            llm=llm,
                            file_manager=file_manager,
                            progress_callback=progress_callback,
                            banner_label=f"Iter {iteration_num} - CORRECTION (retry)",
                        )

                        # Save corrected extraction and post-correction validation with iteration number
                        corrected_file = file_manager.save_json(
                            corrected_extraction, "extraction", iteration_number=iteration_num
                        )
                        console.print(
                            f"[dim]Saved corrected extraction (retry): {corrected_file}[/dim]"
                        )

                        validation_file = file_manager.save_json(
                            final_validation, "validation", iteration_number=iteration_num
                        )
                        console.print(
                            f"[dim]Saved post-correction validation (retry): {validation_file}[/dim]"
                        )

                        # Update current extraction and validation for next iteration
                        # Strip metadata (including correction_notes) to prevent leakage
                        current_extraction = _strip_metadata_for_pipeline(corrected_extraction)
                        # Reuse post-correction validation for next iteration to avoid re-validating and file overwrite
                        current_validation = final_validation

                        retry_successful = True
                        break
                except LLMError:
                    continue

            if not retry_successful:
                # All retries exhausted
                best = _select_best_iteration(iterations) if iterations else None

                # Save best extraction + validation if available
                if best:
                    best_extraction_file = file_manager.save_json(
                        best["extraction"], "extraction", status="best"
                    )
                    console.print(
                        f"[green]✅ Best extraction saved: {best_extraction_file}[/green]"
                    )

                    best_validation_file = file_manager.save_json(
                        best["validation"], "validation", status="best"
                    )
                    console.print(
                        f"[green]✅ Best validation saved: {best_validation_file}[/green]"
                    )

                    # Save metadata
                    selection_metadata = {
                        "best_iteration_num": best["iteration_num"],
                        "overall_quality": best["metrics"]["overall_quality"],
                        "completeness_score": best["metrics"].get("completeness_score", 0),
                        "accuracy_score": best["metrics"].get("accuracy_score", 0),
                        "schema_compliance_score": best["metrics"].get(
                            "schema_compliance_score", 0
                        ),
                        "selection_reason": "failed_llm_error",
                        "total_iterations": len(iterations),
                        "timestamp": datetime.now().isoformat(),
                    }
                    file_manager.save_json(selection_metadata, "extraction", status="best-metadata")
                    console.print("[dim]Saved best iteration metadata[/dim]")

                return {
                    "best_extraction": best["extraction"] if best else current_extraction,
                    "best_validation": best["validation"] if best else None,
                    "iterations": iterations,
                    "final_status": "failed_llm_error",
                    "iteration_count": len(iterations),
                    "best_iteration": best["iteration_num"] if best else 0,
                    "error": f"LLM provider error after {max_retries} retries: {str(e)}",
                    "failed_at_iteration": iteration_num,
                }

        except json.JSONDecodeError as e:
            # Invalid JSON from correction - treat as critical error
            console.print(
                f"[red]❌ Correction returned invalid JSON at iteration {iteration_num}[/red]"
            )
            best = _select_best_iteration(iterations) if iterations else None

            # Save best extraction + validation if available
            if best:
                best_extraction_file = file_manager.save_json(
                    best["extraction"], "extraction", status="best"
                )
                console.print(f"[green]✅ Best extraction saved: {best_extraction_file}[/green]")

                best_validation_file = file_manager.save_json(
                    best["validation"], "validation", status="best"
                )
                console.print(f"[green]✅ Best validation saved: {best_validation_file}[/green]")

                # Save metadata
                selection_metadata = {
                    "best_iteration_num": best["iteration_num"],
                    "overall_quality": best["metrics"]["overall_quality"],
                    "completeness_score": best["metrics"].get("completeness_score", 0),
                    "accuracy_score": best["metrics"].get("accuracy_score", 0),
                    "schema_compliance_score": best["metrics"].get("schema_compliance_score", 0),
                    "selection_reason": "failed_invalid_json",
                    "total_iterations": len(iterations),
                    "timestamp": datetime.now().isoformat(),
                }
                file_manager.save_json(selection_metadata, "extraction", status="best-metadata")
                console.print("[dim]Saved best iteration metadata[/dim]")

            return {
                "best_extraction": best["extraction"] if best else current_extraction,
                "best_validation": best["validation"] if best else None,
                "iterations": iterations,
                "final_status": "failed_invalid_json",
                "iteration_count": len(iterations),
                "best_iteration": best["iteration_num"] if best else 0,
                "error": f"Correction produced invalid JSON: {str(e)}",
                "failed_at_iteration": iteration_num,
            }

        except Exception as e:
            # Unexpected error - fail gracefully
            console.print(f"[red]❌ Unexpected error at iteration {iteration_num}: {str(e)}[/red]")
            best = _select_best_iteration(iterations) if len(iterations) > 0 else None

            # Save best extraction + validation if available
            if best:
                best_extraction_file = file_manager.save_json(
                    best["extraction"], "extraction", status="best"
                )
                console.print(f"[green]✅ Best extraction saved: {best_extraction_file}[/green]")

                best_validation_file = file_manager.save_json(
                    best["validation"], "validation", status="best"
                )
                console.print(f"[green]✅ Best validation saved: {best_validation_file}[/green]")

                # Save metadata
                selection_metadata = {
                    "best_iteration_num": best["iteration_num"],
                    "overall_quality": best["metrics"]["overall_quality"],
                    "completeness_score": best["metrics"].get("completeness_score", 0),
                    "accuracy_score": best["metrics"].get("accuracy_score", 0),
                    "schema_compliance_score": best["metrics"].get("schema_compliance_score", 0),
                    "selection_reason": "failed_unexpected_error",
                    "total_iterations": len(iterations),
                    "timestamp": datetime.now().isoformat(),
                }
                file_manager.save_json(selection_metadata, "extraction", status="best-metadata")
                console.print("[dim]Saved best iteration metadata[/dim]")

            return {
                "best_extraction": best["extraction"] if best else current_extraction,
                "best_validation": best["validation"] if best else None,
                "iterations": iterations,
                "final_status": "failed_unexpected_error",
                "iteration_count": len(iterations),
                "best_iteration": best["iteration_num"] if best else 0,
                "error": f"Unexpected error: {str(e)}",
                "failed_at_iteration": iteration_num,
            }


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


def _run_classification_step(
    pdf_path: Path,
    max_pages: int | None,
    llm_provider: str,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
    have_llm_support: bool,
) -> dict[str, Any]:
    """
    Run classification step of the pipeline.

    Identifies publication type and extracts metadata from PDF using LLM.

    Args:
        pdf_path: Path to PDF file to process
        max_pages: Maximum pages to process (None = all pages)
        llm_provider: LLM provider name ("openai" or "claude")
        file_manager: File manager for saving results
        progress_callback: Optional callback for progress updates
        have_llm_support: Whether LLM modules are available

    Returns:
        Classification result dictionary with keys:
        - publication_type: str
        - metadata: dict

    Raises:
        RuntimeError: If LLM support not available
        LLMError: If LLM API call fails
        SchemaLoadError: If classification schema cannot be loaded
        PromptLoadError: If classification prompt cannot be loaded

    Example:
        >>> file_mgr = PipelineFileManager(Path("paper.pdf"))
        >>> result = _run_classification_step(
        ...     pdf_path=Path("paper.pdf"),
        ...     max_pages=20,
        ...     llm_provider="openai",
        ...     file_manager=file_mgr,
        ...     progress_callback=None,
        ...     have_llm_support=True
        ... )
        >>> result["publication_type"]
        'interventional_trial'
    """
    console.print("\n[bold magenta]═══ STEP 1: CLASSIFICATION ═══[/bold magenta]\n")

    if not have_llm_support:
        console.print("[red]❌ LLM support not available[/red]")
        raise RuntimeError(
            "LLM support is required for pipeline execution. "
            "Please install required dependencies: pip install openai anthropic"
        )

    # Start classification with callback
    start_time = time.time()
    _call_progress_callback(
        progress_callback,
        "classification",
        "starting",
        {"pdf_path": str(pdf_path), "max_pages": max_pages},
    )

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

        publication_type = classification_result.get("publication_type", "unknown")
        confidence = classification_result.get("classification_confidence")
        if confidence is not None:
            console.print(
                f"[cyan]🔎 Predicted type: {publication_type} "
                f"({confidence:.1%} confidence)[/cyan]"
            )
        else:
            console.print(f"[cyan]🔎 Predicted type: {publication_type}[/cyan]")

        # Add pipeline metadata
        elapsed = time.time() - start_time
        classification_result["_pipeline_metadata"] = {
            "step": "classification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": elapsed,
            "llm_provider": llm_provider,
            "model_used": classification_result.get("_metadata", {}).get("model"),
            "max_pages": max_pages,
            "pdf_filename": pdf_path.name,
            "execution_mode": "streamlit" if progress_callback else "cli",
            "status": "success",
        }

        # Display classification result summary
        publication_type = classification_result.get("publication_type", "unknown")
        model_used = classification_result.get("_metadata", {}).get("model", llm_provider)

        console.print("\n[bold]Classification Result:[/bold]")
        console.print(f"  Publication Type: [cyan]{publication_type}[/cyan]")
        console.print(f"  Model: [dim]{model_used}[/dim]")
        console.print(f"  Duration: [dim]{elapsed:.1f}s[/dim]\n")

        # Save classification result
        classification_file = file_manager.save_json(classification_result, "classification")
        console.print(f"[dim]Saved: {classification_file.name}[/dim]")
        console.print("[green]✅ Classification complete[/green]")

        # Classification completed successfully
        elapsed = time.time() - start_time
        _call_progress_callback(
            progress_callback,
            "classification",
            "completed",
            {
                "result": classification_result,
                "elapsed_seconds": elapsed,
                "file_path": str(classification_file),
            },
        )

        return classification_result

    except (PromptLoadError, LLMError, SchemaLoadError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Classification error: {e}[/red]")

        # Save error metadata (best effort)
        error_data = {
            "_pipeline_metadata": {
                "step": "classification",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": elapsed,
                "llm_provider": llm_provider,
                "model_used": None,
                "max_pages": max_pages,
                "pdf_filename": pdf_path.name,
                "execution_mode": "streamlit" if progress_callback else "cli",
                "status": "failed",
                "error_message": str(e),
                "error_type": type(e).__name__,
            }
        }
        try:
            file_manager.save_json(error_data, "classification", "failed")
        except Exception:
            pass  # Don't fail the error handling

        _call_progress_callback(
            progress_callback,
            "classification",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def _run_appraisal_step(
    extraction_result: dict[str, Any],
    publication_type: str,
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """
    Run critical appraisal step of the pipeline.

    Performs tool-specific critical appraisal (RoB 2, ROBINS-I, PROBAST, AMSTAR 2, etc.)
    on validated extraction data to assess study quality, risk of bias, and applicability.

    Args:
        extraction_result: Validated extraction result to appraise
        publication_type: Publication type from classification (for tool routing)
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates

    Returns:
        Dictionary containing appraisal results with risk_of_bias, GRADE, applicability

    Raises:
        UnsupportedPublicationType: If publication type has no appraisal support
        PromptLoadError: If appraisal prompt cannot be loaded
        SchemaLoadError: If appraisal schema cannot be loaded
        LLMError: If LLM API call fails

    Note:
        The 'diagnostic' publication type shares the prediction prompt (Appraisal-prediction.txt)
        because PROBAST and QUADAS tools have similar structure.
    """
    console.print("[bold cyan]📊 Critical Appraisal[/bold cyan]")

    start_time = time.time()

    # Strip metadata from extraction before using
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)

    # Route to appropriate appraisal prompt
    try:
        prompt_name = _get_appraisal_prompt_name(publication_type)
    except UnsupportedPublicationType as e:
        console.print(f"[red]❌ {e}[/red]")
        raise

    _call_progress_callback(
        progress_callback,
        STEP_APPRAISAL,
        "starting",
        {"publication_type": publication_type, "prompt": prompt_name},
    )

    try:
        # Load appropriate appraisal prompt and schema
        appraisal_prompt = load_appraisal_prompt(publication_type)
        appraisal_schema = load_schema("appraisal")

        console.print(f"[dim]Running {prompt_name} critical appraisal...")
        console.print(f"[dim]Tool routing: {publication_type} → {prompt_name}[/dim]")

        # Run appraisal with extraction context (no PDF needed)
        # Appraisal works from extraction data, not original PDF
        appraisal_result = llm.generate_json_with_schema(
            schema=appraisal_schema,
            system_prompt=appraisal_prompt,
            prompt=f"EXTRACTION_JSON:\n{json.dumps(extraction_clean, indent=2)}",
            schema_name=f"{publication_type}_appraisal",
        )

        console.print("[green]✅ Critical appraisal completed[/green]")

        # Add pipeline metadata
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
        console.print(f"[red]❌ Appraisal error: {e}[/red]")

        # Save error metadata
        error_data = {
            "_pipeline_metadata": {
                "step": "appraisal",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": elapsed,
                "llm_provider": _get_provider_name(llm),
                "model_used": None,
                "execution_mode": "streamlit" if progress_callback else "cli",
                "status": "failed",
                "error_message": str(e),
                "error_type": type(e).__name__,
                "publication_type": publication_type,
            }
        }
        try:
            file_manager.save_json(error_data, STEP_APPRAISAL, status="failed")
        except Exception:
            pass  # Don't fail the error handling

        _call_progress_callback(
            progress_callback,
            STEP_APPRAISAL,
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def _run_appraisal_validation_step(
    appraisal_result: dict[str, Any],
    extraction_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """
    Run appraisal validation step of the pipeline.

    Validates appraisal results for logical consistency, completeness, evidence support,
    and schema compliance using the Appraisal-validation.txt prompt.

    Args:
        appraisal_result: Appraisal result to validate
        extraction_result: Original extraction (for evidence cross-checking)
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates

    Returns:
        Dictionary containing validation results with validation_summary and quality scores

    Raises:
        PromptLoadError: If validation prompt cannot be loaded
        SchemaLoadError: If validation schema cannot be loaded
        LLMError: If LLM API call fails
    """
    console.print("[bold cyan]🔍 Appraisal Validation[/bold cyan]")

    start_time = time.time()
    _call_progress_callback(progress_callback, STEP_APPRAISAL_VALIDATION, "starting", {})

    # Strip metadata from dependencies before using
    appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)

    try:
        # Load appraisal validation prompt and schemas
        validation_prompt = load_appraisal_validation_prompt()
        appraisal_schema = load_schema("appraisal")
        validation_report_schema = load_schema("appraisal_validation")

        # Prepare context with appraisal, extraction, and schema
        context = f"""APPRAISAL_JSON:
{json.dumps(appraisal_clean, indent=2)}

EXTRACTION_JSON (for evidence checking):
{json.dumps(extraction_clean, indent=2)}

APPRAISAL_SCHEMA:
{json.dumps(appraisal_schema, indent=2)}"""

        console.print(
            "[dim]Validating appraisal for logical consistency, completeness, evidence support...[/dim]"
        )

        # Run validation (returns validation report with scores)
        validation_result = llm.generate_json_with_schema(
            schema=validation_report_schema,
            system_prompt=validation_prompt,
            prompt=context,
            schema_name="appraisal_validation",
        )

        console.print("[green]✅ Appraisal validation completed[/green]")

        # Add pipeline metadata
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
                "quality_score": validation_result.get("validation_summary", {}).get(
                    "quality_score"
                ),
            },
        )

        return validation_result

    except (PromptLoadError, SchemaLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Appraisal validation error: {e}[/red]")

        _call_progress_callback(
            progress_callback,
            STEP_APPRAISAL_VALIDATION,
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def _run_appraisal_correction_step(
    appraisal_result: dict[str, Any],
    validation_result: dict[str, Any],
    extraction_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """
    Run appraisal correction step of the pipeline.

    Applies LLM-based corrections to appraisal results based on validation
    feedback (fixes logical inconsistencies, completes missing data, strengthens evidence support).

    Args:
        appraisal_result: Original appraisal result to correct
        validation_result: Validation result containing issues to fix
        extraction_result: Original extraction (for re-checking evidence)
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates

    Returns:
        Corrected appraisal result (ready for re-validation)

    Raises:
        PromptLoadError: If correction prompt cannot be loaded
        SchemaLoadError: If appraisal schema cannot be loaded
        LLMError: If LLM API call fails
    """
    console.print("[bold cyan]🔧 Appraisal Correction[/bold cyan]")

    start_time = time.time()
    validation_status = validation_result.get("validation_summary", {}).get("overall_status")

    _call_progress_callback(
        progress_callback,
        "appraisal_correction",
        "starting",
        {"validation_status": validation_status},
    )

    # Strip metadata from dependencies
    appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)
    validation_clean = _strip_metadata_for_pipeline(validation_result)
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)

    try:
        # Load correction prompt and schema
        correction_prompt = load_appraisal_correction_prompt()
        appraisal_schema = load_schema("appraisal")

        # Prepare context with validation report, original appraisal, extraction, and schema
        context = f"""VALIDATION_REPORT:
{json.dumps(validation_clean, indent=2)}

ORIGINAL_APPRAISAL:
{json.dumps(appraisal_clean, indent=2)}

EXTRACTION_JSON (for re-checking evidence):
{json.dumps(extraction_clean, indent=2)}

APPRAISAL_SCHEMA:
{json.dumps(appraisal_schema, indent=2)}"""

        console.print("[dim]Correcting appraisal based on validation issues...[/dim]")

        # Run correction
        corrected_appraisal = llm.generate_json_with_schema(
            schema=appraisal_schema,
            system_prompt=correction_prompt,
            prompt=context,
            schema_name="appraisal_correction",
        )

        console.print("[green]✅ Appraisal correction completed[/green]")

        # Add pipeline metadata
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
            {
                "result": corrected_appraisal,
                "elapsed_seconds": elapsed,
            },
        )

        return corrected_appraisal

    except (PromptLoadError, SchemaLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Appraisal correction error: {e}[/red]")

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
    """
    Run a single appraisal + validation cycle without iterative correction.

    Saves backward-compatible filenames (paper-appraisal.json) plus best files.
    """
    console.print("\n[bold magenta]═══ CRITICAL APPRAISAL (Single Pass) ═══[/bold magenta]\n")

    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")
    if not publication_type:
        raise ValueError("Classification result missing publication_type")

    if quality_thresholds is None:
        quality_thresholds = APPRAISAL_QUALITY_THRESHOLDS

    llm = get_llm_provider(llm_provider)

    appraisal = _run_appraisal_step(
        extraction_result=extraction_result,
        publication_type=publication_type,
        llm=llm,
        file_manager=file_manager,
        progress_callback=progress_callback,
    )

    validation = _run_appraisal_validation_step(
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

    # Save backward-compatible filenames (no iteration suffix)
    file_manager.save_json(appraisal, STEP_APPRAISAL)
    file_manager.save_json(validation, STEP_APPRAISAL_VALIDATION)
    file_manager.save_best_appraisal(appraisal, validation)

    improvement_trajectory = [metrics["quality_score"]]
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
        "improvement_trajectory": improvement_trajectory,
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

    This function implements the full appraisal workflow with validation/correction loop:
        1. Route to appropriate appraisal prompt based on publication_type
        2. Run initial appraisal (iteration 0)
        3. Validate appraisal (logical consistency, completeness, evidence support)
        4. If quality insufficient and iterations < max:
           - Run correction
           - Validate corrected appraisal
           - Repeat until quality OK or max iterations reached
        5. Select best iteration based on quality metrics
        6. Return best appraisal + validation + iteration history

    Args:
        extraction_result: Validated extraction JSON (input for appraisal)
        classification_result: Classification result (for publication_type routing)
        llm_provider: LLM provider name ("openai" | "claude")
        file_manager: File manager for saving appraisal iterations
        max_iterations: Maximum correction attempts after initial appraisal (default: 3)
            Iteration 0: Initial appraisal + validation
            Iterations 1-N: Correction attempts (if quality insufficient)
            Example: max_iterations=3 → up to 4 total iterations (0,1,2,3)
        quality_thresholds: Custom thresholds, defaults to APPRAISAL_QUALITY_THRESHOLDS:
            {
                'logical_consistency_score': 0.90,
                'completeness_score': 0.85,
                'evidence_support_score': 0.90,
                'schema_compliance_score': 0.95,
                'critical_issues': 0
            }
        progress_callback: Optional callback for progress updates

    Returns:
        dict: {
            'best_appraisal': dict,  # Best appraisal result
            'best_validation': dict,  # Validation of best appraisal
            'best_iteration': int,  # Iteration number of best result (for non-passed statuses)
            'iterations': list[dict],  # All iteration history with metrics
            'final_status': str,  # "passed" | "max_iterations_reached" | "early_stopped_degradation" | "failed"
            'iteration_count': int,  # Total iterations performed
            'improvement_trajectory': list[float],  # Quality scores per iteration
        }

    Raises:
        UnsupportedPublicationType: If publication_type not supported for appraisal
        SchemaLoadError: If appraisal.schema.json cannot be loaded or is invalid
        LLMProviderError: If LLM provider initialization fails
        LLMError: If LLM calls fail after retries

    Example:
        >>> appraisal_result = run_appraisal_with_correction(
        ...     extraction_result=extraction,
        ...     classification_result=classification,
        ...     llm_provider="openai",
        ...     file_manager=file_mgr,
        ...     max_iterations=3
        ... )
        >>> appraisal_result['final_status']
        'passed'
        >>> appraisal_result['best_appraisal']['risk_of_bias']['overall']
        'Some concerns'
    """
    console.print(
        "\n[bold magenta]═══ CRITICAL APPRAISAL WITH ITERATIVE CORRECTION ═══[/bold magenta]\n"
    )

    # Extract publication type from classification
    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")

    if not publication_type:
        raise ValueError("Classification result missing publication_type")

    console.print(f"[blue]Publication type: {publication_type}[/blue]")
    console.print(f"[blue]Max iterations: {max_iterations}[/blue]\n")

    # Use default thresholds if not provided
    if quality_thresholds is None:
        quality_thresholds = APPRAISAL_QUALITY_THRESHOLDS

    # Initialize LLM provider
    try:
        llm = get_llm_provider(llm_provider)
    except Exception as e:
        console.print(f"[red]❌ LLM provider error: {e}[/red]")
        raise

    # Track iterations
    iterations = []
    current_appraisal = None
    current_validation = None
    iteration_num = 0

    # Main iteration loop
    while iteration_num <= max_iterations:
        console.print(f"\n[bold cyan]─── Iteration {iteration_num} ───[/bold cyan]")

        try:
            # Step 1: Run appraisal (or use corrected from previous iteration)
            if iteration_num == 0:
                # Initial appraisal
                current_appraisal = _run_appraisal_step(
                    extraction_result=extraction_result,
                    publication_type=publication_type,
                    llm=llm,
                    file_manager=file_manager,
                    progress_callback=progress_callback,
                )
            else:
                # Correction already ran at end of previous iteration
                # current_appraisal already contains corrected version
                pass

            # Step 2: Validate appraisal
            current_validation = _run_appraisal_validation_step(
                appraisal_result=current_appraisal,
                extraction_result=extraction_result,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
            )

            # Save appraisal + validation iteration via file manager helper
            appraisal_file, validation_file = file_manager.save_appraisal_iteration(
                iteration=iteration_num,
                appraisal_result=current_appraisal,
                validation_result=current_validation,
            )
            console.print(f"[dim]Saved: {appraisal_file.name}[/dim]")
            if validation_file:
                console.print(f"[dim]Saved: {validation_file.name}[/dim]")

            # Extract metrics
            metrics = _extract_appraisal_metrics(current_validation)

            # Store iteration data
            iteration_data = {
                "iteration_num": iteration_num,
                "appraisal": current_appraisal,
                "validation": current_validation,
                "metrics": metrics,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            iterations.append(iteration_data)

            # Display quality scores
            console.print(f"\n[bold]Quality Scores (Iteration {iteration_num}):[/bold]")
            console.print(f"  Logical Consistency: {metrics['logical_consistency_score']:.2f}")
            console.print(f"  Completeness:        {metrics['completeness_score']:.2f}")
            console.print(f"  Evidence Support:    {metrics['evidence_support_score']:.2f}")
            console.print(f"  Schema Compliance:   {metrics['schema_compliance_score']:.2f}")
            console.print(f"  [bold]Quality Score:       {metrics['quality_score']:.2f}[/bold]")
            console.print(f"  Critical Issues:     {metrics['critical_issues']}")

            # Display improvement trajectory if not first iteration
            if len(iterations) > 1:
                prev_score = iterations[-2]["metrics"]["quality_score"]
                current_score = metrics["quality_score"]
                delta = current_score - prev_score
                if delta > 0:
                    delta_symbol = "↑"
                    delta_color = "green"
                elif delta < 0:
                    delta_symbol = "↓"
                    delta_color = "red"
                else:
                    delta_symbol = "→"
                    delta_color = "yellow"
                console.print(
                    f"  [{delta_color}]Improvement: {delta_symbol} {delta:+.3f} "
                    f"(prev: {prev_score:.2f})[/{delta_color}]"
                )

            # Check if quality is sufficient
            if is_appraisal_quality_sufficient(current_validation, quality_thresholds):
                console.print(
                    f"\n[green]✅ Quality sufficient at iteration {iteration_num}! Stopping.[/green]"
                )

                # Save best files
                best_appraisal_file, best_validation_file = file_manager.save_best_appraisal(
                    current_appraisal, current_validation
                )

                console.print(f"[green]Saved best: {best_appraisal_file.name}[/green]")
                console.print(f"[green]Saved best: {best_validation_file.name}[/green]")

                # Summary of saved iterations
                console.print("\n[bold]Saved Appraisal Iterations:[/bold]")
                all_iterations = file_manager.get_appraisal_iterations()
                for it in all_iterations:
                    status_symbol = "✅" if it["validation_exists"] else "⚠️"
                    console.print(
                        f"  {status_symbol} Iteration {it['iteration_num']}: "
                        f"{it['appraisal_file'].name}"
                    )
                best_file = file_manager.get_filename("appraisal", status="best")
                if best_file.exists():
                    console.print(f"  🏆 Best: {best_file.name}")

                improvement_trajectory = [it["metrics"]["quality_score"] for it in iterations]

                return {
                    "best_appraisal": current_appraisal,
                    "best_validation": current_validation,
                    "best_iteration": iteration_num,
                    "iterations": iterations,
                    "final_status": "passed",
                    "iteration_count": iteration_num + 1,
                    "improvement_trajectory": improvement_trajectory,
                }

            # Check for quality degradation (early stopping)
            if _detect_quality_degradation(iterations, window=2):
                console.print(
                    "\n[yellow]⚠️  Quality degrading - stopping early and selecting best[/yellow]"
                )

                # Select best iteration
                best = _select_best_appraisal_iteration(iterations)
                best_appraisal = best["appraisal"]
                best_validation = best["validation"]

                # Save best files
                best_appraisal_file, best_validation_file = file_manager.save_best_appraisal(
                    best_appraisal, best_validation
                )

                console.print(
                    f"[yellow]Selected iteration {best['iteration_num']} as best "
                    f"(reason: {best['selection_reason']})[/yellow]"
                )

                # Summary of saved iterations
                console.print("\n[bold]Saved Appraisal Iterations:[/bold]")
                all_iterations = file_manager.get_appraisal_iterations()
                for it in all_iterations:
                    status_symbol = "✅" if it["validation_exists"] else "⚠️"
                    console.print(
                        f"  {status_symbol} Iteration {it['iteration_num']}: "
                        f"{it['appraisal_file'].name}"
                    )
                best_file = file_manager.get_filename("appraisal", status="best")
                if best_file.exists():
                    console.print(f"  🏆 Best: {best_file.name}")

                improvement_trajectory = [it["metrics"]["quality_score"] for it in iterations]

                return {
                    "best_appraisal": best_appraisal,
                    "best_validation": best_validation,
                    "best_iteration": best["iteration_num"],
                    "iterations": iterations,
                    "final_status": "early_stopped_degradation",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": improvement_trajectory,
                }

            # Check if max iterations reached
            if iteration_num >= max_iterations:
                console.print(
                    f"\n[yellow]⚠️  Max iterations ({max_iterations}) reached - selecting best[/yellow]"
                )

                # Select best iteration
                best = _select_best_appraisal_iteration(iterations)
                best_appraisal = best["appraisal"]
                best_validation = best["validation"]

                # Save best files
                best_appraisal_file, best_validation_file = file_manager.save_best_appraisal(
                    best_appraisal, best_validation
                )

                console.print(
                    f"[yellow]Selected iteration {best['iteration_num']} as best "
                    f"(reason: {best['selection_reason']})[/yellow]"
                )

                # Summary of saved iterations
                console.print("\n[bold]Saved Appraisal Iterations:[/bold]")
                all_iterations = file_manager.get_appraisal_iterations()
                for it in all_iterations:
                    status_symbol = "✅" if it["validation_exists"] else "⚠️"
                    console.print(
                        f"  {status_symbol} Iteration {it['iteration_num']}: "
                        f"{it['appraisal_file'].name}"
                    )
                best_file = file_manager.get_filename("appraisal", status="best")
                if best_file.exists():
                    console.print(f"  🏆 Best: {best_file.name}")

                improvement_trajectory = [it["metrics"]["quality_score"] for it in iterations]

                return {
                    "best_appraisal": best_appraisal,
                    "best_validation": best_validation,
                    "best_iteration": best["iteration_num"],
                    "iterations": iterations,
                    "final_status": "max_iterations_reached",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": improvement_trajectory,
                }

            # Quality insufficient and iterations remain - run correction
            console.print(
                f"\n[yellow]Quality insufficient (iteration {iteration_num}). Running correction...[/yellow]"
            )

            # Step 3: Run correction for next iteration
            current_appraisal = _run_appraisal_correction_step(
                appraisal_result=current_appraisal,
                validation_result=current_validation,
                extraction_result=extraction_result,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
            )

            # Increment iteration for next loop
            iteration_num += 1

        except (UnsupportedPublicationType, PromptLoadError, SchemaLoadError) as e:
            # These are fatal errors - cannot continue
            console.print(f"\n[red]❌ Fatal error: {e}[/red]")

            # If we have any iterations, save best available
            if iterations:
                console.print("[yellow]Saving best iteration from partial results...[/yellow]")
                best = _select_best_appraisal_iteration(iterations)
                file_manager.save_best_appraisal(best["appraisal"], best["validation"])

                improvement_trajectory = [it["metrics"]["quality_score"] for it in iterations]

                return {
                    "best_appraisal": best["appraisal"],
                    "best_validation": best["validation"],
                    "iterations": iterations,
                    "final_status": "failed",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": improvement_trajectory,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }

            # No iterations - re-raise
            raise

        except LLMError as e:
            # LLM errors - try to continue or use best available
            console.print(f"\n[red]❌ LLM error at iteration {iteration_num}: {e}[/red]")

            # If we have any iterations, save best available
            if iterations:
                console.print("[yellow]Using best iteration from previous attempts...[/yellow]")
                best = _select_best_appraisal_iteration(iterations)
                file_manager.save_best_appraisal(best["appraisal"], best["validation"])

                improvement_trajectory = [it["metrics"]["quality_score"] for it in iterations]

                return {
                    "best_appraisal": best["appraisal"],
                    "best_validation": best["validation"],
                    "iterations": iterations,
                    "final_status": "failed_llm_error",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": improvement_trajectory,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }

            # No iterations - re-raise
            raise

    # Should never reach here (loop exits via returns)
    raise RuntimeError("Appraisal loop exited unexpectedly")


def run_report_with_correction(
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm_provider: str,
    file_manager: PipelineFileManager,
    language: str = "nl",
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    compile_pdf: bool = True,
    enable_figures: bool = True,
    renderer: str = "latex",
    progress_callback: Callable[[str, str, dict], None] | None = None,
) -> dict[str, Any]:
    """
    Run report generation with automatic iterative correction until quality is sufficient.

    This function implements the full report workflow with validation/correction loop:
        1. Generate initial report from extraction + appraisal (iteration 0)
        2. Validate report (completeness, accuracy, consistency)
        3. If quality insufficient and iterations < max:
           - Run correction
           - Validate corrected report
           - Repeat until quality OK or max iterations reached
        4. Select best iteration based on quality metrics
        5. Return best report + validation + iteration history

    Args:
        extraction_result: Validated extraction JSON (input for report data)
        appraisal_result: Validated appraisal JSON (input for quality assessments)
        classification_result: Classification result (for metadata + publication_type)
        llm_provider: LLM provider name ("openai" | "claude")
        file_manager: File manager for saving report iterations
        language: Report language ("nl" | "en"), default: "nl"
        max_iterations: Maximum correction attempts after initial report (default: 3)
            Iteration 0: Initial report + validation
            Iterations 1-N: Correction attempts (if quality insufficient)
            Example: max_iterations=3 → up to 4 total iterations (0,1,2,3)
        quality_thresholds: Custom thresholds, defaults to REPORT_QUALITY_THRESHOLDS:
            {
                'completeness_score': 0.85,
                'accuracy_score': 0.95,
                'cross_reference_consistency_score': 0.90,
                'data_consistency_score': 0.90,
                'schema_compliance_score': 0.95,
                'critical_issues': 0
            }
        progress_callback: Optional callback for progress updates

    Returns:
        dict: {
            'best_report': dict,  # Best report result
            'best_validation': dict,  # Validation of best report
            'best_iteration': int,  # Iteration number of best result
            'iterations': list[dict],  # All iteration history with metrics
            'final_status': str,  # "passed" | "max_iterations_reached" | "early_stopped_degradation" | "failed"
            'iteration_count': int,  # Total iterations performed
            'improvement_trajectory': list[float],  # Quality scores per iteration
        }

    Raises:
        SchemaLoadError: If report.schema.json cannot be loaded or is invalid
        LLMProviderError: If LLM provider initialization fails
        LLMError: If LLM calls fail after retries

    Example:
        >>> report_result = run_report_with_correction(
        ...     extraction_result=extraction,
        ...     appraisal_result=appraisal,
        ...     classification_result=classification,
        ...     llm_provider="openai",
        ...     file_manager=file_mgr,
        ...     language="nl",
        ...     max_iterations=3
        ... )
        >>> report_result['final_status']
        'passed'
        >>> report_result['best_report']['metadata']['title']
        'Study Title'
    """
    console.print(
        "\n[bold magenta]═══ REPORT GENERATION WITH ITERATIVE CORRECTION ═══[/bold magenta]\n"
    )

    console.print(f"[blue]Report language: {language}[/blue]")
    console.print(f"[blue]Max iterations: {max_iterations}[/blue]\n")

    # Use default thresholds if not provided
    if quality_thresholds is None:
        quality_thresholds = REPORT_QUALITY_THRESHOLDS

    # Initialize LLM provider
    try:
        llm = get_llm_provider(llm_provider)
    except Exception as e:
        console.print(f"[red]❌ LLM provider error: {e}[/red]")
        raise

    # ============================================================================
    # Dependency Gating: Validate upstream quality before report generation
    # ============================================================================
    console.print("\n[bold]Checking upstream dependencies...[/bold]")

    # Check extraction quality
    extraction_quality = extraction_result.get("quality_score")
    if extraction_quality is None:
        # Try alternative location (validation_summary)
        validation_summary = extraction_result.get("validation_summary", {})
        extraction_quality = validation_summary.get("quality_score")

    if extraction_quality is not None:
        console.print(f"  Extraction quality: {extraction_quality:.2f}")
        if extraction_quality < 0.70:
            error_msg = (
                f"[red]❌ Extraction quality too low ({extraction_quality:.2f} < 0.70). "
                "Cannot generate reliable report. Please improve extraction quality first.[/red]"
            )
            console.print(error_msg)
            return {
                "_pipeline_metadata": {
                    "step": STEP_REPORT_GENERATION,
                    "status": "blocked",
                    "reason": "extraction_quality_low",
                    "extraction_quality": extraction_quality,
                },
                "status": "blocked",
                "message": "Extraction quality insufficient for report generation",
                "extraction_quality": extraction_quality,
                "minimum_required": 0.70,
            }
        elif extraction_quality < 0.90:
            console.print(
                f"  [yellow]⚠️  Warning: Extraction quality is below recommended threshold "
                f"({extraction_quality:.2f} < 0.90). Report accuracy may be limited.[/yellow]"
            )
    else:
        console.print("  [dim]Extraction quality: not available[/dim]")

    # Check appraisal quality and RoB data
    appraisal_status = appraisal_result.get("status", "unknown")
    appraisal_final_status = appraisal_result.get("final_status", appraisal_status)
    risk_of_bias = appraisal_result.get("risk_of_bias")

    blocking_appraisal_statuses = {
        "failed",
        "failed_schema_validation",
        "failed_llm_error",
    }

    # Check validation summary for a failed overall status (best or direct validation)
    validation_summary = appraisal_result.get("validation_summary", {})
    if not validation_summary:
        best_validation = appraisal_result.get("best_validation", {})
        validation_summary = best_validation.get("validation_summary", {})

    validation_overall_status = validation_summary.get("overall_status")
    validation_failed = validation_overall_status == "failed"

    if (
        appraisal_final_status in blocking_appraisal_statuses
        or validation_failed
        or risk_of_bias is None
    ):
        error_msg = (
            "[red]❌ Appraisal failed or missing Risk of Bias data. "
            "Cannot generate report without quality assessment.[/red]"
        )
        console.print(error_msg)
        return {
            "_pipeline_metadata": {
                "step": STEP_REPORT_GENERATION,
                "status": "blocked",
                "reason": "appraisal_failed",
                "appraisal_final_status": appraisal_final_status,
                "appraisal_validation_status": validation_overall_status,
            },
            "status": "blocked",
            "message": "Appraisal data missing or incomplete",
            "appraisal_status": appraisal_status,
            "appraisal_final_status": appraisal_final_status,
            "appraisal_validation_status": validation_overall_status,
            "has_risk_of_bias": risk_of_bias is not None,
        }

    appraisal_quality = appraisal_result.get("quality_score")
    if appraisal_quality is None:
        # Try alternative location (validation_summary from best iteration)
        best_iteration = appraisal_result.get("best_iteration", {})
        validation = best_iteration.get("validation", {})
        validation_summary = validation.get("validation_summary", {})
        appraisal_quality = validation_summary.get("quality_score")

    if appraisal_quality is not None:
        console.print(f"  Appraisal quality: {appraisal_quality:.2f}")
        if appraisal_quality < 0.70:
            console.print(
                f"  [yellow]⚠️  Warning: Appraisal quality is below recommended threshold "
                f"({appraisal_quality:.2f} < 0.70). Report quality assessments may be limited.[/yellow]"
            )
    else:
        console.print("  [dim]Appraisal quality: not available[/dim]")

    console.print("  [green]✓ Dependency checks passed[/green]")

    # Track iterations
    iterations = []
    current_report = None
    current_validation = None
    iteration_num = 0

    # Main iteration loop
    while iteration_num <= max_iterations:
        console.print(f"\n[bold cyan]─── Iteration {iteration_num} ───[/bold cyan]")

        try:
            # Step 1: Generate report (or use corrected from previous iteration)
            if iteration_num == 0:
                # Initial report generation (Phase 2 single-pass)
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
            else:
                # Correction already ran at end of previous iteration
                # current_report already contains corrected version
                pass

            # Step 2: Validate report
            current_validation = _run_report_validation_step(
                report_result=current_report,
                extraction_result=extraction_result,
                appraisal_result=appraisal_result,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
            )

            # Save report + validation iteration via file manager helper
            report_file, validation_file = file_manager.save_report_iteration(
                iteration=iteration_num,
                report_result=current_report,
                validation_result=current_validation,
            )
            console.print(f"[dim]Saved: {report_file.name}[/dim]")
            if validation_file:
                console.print(f"[dim]Saved: {validation_file.name}[/dim]")

            # Extract metrics
            metrics = _extract_report_metrics(current_validation)

            # Store iteration data
            iteration_data = {
                "iteration_num": iteration_num,
                "report": current_report,
                "validation": current_validation,
                "metrics": metrics,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            iterations.append(iteration_data)

            # Display quality scores
            console.print(f"\n[bold]Quality Scores (Iteration {iteration_num}):[/bold]")
            console.print(f"  Completeness:         {metrics['completeness_score']:.2f}")
            console.print(f"  Accuracy:             {metrics['accuracy_score']:.2f}")
            console.print(
                f"  Cross-Ref Consistency: {metrics['cross_reference_consistency_score']:.2f}"
            )
            console.print(f"  Data Consistency:     {metrics['data_consistency_score']:.2f}")
            console.print(f"  Schema Compliance:    {metrics['schema_compliance_score']:.2f}")
            console.print(f"  [bold]Quality Score:        {metrics['quality_score']:.2f}[/bold]")
            console.print(f"  Critical Issues:      {metrics['critical_issues']}")

            # Display improvement trajectory if not first iteration
            if len(iterations) > 1:
                prev_score = iterations[-2]["metrics"]["quality_score"]
                current_score = metrics["quality_score"]
                delta = current_score - prev_score
                if delta > 0:
                    delta_symbol = "↑"
                    delta_color = "green"
                elif delta < 0:
                    delta_symbol = "↓"
                    delta_color = "red"
                else:
                    delta_symbol = "→"
                    delta_color = "yellow"
                console.print(
                    f"  [{delta_color}]Improvement: {delta_symbol} {delta:+.3f} "
                    f"(prev: {prev_score:.2f})[/{delta_color}]"
                )

            # Check if quality is sufficient
            if is_report_quality_sufficient(current_validation, quality_thresholds):
                console.print(
                    f"\n[green]✅ Quality sufficient at iteration {iteration_num}! Stopping.[/green]"
                )

                # Save best files
                best_report_file, best_validation_file = file_manager.save_best_report(
                    current_report, current_validation
                )
                # Render artefact (latex or weasyprint) and always write markdown
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
                    console.print(f"[yellow]⚠️  Failed to render report: {e}[/yellow]")
                    render_dirs = {"error": str(e), "renderer": renderer}
                except Exception as e:
                    console.print(f"[yellow]⚠️  Failed to render report: {e}[/yellow]")
                    render_dirs = {}

                # Always emit markdown as fallback, even if PDF/HTML failed
                try:
                    md_path = render_report_to_markdown(current_report, render_root)
                    render_dirs["markdown"] = md_path
                    # Also store a copy alongside other tmp outputs for easy access
                    root_md = file_manager.tmp_dir / f"{file_manager.identifier}-report.md"
                    root_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
                    render_dirs["markdown_root"] = root_md
                except Exception as e:
                    console.print(f"[yellow]⚠️  Failed to write markdown fallback: {e}[/yellow]")

                console.print(f"[green]Saved best: {best_report_file.name}[/green]")
                console.print(f"[green]Saved best: {best_validation_file.name}[/green]")

                # Summary of saved iterations
                console.print("\n[bold]Saved Report Iterations:[/bold]")
                all_iterations = file_manager.get_report_iterations()
                for it in all_iterations:
                    status_symbol = "✅" if it["validation_exists"] else "⚠️"
                    console.print(
                        f"  {status_symbol} Iteration {it['iteration_num']}: "
                        f"{it['report_file'].name}"
                    )
                best_file = file_manager.get_filename("report", status="best")
                if best_file.exists():
                    console.print(f"  🏆 Best: {best_file.name}")

                improvement_trajectory = [it["metrics"]["quality_score"] for it in iterations]

                return {
                    "best_report": current_report,
                    "best_validation": current_validation,
                    "best_iteration": iteration_num,
                    "iterations": iterations,
                    "final_status": "passed",
                    "iteration_count": iteration_num + 1,
                    "improvement_trajectory": improvement_trajectory,
                    "rendered_paths": render_dirs,
                }

            # Check for quality degradation (early stopping)
            if _detect_quality_degradation(iterations, window=2):
                console.print(
                    "\n[yellow]⚠️  Quality degrading - stopping early and selecting best[/yellow]"
                )

                # Select best iteration
                best = _select_best_report_iteration(iterations)
                best_report = best["report"]
                best_validation = best["validation"]

                # Save best files
                best_report_file, best_validation_file = file_manager.save_best_report(
                    best_report, best_validation
                )

                console.print(
                    f"[yellow]Selected iteration {best['iteration_num']} as best "
                    f"(reason: {best['selection_reason']})[/yellow]"
                )

                # Summary of saved iterations
                console.print("\n[bold]Saved Report Iterations:[/bold]")
                all_iterations = file_manager.get_report_iterations()
                for it in all_iterations:
                    status_symbol = "✅" if it["validation_exists"] else "⚠️"
                    console.print(
                        f"  {status_symbol} Iteration {it['iteration_num']}: "
                        f"{it['report_file'].name}"
                    )
                best_file = file_manager.get_filename("report", status="best")
                if best_file.exists():
                    console.print(f"  🏆 Best: {best_file.name}")

                improvement_trajectory = [it["metrics"]["quality_score"] for it in iterations]

                return {
                    "best_report": best_report,
                    "best_validation": best_validation,
                    "best_iteration": best["iteration_num"],
                    "iterations": iterations,
                    "final_status": "early_stopped_degradation",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": improvement_trajectory,
                }

            # Check if max iterations reached
            if iteration_num >= max_iterations:
                console.print(
                    f"\n[yellow]⚠️  Max iterations ({max_iterations}) reached - selecting best[/yellow]"
                )

                # Select best iteration
                best = _select_best_report_iteration(iterations)
                best_report = best["report"]
                best_validation = best["validation"]

                # Save best files
                best_report_file, best_validation_file = file_manager.save_best_report(
                    best_report, best_validation
                )

                console.print(
                    f"[yellow]Selected iteration {best['iteration_num']} as best "
                    f"(reason: {best['selection_reason']})[/yellow]"
                )

                # Summary of saved iterations
                console.print("\n[bold]Saved Report Iterations:[/bold]")
                all_iterations = file_manager.get_report_iterations()
                for it in all_iterations:
                    status_symbol = "✅" if it["validation_exists"] else "⚠️"
                    console.print(
                        f"  {status_symbol} Iteration {it['iteration_num']}: "
                        f"{it['report_file'].name}"
                    )
                best_file = file_manager.get_filename("report", status="best")
                if best_file.exists():
                    console.print(f"  🏆 Best: {best_file.name}")

                improvement_trajectory = [it["metrics"]["quality_score"] for it in iterations]

                return {
                    "best_report": best_report,
                    "best_validation": best_validation,
                    "best_iteration": best["iteration_num"],
                    "iterations": iterations,
                    "final_status": "max_iterations_reached",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": improvement_trajectory,
                }

            # Quality insufficient and iterations remain - run correction
            console.print(
                f"\n[yellow]Quality insufficient (iteration {iteration_num}). Running correction...[/yellow]"
            )

            # Step 3: Run correction for next iteration
            current_report = _run_report_correction_step(
                report_result=current_report,
                validation_result=current_validation,
                extraction_result=extraction_result,
                appraisal_result=appraisal_result,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
            )

            # Increment iteration for next loop
            iteration_num += 1

        except (PromptLoadError, SchemaLoadError) as e:
            # These are fatal errors - cannot continue
            console.print(f"\n[red]❌ Fatal error: {e}[/red]")

            # If we have any iterations, save best available
            if iterations:
                console.print("[yellow]Saving best iteration from partial results...[/yellow]")
                best = _select_best_report_iteration(iterations)
                file_manager.save_best_report(best["report"], best["validation"])

                improvement_trajectory = [it["metrics"]["quality_score"] for it in iterations]

                return {
                    "best_report": best["report"],
                    "best_validation": best["validation"],
                    "best_iteration": best["iteration_num"],
                    "iterations": iterations,
                    "final_status": "failed",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": improvement_trajectory,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }

            # No iterations - re-raise
            raise

        except LLMError as e:
            # LLM errors - try to continue or use best available
            console.print(f"\n[red]❌ LLM error at iteration {iteration_num}: {e}[/red]")

            # If we have any iterations, save best available
            if iterations:
                console.print("[yellow]Using best iteration from previous attempts...[/yellow]")
                best = _select_best_report_iteration(iterations)
                file_manager.save_best_report(best["report"], best["validation"])

                improvement_trajectory = [it["metrics"]["quality_score"] for it in iterations]

                return {
                    "best_report": best["report"],
                    "best_validation": best["validation"],
                    "best_iteration": best["iteration_num"],
                    "iterations": iterations,
                    "final_status": "failed_llm_error",
                    "iteration_count": len(iterations),
                    "improvement_trajectory": improvement_trajectory,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }

            # No iterations - re-raise
            raise

    # Should never reach here (loop exits via returns)
    raise RuntimeError("Report loop exited unexpectedly")


def run_report_generation(
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    classification_result: dict[str, Any],
    llm_provider: str,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """
    Generate a structured report from extraction and appraisal data (single-pass, Phase 2).

    This function implements the basic report generation workflow:
        1. Load report generation prompt (type-agnostic, handles all study types)
        2. Prepare input data (classification + extraction + appraisal)
        3. Call LLM to generate report JSON
        4. Validate report against report.schema.json
        5. Save report iteration (report0.json)
        6. Return report result

    Note: Phase 2 implementation - single-pass generation only.
          Validation & correction loop will be added in Phase 3.

    Args:
        extraction_result: Validated extraction JSON (best iteration)
        appraisal_result: Validated appraisal JSON (best iteration)
        classification_result: Classification result (for publication_type and metadata)
        llm_provider: LLM provider name ("openai" | "claude")
        file_manager: File manager for saving report iterations
        progress_callback: Optional callback for progress updates
        language: Report language ("en" or "nl"), default "en"

    Returns:
        dict: {
            'report': dict,  # Generated report JSON
            'iteration': int,  # Always 0 in Phase 2
            'status': str,  # "completed"
            '_pipeline_metadata': dict,  # Pipeline tracking metadata
        }

    Raises:
        ValueError: If classification_result missing publication_type
        PromptLoadError: If report generation prompt cannot be loaded
        SchemaLoadError: If report.schema.json cannot be loaded or is invalid
        LLMError: If LLM call fails after retries

    Example:
        >>> report_result = run_report_generation(
        ...     extraction_result=extraction,
        ...     appraisal_result=appraisal,
        ...     classification_result=classification,
        ...     llm_provider="openai",
        ...     file_manager=file_mgr,
        ... )
        >>> report_result['report']['report_version']
        'v1.0'
        >>> report_result['status']
        'completed'
    """
    console.print("\n[bold cyan]═══ REPORT GENERATION (Phase 2 - Single Pass) ═══[/bold cyan]\n")

    # Extract publication type
    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")
    if not publication_type:
        raise ValueError("Classification result missing publication_type")

    # Progress update: started
    if progress_callback:
        progress_callback(
            STEP_REPORT_GENERATION,
            "started",
            {"publication_type": publication_type, "iteration": 0},
        )

    # Load report generation prompt
    console.print("[yellow]📄 Loading report generation prompt...[/yellow]")
    try:
        report_prompt = load_report_generation_prompt()
    except PromptLoadError as e:
        console.print(f"[red]❌ Failed to load report generation prompt: {e}[/red]")
        raise

    # Load report schema for validation
    console.print("[yellow]📋 Loading report schema...[/yellow]")
    try:
        report_schema = load_schema("report")
    except SchemaLoadError as e:
        console.print(f"[red]❌ Failed to load report schema: {e}[/red]")
        raise

    # Prepare input data for LLM
    # Strip metadata to send only clean data to LLM
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)
    appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)

    # Prepare additional inputs required by prompt (Issue #3 fix)
    generation_timestamp = datetime.now(timezone.utc).isoformat()
    pipeline_version = _get_pipeline_version()
    report_schema_str = json.dumps(report_schema, indent=2)

    # Build prompt context with all required inputs (matches Report-generation.txt:6-12)
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

    # Get LLM provider
    llm = get_llm_provider(llm_provider)

    # Call LLM to generate report (Issue #1 fix: use generate_json_with_schema)
    console.print(f"[yellow]🤖 Generating report via {llm_provider}...[/yellow]")
    console.print(f"[dim]Publication type: {publication_type}, Language: {language}[/dim]")

    try:
        report_json = llm.generate_json_with_schema(
            schema=report_schema,
            system_prompt=report_prompt,
            prompt=prompt_context,
            schema_name="report_generation",
        )
    except LLMError as e:
        console.print(f"[red]❌ LLM call failed: {e}[/red]")
        if progress_callback:
            progress_callback(STEP_REPORT_GENERATION, "failed", {"error": str(e)})
        raise

    # Validate report against schema (Issue #2 fix: use validate_with_schema)
    console.print("[yellow]✓ Validating report against schema...[/yellow]")
    from ..validation import validate_with_schema

    # Strip metadata before validation (LLM adds _metadata and usage fields)
    report_clean = _strip_metadata_for_pipeline(report_json)
    is_valid, validation_errors = validate_with_schema(report_clean, report_schema, strict=True)
    if not is_valid:
        error_msg = "\n".join(validation_errors)
        console.print(f"[red]❌ Report schema validation failed:\n{error_msg}[/red]")
        if progress_callback:
            progress_callback(
                STEP_REPORT_GENERATION, "failed", {"error": f"Schema validation: {error_msg}"}
            )
        raise SchemaLoadError(f"Report schema validation failed:\n{error_msg}")

    console.print("[green]✓ Report schema validation passed[/green]")

    # Save report iteration 0
    console.print("[yellow]💾 Saving report iteration 0...[/yellow]")
    report_path, _ = file_manager.save_report_iteration(
        iteration=0, report_result=report_json, validation_result=None
    )
    console.print(f"[green]✓ Report saved: {report_path.name}[/green]")

    # Add pipeline metadata
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

    # Progress update: completed
    if progress_callback:
        progress_callback(
            STEP_REPORT_GENERATION,
            "completed",
            {"iteration": 0, "file": report_path.name},
        )

    console.print("\n[bold green]✓ Report generation completed successfully[/bold green]\n")

    return result


def _run_report_validation_step(
    report_result: dict[str, Any],
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """
    Run report validation step of the pipeline.

    Validates report results for completeness, accuracy, cross-reference consistency,
    data consistency, and schema compliance using the Report-validation.txt prompt.

    Args:
        report_result: Report result to validate
        extraction_result: Original extraction (for data cross-checking)
        appraisal_result: Original appraisal (for quality assessment cross-checking)
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates

    Returns:
        Dictionary containing validation results with validation_summary and quality scores

    Raises:
        PromptLoadError: If validation prompt cannot be loaded
        SchemaLoadError: If validation schema cannot be loaded
        LLMError: If LLM API call fails
    """
    console.print("[bold cyan]🔍 Report Validation[/bold cyan]")

    start_time = time.time()
    _call_progress_callback(progress_callback, "report_validation", "starting", {})

    # Strip metadata from dependencies before using
    report_clean = _strip_metadata_for_pipeline(report_result)
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)
    appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)

    try:
        # Load report validation prompt and schema
        validation_prompt = load_report_validation_prompt()
        validation_schema = load_schema("report_validation")

        # Prepare context with report, extraction, and appraisal
        context = f"""REPORT_JSON:
{json.dumps(report_clean, indent=2)}

EXTRACTION_JSON (for data accuracy checking):
{json.dumps(extraction_clean, indent=2)}

APPRAISAL_JSON (for quality assessment cross-checking):
{json.dumps(appraisal_clean, indent=2)}"""

        console.print("[dim]Validating report for completeness, accuracy, consistency...[/dim]")

        # Run validation (returns validation report with scores)
        validation_result = llm.generate_json_with_schema(
            schema=validation_schema,
            system_prompt=validation_prompt,
            prompt=context,
            schema_name="report_validation",
        )

        console.print("[green]✅ Report validation completed[/green]")

        # Add pipeline metadata
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
                "quality_score": validation_result.get("validation_summary", {}).get(
                    "quality_score"
                ),
            },
        )

        return validation_result

    except (PromptLoadError, SchemaLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Report validation error: {e}[/red]")

        _call_progress_callback(
            progress_callback,
            "report_validation",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


def _run_report_correction_step(
    report_result: dict[str, Any],
    validation_result: dict[str, Any],
    extraction_result: dict[str, Any],
    appraisal_result: dict[str, Any],
    llm: Any,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None,
) -> dict[str, Any]:
    """
    Run report correction step of the pipeline.

    Applies LLM-based corrections to report results based on validation
    feedback (fixes data mismatches, completes missing sections, fixes broken references,
    resolves schema violations).

    Args:
        report_result: Original report result to correct
        validation_result: Validation result containing issues to fix
        extraction_result: Original extraction (for re-checking data)
        appraisal_result: Original appraisal (for re-checking quality assessments)
        llm: LLM provider instance (from get_llm_provider)
        file_manager: PipelineFileManager for saving results
        progress_callback: Optional callback for progress updates

    Returns:
        Corrected report result (ready for re-validation)

    Raises:
        PromptLoadError: If correction prompt cannot be loaded
        SchemaLoadError: If report schema cannot be loaded
        LLMError: If LLM API call fails
    """
    console.print("[bold cyan]🔧 Report Correction[/bold cyan]")

    start_time = time.time()
    validation_status = validation_result.get("validation_summary", {}).get("overall_status")

    _call_progress_callback(
        progress_callback,
        "report_correction",
        "starting",
        {"validation_status": validation_status},
    )

    # Strip metadata from dependencies
    report_clean = _strip_metadata_for_pipeline(report_result)
    validation_clean = _strip_metadata_for_pipeline(validation_result)
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)
    appraisal_clean = _strip_metadata_for_pipeline(appraisal_result)

    try:
        # Load correction prompt and schema
        correction_prompt = load_report_correction_prompt()
        report_schema = load_schema("report")

        # Prepare context with validation report, original report, extraction, appraisal, and schema
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

        # Run correction
        corrected_report = llm.generate_json_with_schema(
            schema=report_schema,
            system_prompt=correction_prompt,
            prompt=context,
            schema_name="report_correction",
        )

        console.print("[green]✅ Report correction completed[/green]")

        # Add pipeline metadata
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
            {
                "result": corrected_report,
                "elapsed_seconds": elapsed,
            },
        )

        return corrected_report

    except (PromptLoadError, SchemaLoadError, LLMError) as e:
        elapsed = time.time() - start_time
        console.print(f"[red]❌ Report correction error: {e}[/red]")

        _call_progress_callback(
            progress_callback,
            "report_correction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


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
    report_language: str | None = None,
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
        report_language: Language to use for report generation ("en" or "nl")

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
                language=report_language or "nl",
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

    else:
        # Should never reach here due to validation above
        raise ValueError(f"Unknown step: {step_name}")


def run_four_step_pipeline(
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
    Four-step extraction-and-appraisal pipeline with optional step filtering.

    Coordinates the full pipeline from PDF to validated evidence outputs:
    1. Classification - Identify publication type + extract metadata
    2. Extraction - Detailed data extraction based on classified type
    3. Validation & Correction - Iterative quality control with automatic fixes
    4. Appraisal - Critical appraisal (RoB, GRADE, applicability)
    5. Report Generation - Compose structured report JSON (optional)

    Args:
        pdf_path: Path to PDF file to process
        max_pages: Maximum pages to process (None = all pages, max 100)
        llm_provider: LLM provider to use ("openai" or "claude")
        breakpoint_after_step: Step name to pause after (for testing)
        have_llm_support: Whether LLM modules are available
        steps_to_run: Optional list of steps to execute.
            None = run all steps (default).
            Dependencies are validated automatically.
        report_language: Language for report generation ("en" or "nl")
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
        >>> # Basic usage (backwards compatible)
        >>> results = run_four_step_pipeline(
        ...     pdf_path=Path("paper.pdf"),
        ...     max_pages=20,
        ...     llm_provider="openai"
        ... )
        >>> results["classification"]["publication_type"]
        'interventional_trial'
        >>>
        >>> # With step filtering
        >>> results = run_four_step_pipeline(
        ...     pdf_path=Path("paper.pdf"),
        ...     steps_to_run=["classification", "extraction"]
        ... )
        >>>
        >>> # With progress callback
        >>> def my_callback(step, status, data):
        ...     print(f"{step}: {status}")
        >>> results = run_four_step_pipeline(
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
