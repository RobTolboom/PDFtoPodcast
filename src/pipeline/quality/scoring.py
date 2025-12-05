"""
Quality scoring utilities for iteration ranking and comparison.

This module provides unified scoring functions that replace the duplicate
safe_score() and quality_rank() implementations in orchestrator.py.
"""

from dataclasses import dataclass
from typing import Literal

from .metrics import MetricType, QualityMetrics


@dataclass(frozen=True)
class QualityWeights:
    """
    Configurable weights for quality score calculation.

    Each weight represents the contribution of that metric to the overall
    quality score. Weights should sum to 1.0 for consistent scoring.
    """

    # Common weights
    completeness: float = 0.0
    accuracy: float = 0.0
    schema_compliance: float = 0.0

    # Appraisal-specific
    logical_consistency: float = 0.0
    evidence_support: float = 0.0

    # Report-specific
    cross_reference_consistency: float = 0.0
    data_consistency: float = 0.0


# Predefined weight configurations for each metric type
EXTRACTION_WEIGHTS = QualityWeights(
    completeness=0.40,
    accuracy=0.40,
    schema_compliance=0.20,
)

APPRAISAL_WEIGHTS = QualityWeights(
    logical_consistency=0.35,
    completeness=0.25,
    evidence_support=0.25,
    schema_compliance=0.15,
)

REPORT_WEIGHTS = QualityWeights(
    accuracy=0.35,
    completeness=0.30,
    cross_reference_consistency=0.10,
    data_consistency=0.10,
    schema_compliance=0.15,
)


def safe_score(summary: dict, key: str, default: float = 0.0) -> float:
    """
    Safely extract numeric score from dict, handling None and invalid types.

    This replaces the multiple inline safe_score() definitions in orchestrator.py.

    Args:
        summary: Dict containing validation summary data
        key: Key to look up in the dict
        default: Default value if key is missing or value is invalid

    Returns:
        float: The score value, or default if not found/invalid

    Example:
        >>> summary = {'completeness_score': 0.95, 'accuracy_score': None}
        >>> safe_score(summary, 'completeness_score')
        0.95
        >>> safe_score(summary, 'accuracy_score')
        0.0
        >>> safe_score(summary, 'missing_key', 0.5)
        0.5
    """
    val = summary.get(key, default)
    return val if isinstance(val, int | float) else default


def get_weights_for_type(metric_type: MetricType) -> QualityWeights:
    """Get predefined weights for a metric type."""
    weights_map = {
        MetricType.EXTRACTION: EXTRACTION_WEIGHTS,
        MetricType.APPRAISAL: APPRAISAL_WEIGHTS,
        MetricType.REPORT: REPORT_WEIGHTS,
    }
    return weights_map.get(metric_type, EXTRACTION_WEIGHTS)


def calculate_quality_score(
    metrics: QualityMetrics, weights: QualityWeights | None = None
) -> float:
    """
    Calculate weighted quality score from metrics.

    If weights is None, uses predefined weights based on metric_type.

    Args:
        metrics: QualityMetrics instance with scores
        weights: Optional custom weights (uses defaults if None)

    Returns:
        float: Weighted composite quality score (0.0-1.0)
    """
    if weights is None:
        weights = get_weights_for_type(metrics.metric_type)

    score = 0.0

    # Common weights
    score += metrics.completeness_score * weights.completeness
    score += metrics.accuracy_score * weights.accuracy
    score += metrics.schema_compliance_score * weights.schema_compliance

    # Appraisal-specific
    score += metrics.logical_consistency_score * weights.logical_consistency
    score += metrics.evidence_support_score * weights.evidence_support

    # Report-specific
    score += metrics.cross_reference_consistency_score * weights.cross_reference_consistency
    score += metrics.data_consistency_score * weights.data_consistency

    return score


TiebreakerField = Literal["completeness", "accuracy"]


