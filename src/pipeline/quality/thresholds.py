"""
Quality threshold definitions and checking functions.

This module provides unified threshold checking for all pipeline stages,
replacing the duplicate is_quality_sufficient(), is_appraisal_quality_sufficient(),
and is_report_quality_sufficient() functions in orchestrator.py.
"""

from dataclasses import dataclass

from .metrics import MetricType, QualityMetrics
from .scoring import safe_score


@dataclass(frozen=True)
class QualityThresholds:
    """
    Quality threshold configuration for a pipeline stage.

    All thresholds are minimum values (except critical_issues which is maximum).
    Validation passes only if ALL thresholds are met.
    """

    # Common thresholds
    completeness_score: float = 0.0
    schema_compliance_score: float = 0.0
    critical_issues: int = 0

    # Extraction-specific
    accuracy_score: float = 0.0

    # Appraisal-specific
    logical_consistency_score: float = 0.0
    evidence_support_score: float = 0.0

    # Report-specific
    cross_reference_consistency_score: float = 0.0
    data_consistency_score: float = 0.0


# Default thresholds for extraction validation
EXTRACTION_THRESHOLDS = QualityThresholds(
    completeness_score=0.90,  # >=90% of PDF data extracted
    accuracy_score=0.95,  # >=95% correct data (max 5% errors)
    schema_compliance_score=0.95,  # >=95% schema compliant
    critical_issues=0,  # Absolutely no critical errors
)

# Default thresholds for appraisal validation
APPRAISAL_THRESHOLDS = QualityThresholds(
    logical_consistency_score=0.90,  # >=90% logical consistency
    completeness_score=0.85,  # >=85% completeness (all domains, outcomes)
    evidence_support_score=0.90,  # >=90% evidence support
    schema_compliance_score=0.95,  # >=95% schema compliance
    critical_issues=0,  # Absolutely no critical errors
)

# Default thresholds for report validation
REPORT_THRESHOLDS = QualityThresholds(
    completeness_score=0.85,  # >=85% completeness (all core sections present)
    accuracy_score=0.95,  # >=95% accuracy (data correctness paramount)
    cross_reference_consistency_score=0.90,  # >=90% cross-ref consistency
    data_consistency_score=0.90,  # >=90% data consistency
    schema_compliance_score=0.95,  # >=95% schema compliance
    critical_issues=0,  # Absolutely no critical errors
)


def get_thresholds_for_type(metric_type: MetricType) -> QualityThresholds:
    """Get default thresholds for a metric type."""
    thresholds_map = {
        MetricType.EXTRACTION: EXTRACTION_THRESHOLDS,
        MetricType.APPRAISAL: APPRAISAL_THRESHOLDS,
        MetricType.REPORT: REPORT_THRESHOLDS,
    }
    return thresholds_map.get(metric_type, EXTRACTION_THRESHOLDS)


def _check_extraction_thresholds(summary: dict, thresholds: QualityThresholds) -> bool:
    """Check extraction-specific thresholds."""
    return (
        safe_score(summary, "completeness_score") >= thresholds.completeness_score
        and safe_score(summary, "accuracy_score") >= thresholds.accuracy_score
        and safe_score(summary, "schema_compliance_score") >= thresholds.schema_compliance_score
        and safe_score(summary, "critical_issues", 999) <= thresholds.critical_issues
    )


def _check_appraisal_thresholds(summary: dict, thresholds: QualityThresholds) -> bool:
    """Check appraisal-specific thresholds."""
    return (
        safe_score(summary, "logical_consistency_score") >= thresholds.logical_consistency_score
        and safe_score(summary, "completeness_score") >= thresholds.completeness_score
        and safe_score(summary, "evidence_support_score") >= thresholds.evidence_support_score
        and safe_score(summary, "schema_compliance_score") >= thresholds.schema_compliance_score
        and safe_score(summary, "critical_issues", 999) <= thresholds.critical_issues
    )


def _check_report_thresholds(summary: dict, thresholds: QualityThresholds) -> bool:
    """Check report-specific thresholds."""
    return (
        safe_score(summary, "completeness_score") >= thresholds.completeness_score
        and safe_score(summary, "accuracy_score") >= thresholds.accuracy_score
        and safe_score(summary, "cross_reference_consistency_score")
        >= thresholds.cross_reference_consistency_score
        and safe_score(summary, "data_consistency_score") >= thresholds.data_consistency_score
        and safe_score(summary, "schema_compliance_score") >= thresholds.schema_compliance_score
        and safe_score(summary, "critical_issues", 999) <= thresholds.critical_issues
    )


