# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Four-step PDF extraction pipeline orchestration.

This module contains the main pipeline orchestration logic that coordinates
the four extraction steps: Classification → Extraction → Validation → Correction.

Pipeline Steps:
    1. Classification - Identify publication type and extract metadata
    2. Extraction - Schema-based structured data extraction
    3. Validation - Dual validation (schema + conditional LLM semantic)
    4. Correction - Fix issues identified during validation

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
)
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

# Default pipeline steps (validation_correction replaces separate validation+correction)
ALL_PIPELINE_STEPS = [
    STEP_CLASSIFICATION,
    STEP_EXTRACTION,
    STEP_VALIDATION_CORRECTION,
    STEP_APPRAISAL,  # Critical appraisal after extraction validation
]
# Note: STEP_VALIDATION and STEP_CORRECTION remain available for CLI backward compatibility

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

    Returns:
        Dictionary containing extracted structured data

    Raises:
        SchemaLoadError: If schema file cannot be loaded
        PromptLoadError: If prompt file cannot be loaded
        LLMError: If LLM API call fails
    """
    console.print("[bold cyan]📊 Stap 2: Data Extractie (Schema-based)[/bold cyan]")

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

        console.print(f"[dim]Running schema-based {publication_type} extraction with PDF upload...")
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

        # Save extraction result (iteration 0)
        extraction_file = file_manager.save_json(
            extraction_result, "extraction", iteration_number=0
        )
        console.print(f"[green]✅ Extractie opgeslagen: {extraction_file}[/green]")

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
        console.print(f"[red]❌ Extractie fout: {e}[/red]")

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
        except Exception:
            pass  # Don't fail the error handling

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
    console.print("[bold cyan]🔍 Stap 3: Validatie (Schema + LLM)[/bold cyan]")

    start_time = time.time()
    _call_progress_callback(progress_callback, STEP_VALIDATION, "starting", {})

    # Strip metadata from dependencies before using
    extraction_clean = _strip_metadata_for_pipeline(extraction_result)
    classification_clean = _strip_metadata_for_pipeline(classification_result)
    publication_type = classification_clean.get("publication_type")

    # Run dual validation (schema + conditional LLM) with clean data
    validation_result = run_dual_validation(
        extraction_result=extraction_clean,
        pdf_path=pdf_path,
        max_pages=max_pages,
        publication_type=publication_type,
        llm=llm,
        console=console,
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
    console.print(f"[green]✅ Validatie opgeslagen: {validation_file}[/green]")

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

    Returns:
        Tuple of (corrected_extraction, final_validation)

    Raises:
        PromptLoadError: If correction prompt cannot be loaded
        SchemaLoadError: If extraction schema cannot be loaded
        LLMError: If LLM API call fails
    """
    console.print("[bold cyan]🔧 Stap 4: Correctie[/bold cyan]")

    start_time = time.time()
    validation_status = validation_result.get("verification_summary", {}).get("overall_status")

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
        console.print(f"[red]❌ Correctie fout: {e}[/red]")

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
        except Exception:
            pass  # Don't fail the error handling

        _call_progress_callback(
            progress_callback,
            "correction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


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

    # Get LLM instance
    llm = get_llm_provider(llm_provider)

    while iteration_num <= max_iterations:
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
            iteration_data = {
                "iteration_num": iteration_num,
                "extraction": current_extraction,
                "validation": validation_result,
                "metrics": _extract_metrics(validation_result),
                "timestamp": datetime.now().isoformat(),
            }
            iterations.append(iteration_data)

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
    console.print("[bold cyan]📋 Stap 1: Classificatie[/bold cyan]")

    if not have_llm_support:
        console.print("[red]❌ LLM support niet beschikbaar[/red]")
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

        # Save classification result
        classification_file = file_manager.save_json(classification_result, "classification")
        console.print(f"[green]✅ Classificatie opgeslagen: {classification_file}[/green]")

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
        console.print(f"[red]❌ Classificatie fout: {e}[/red]")

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
            user_prompt=f"EXTRACTION_JSON:\n{json.dumps(extraction_clean, indent=2)}",
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
        console.print(f"[red]❌ Appraisal fout: {e}[/red]")

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
            user_prompt=context,
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
        console.print(f"[red]❌ Appraisal validation fout: {e}[/red]")

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
            user_prompt=context,
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
        console.print(f"[red]❌ Appraisal correction fout: {e}[/red]")

        _call_progress_callback(
            progress_callback,
            "appraisal_correction",
            "failed",
            {"error": str(e), "error_type": type(e).__name__, "elapsed_seconds": elapsed},
        )
        raise


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

            # Save appraisal iteration
            appraisal_file = file_manager.save_json(
                current_appraisal,
                STEP_APPRAISAL,
                iteration_number=iteration_num,
            )
            console.print(f"[dim]Saved: {appraisal_file.name}[/dim]")

            # Step 2: Validate appraisal
            current_validation = _run_appraisal_validation_step(
                appraisal_result=current_appraisal,
                extraction_result=extraction_result,
                llm=llm,
                file_manager=file_manager,
                progress_callback=progress_callback,
            )

            # Save validation iteration
            validation_file = file_manager.save_json(
                current_validation,
                STEP_APPRAISAL_VALIDATION,
                iteration_number=iteration_num,
            )
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


def run_single_step(
    step_name: str,
    pdf_path: Path,
    max_pages: int | None,
    llm_provider: str,
    file_manager: PipelineFileManager,
    progress_callback: Callable[[str, str, dict], None] | None = None,
    previous_results: dict[str, Any] | None = None,
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
            - "validation": Legacy - Single validation run (backward compat)
            - "correction": Legacy - Single correction run (backward compat)
        pdf_path: Path to PDF file to process
        max_pages: Maximum pages to process (None = all pages)
        llm_provider: LLM provider name ("openai" or "claude")
        file_manager: File manager for saving step results
        progress_callback: Optional callback for progress updates (step_name, status, data)
        previous_results: Results from previous steps (required for dependent steps)

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

        # For other steps: load normally
        else:
            result = file_manager.load_json(dep_step)

        if result is None:
            raise ValueError(
                f"{dep_step.title()} step result not found. "
                f"Please run {dep_step} step first or ensure "
                f"tmp/{file_manager.identifier}-{dep_step}.json exists."
            )

        if dep_step not in ["extraction", "validation"]:
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
        # New iterative validation-correction step requires same dependencies as STEP_EXTRACTION
        classification_result = _get_or_load_result("classification")
        extraction_result = _get_or_load_result("extraction")
        previous_results[STEP_CLASSIFICATION] = classification_result
        previous_results[STEP_EXTRACTION] = extraction_result

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
        # New iterative validation-correction workflow
        classification_result = previous_results[STEP_CLASSIFICATION]
        extraction_result = previous_results[STEP_EXTRACTION]

        # Call the iterative loop with default or custom parameters
        return run_validation_with_correction(
            pdf_path=pdf_path,
            extraction_result=extraction_result,
            classification_result=classification_result,
            llm_provider=llm_provider,
            file_manager=file_manager,
            max_iterations=3,  # Could be parameterized in future
            quality_thresholds=None,  # Uses DEFAULT_QUALITY_THRESHOLDS
            progress_callback=progress_callback,
        )

    elif step_name == STEP_APPRAISAL:
        # Critical appraisal with iterative validation-correction
        classification_result = previous_results[STEP_CLASSIFICATION]
        extraction_result = previous_results[STEP_EXTRACTION]

        # Call the appraisal iterative loop
        return run_appraisal_with_correction(
            extraction_result=extraction_result,
            classification_result=classification_result,
            llm_provider=llm_provider,
            file_manager=file_manager,
            max_iterations=3,  # Could be parameterized in future
            quality_thresholds=None,  # Uses APPRAISAL_QUALITY_THRESHOLDS
            progress_callback=progress_callback,
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
    progress_callback: Callable[[str, str, dict], None] | None = None,
) -> dict[str, Any]:
    """
    Four-step extraction pipeline with optional step filtering and progress callbacks.

    Coordinates the full extraction pipeline from PDF to validated structured data:
    1. Classification - Identify publication type + extract metadata
    2. Extraction - Detailed data extraction based on classified type
    3. Validation - Quality control with dual validation strategy
    4. Correction - Fix issues if validation indicates problems

    Args:
        pdf_path: Path to PDF file to process
        max_pages: Maximum pages to process (None = all pages, max 100)
        llm_provider: LLM provider to use ("openai" or "claude")
        breakpoint_after_step: Step name to pause after (for testing)
        have_llm_support: Whether LLM modules are available
        steps_to_run: Optional list of steps to execute. Valid steps:
            ["classification", "extraction", "validation", "correction"]
            None = run all steps (default, backwards compatible)
            Dependencies are validated automatically.
        progress_callback: Optional callback for progress updates.
            Signature: callback(step_name: str, status: str, data: dict)
            - step_name: "classification" | "extraction" | "validation" | "correction"
            - status: "starting" | "completed" | "failed" | "skipped"
            - data: dict with step-specific info (results, errors, timing, file_path)

    Returns:
        Dictionary with results from each completed step:
        {
            "classification": {...},
            "extraction": {...},
            "validation": {...},
            "extraction_corrected": {...},  # Only if correction ran
            "validation_corrected": {...}   # Only if correction ran
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
            return results

        # Check for publication_type == "overig" after classification
        if step_name == STEP_CLASSIFICATION:
            if step_result.get("publication_type") == "overig":
                console.print(
                    "[yellow]⚠️ Publicatietype 'overig' - "
                    "geen gespecialiseerde extractie beschikbaar[/yellow]"
                )
                return results

    return results