def quality_rank(
    iteration: dict,
    metric_type: MetricType,
    tiebreaker: TiebreakerField = "completeness",
) -> tuple:
    """
    Create sortable quality tuple for iteration ranking.

    This replaces the three inline quality_rank() definitions in orchestrator.py
    (_select_best_iteration, _select_best_appraisal_iteration, _select_best_report_iteration).

    Priority order:
        1. No critical issues (bool, True > False)
        2. Quality score (float, higher > lower)
        3. Tiebreaker score (float, higher > lower)
        4. Earlier iteration preferred (negative iteration_num)

    Args:
        iteration: Iteration data dict with 'metrics' and 'iteration_num'
        metric_type: Type of metrics for weight selection
        tiebreaker: Which field to use as tiebreaker ("completeness" or "accuracy")

    Returns:
        tuple: Sortable tuple (critical_ok, quality_score, tiebreaker_score, neg_iteration)

    Example:
        >>> iterations = [
        ...     {'iteration_num': 0, 'metrics': {'quality_score': 0.85, 'critical_issues': 0}},
        ...     {'iteration_num': 1, 'metrics': {'quality_score': 0.92, 'critical_issues': 0}},
        ... ]
        >>> sorted(iterations, key=lambda x: quality_rank(x, MetricType.EXTRACTION), reverse=True)
        # Returns iteration 1 first (higher quality_score)
    """
    metrics = iteration.get("metrics", {})

    # Handle both dict metrics and QualityMetrics dataclass
    if isinstance(metrics, QualityMetrics):
        critical_issues = metrics.critical_issues
        quality_score = metrics.quality_score
        tiebreaker_score = (
            metrics.completeness_score if tiebreaker == "completeness" else metrics.accuracy_score
        )
    else:
        critical_issues = metrics.get("critical_issues", 999)
        quality_score = metrics.get("quality_score", 0)

        # For extraction, compute quality_score if not present
        if metric_type == MetricType.EXTRACTION and quality_score == 0:
            quality_score = (
                metrics.get("completeness_score", 0) * 0.40
                + metrics.get("accuracy_score", 0) * 0.40
                + metrics.get("schema_compliance_score", 0) * 0.20
            )
            # Also check for 'overall_quality' key (legacy)
            quality_score = metrics.get("overall_quality", quality_score)

        tiebreaker_score = metrics.get(f"{tiebreaker}_score", 0)

    iteration_num = iteration.get("iteration_num", 0)

    return (
        critical_issues == 0,  # Priority 1: No critical issues
        quality_score,  # Priority 2: Quality score
        tiebreaker_score,  # Priority 3: Tiebreaker
        -iteration_num,  # Priority 4: Prefer earlier iterations
    )


def select_best_iteration(
    iterations: list[dict],
    metric_type: MetricType,
    tiebreaker: TiebreakerField = "completeness",
) -> dict:
    """
    Select best iteration from list based on quality ranking.

    This replaces the three separate _select_best_*_iteration() functions
    in orchestrator.py.

    Args:
        iterations: List of iteration data dicts
        metric_type: Type of metrics for weight selection
        tiebreaker: Which field to use as tiebreaker

    Returns:
        dict: Best iteration with added 'selection_reason' key

    Raises:
        ValueError: If iterations list is empty

    Example:
        >>> iterations = [
        ...     {'iteration_num': 0, 'metrics': {...}, 'result': {...}},
        ...     {'iteration_num': 1, 'metrics': {...}, 'result': {...}},
        ... ]
        >>> best = select_best_iteration(iterations, MetricType.EXTRACTION)
        >>> best['selection_reason']
        'final_iteration_best'
    """
    if not iterations:
        raise ValueError("No iterations to select from")

    # Single iteration case
    if len(iterations) == 1:
        return {**iterations[0], "selection_reason": "only_iteration"}

    # Determine tiebreaker based on metric type (reports prefer accuracy)
    if metric_type == MetricType.REPORT:
        tiebreaker = "accuracy"

    # Sort by quality rank (best first)
    sorted_iterations = sorted(
        iterations, key=lambda x: quality_rank(x, metric_type, tiebreaker), reverse=True
    )

    best = sorted_iterations[0]
    last = iterations[-1]

    # Determine selection reason
    if best["iteration_num"] == last["iteration_num"]:
        reason = "final_iteration_best"
    else:
        reason = f"quality_peaked_at_iteration_{best['iteration_num']}"

    return {**best, "selection_reason": reason}