def is_quality_sufficient(
    validation_result: dict | None,
    metric_type: MetricType,
    thresholds: QualityThresholds | None = None,
) -> bool:
    """
    Check if validation quality meets thresholds for stopping iteration.

    This unified function replaces the three separate is_*_quality_sufficient()
    functions in orchestrator.py.

    Args:
        validation_result: Validation JSON (can be None)
        metric_type: Type of validation (EXTRACTION, APPRAISAL, REPORT)
        thresholds: Custom thresholds (uses defaults if None)

    Returns:
        bool: True if ALL thresholds are met, False otherwise

    Edge Cases:
        - validation_result is None -> False
        - summary missing -> False
        - Any score is None -> treated as 0 (fails threshold)
        - Empty dict -> False (all scores default to 0)

    Example:
        >>> validation = {
        ...     'verification_summary': {
        ...         'completeness_score': 0.92,
        ...         'accuracy_score': 0.98,
        ...         'schema_compliance_score': 0.97,
        ...         'critical_issues': 0
        ...     }
        ... }
        >>> is_quality_sufficient(validation, MetricType.EXTRACTION)
        True
        >>> is_quality_sufficient(None, MetricType.EXTRACTION)
        False
    """
    # Use default thresholds if not provided
    if thresholds is None:
        thresholds = get_thresholds_for_type(metric_type)

    # Handle None validation_result
    if validation_result is None:
        return False

    # Get summary based on metric type
    # Extraction uses 'verification_summary', others use 'validation_summary'
    if metric_type == MetricType.EXTRACTION:
        summary = validation_result.get("verification_summary", {})
    else:
        summary = validation_result.get("validation_summary", {})

    # Handle missing or empty summary
    if not summary:
        return False

    # Check thresholds based on type
    checkers = {
        MetricType.EXTRACTION: _check_extraction_thresholds,
        MetricType.APPRAISAL: _check_appraisal_thresholds,
        MetricType.REPORT: _check_report_thresholds,
    }

    checker = checkers.get(metric_type)
    if checker is None:
        return False

    return checker(summary, thresholds)


def is_quality_sufficient_from_metrics(
    metrics: QualityMetrics,
    thresholds: QualityThresholds | None = None,
) -> bool:
    """
    Check if QualityMetrics instance meets thresholds.

    Alternative to is_quality_sufficient() when you already have extracted metrics.

    Args:
        metrics: QualityMetrics instance
        thresholds: Custom thresholds (uses defaults based on metrics.metric_type if None)

    Returns:
        bool: True if ALL thresholds are met
    """
    if thresholds is None:
        thresholds = get_thresholds_for_type(metrics.metric_type)

    # Check common thresholds
    if metrics.critical_issues > thresholds.critical_issues:
        return False
    if metrics.schema_compliance_score < thresholds.schema_compliance_score:
        return False
    if metrics.completeness_score < thresholds.completeness_score:
        return False

    # Check type-specific thresholds
    if metrics.metric_type == MetricType.EXTRACTION:
        return metrics.accuracy_score >= thresholds.accuracy_score

    elif metrics.metric_type == MetricType.APPRAISAL:
        return (
            metrics.logical_consistency_score >= thresholds.logical_consistency_score
            and metrics.evidence_support_score >= thresholds.evidence_support_score
        )

    elif metrics.metric_type == MetricType.REPORT:
        return (
            metrics.accuracy_score >= thresholds.accuracy_score
            and metrics.cross_reference_consistency_score
            >= thresholds.cross_reference_consistency_score
            and metrics.data_consistency_score >= thresholds.data_consistency_score
        )

    return False


def thresholds_to_dict(thresholds: QualityThresholds, metric_type: MetricType) -> dict:
    """
    Convert QualityThresholds to dict for backward compatibility.

    Returns only the relevant thresholds for the given metric type.
    """
    if metric_type == MetricType.EXTRACTION:
        return {
            "completeness_score": thresholds.completeness_score,
            "accuracy_score": thresholds.accuracy_score,
            "schema_compliance_score": thresholds.schema_compliance_score,
            "critical_issues": thresholds.critical_issues,
        }
    elif metric_type == MetricType.APPRAISAL:
        return {
            "logical_consistency_score": thresholds.logical_consistency_score,
            "completeness_score": thresholds.completeness_score,
            "evidence_support_score": thresholds.evidence_support_score,
            "schema_compliance_score": thresholds.schema_compliance_score,
            "critical_issues": thresholds.critical_issues,
        }
    elif metric_type == MetricType.REPORT:
        return {
            "completeness_score": thresholds.completeness_score,
            "accuracy_score": thresholds.accuracy_score,
            "cross_reference_consistency_score": thresholds.cross_reference_consistency_score,
            "data_consistency_score": thresholds.data_consistency_score,
            "schema_compliance_score": thresholds.schema_compliance_score,
            "critical_issues": thresholds.critical_issues,
        }
    return {}
