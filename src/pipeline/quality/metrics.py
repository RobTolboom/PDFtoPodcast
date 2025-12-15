"""
Quality metrics extraction and data structures.

This module provides unified metrics extraction for all pipeline stages,
replacing the duplicate _extract_metrics(), _extract_appraisal_metrics(),
and _extract_report_metrics() functions in orchestrator.py.
"""

from dataclasses import dataclass, field
from enum import Enum


class MetricType(Enum):
    """Type of metrics to extract from validation result."""

    EXTRACTION = "extraction"
    APPRAISAL = "appraisal"
    REPORT = "report"


@dataclass(frozen=True)
class QualityMetrics:
    """
    Unified quality metrics structure for all pipeline stages.

    This dataclass consolidates metrics from extraction, appraisal, and report
    validation results into a common structure for comparison and ranking.

    Common Fields:
        completeness_score: Coverage of expected data (0.0-1.0)
        schema_compliance_score: Structural correctness (0.0-1.0)
        critical_issues: Count of critical errors (0 = best)
        overall_status: Status string ("passed", "failed", "unknown")
        quality_score: Weighted composite score (0.0-1.0)

    Extraction-specific:
        accuracy_score: Correctness, no hallucinations (0.0-1.0)
        total_issues: Total issue count

    Appraisal-specific:
        logical_consistency_score: Logical consistency (0.0-1.0)
        evidence_support_score: Rationales match extraction (0.0-1.0)

    Report-specific:
        accuracy_score: Data correctness (0.0-1.0)
        cross_reference_consistency_score: Table/figure refs valid (0.0-1.0)
        data_consistency_score: Bottom-line matches results (0.0-1.0)
    """

    # Common fields (all types)
    completeness_score: float = 0.0
    schema_compliance_score: float = 0.0
    critical_issues: int = 0
    overall_status: str = "unknown"
    quality_score: float = 0.0

    # Extraction-specific
    accuracy_score: float = 0.0
    total_issues: int = 0

    # Appraisal-specific
    logical_consistency_score: float = 0.0
    evidence_support_score: float = 0.0

    # Report-specific
    cross_reference_consistency_score: float = 0.0
    data_consistency_score: float = 0.0

    # Metadata
    metric_type: MetricType = field(default=MetricType.EXTRACTION)

    def to_dict(self) -> dict:
        """Convert metrics to dict for serialization."""
        return {
            "completeness_score": self.completeness_score,
            "schema_compliance_score": self.schema_compliance_score,
            "critical_issues": self.critical_issues,
            "overall_status": self.overall_status,
            "quality_score": self.quality_score,
            "accuracy_score": self.accuracy_score,
            "total_issues": self.total_issues,
            "logical_consistency_score": self.logical_consistency_score,
            "evidence_support_score": self.evidence_support_score,
            "cross_reference_consistency_score": self.cross_reference_consistency_score,
            "data_consistency_score": self.data_consistency_score,
            "metric_type": self.metric_type.value,
        }


def _safe_get(summary: dict, key: str, default: float = 0.0) -> float:
    """Safely extract numeric value from dict."""
    val = summary.get(key, default)
    return val if isinstance(val, int | float) else default


def _extract_extraction_metrics(validation_result: dict) -> QualityMetrics:
    """
    Extract metrics from extraction validation result.

    Quality score composition:
        - 40% completeness (coverage of PDF data)
        - 40% accuracy (correctness, no hallucinations)
        - 20% schema compliance (structural correctness)
    """
    summary = validation_result.get("verification_summary", {})

    completeness = _safe_get(summary, "completeness_score")
    accuracy = _safe_get(summary, "accuracy_score")
    schema = _safe_get(summary, "schema_compliance_score")

    # Compute quality score (weighted composite)
    quality_score = completeness * 0.4 + accuracy * 0.4 + schema * 0.2

    return QualityMetrics(
        completeness_score=completeness,
        accuracy_score=accuracy,
        schema_compliance_score=schema,
        critical_issues=int(_safe_get(summary, "critical_issues")),
        total_issues=int(_safe_get(summary, "total_issues")),
        overall_status=summary.get("overall_status", "unknown"),
        quality_score=quality_score,
        metric_type=MetricType.EXTRACTION,
    )


def _extract_appraisal_metrics(validation_result: dict) -> QualityMetrics:
    """
    Extract metrics from appraisal validation result.

    Quality score composition:
        - 35% logical_consistency (overall = worst domain, GRADE alignment)
        - 25% completeness (all domains, all outcomes)
        - 25% evidence_support (rationales match extraction)
        - 15% schema_compliance (enums, required fields)
    """
    summary = validation_result.get("validation_summary", {})

    logical = _safe_get(summary, "logical_consistency_score")
    completeness = _safe_get(summary, "completeness_score")
    evidence = _safe_get(summary, "evidence_support_score")
    schema = _safe_get(summary, "schema_compliance_score")

    # Use provided quality_score or compute fallback
    quality_score = summary.get(
        "quality_score", logical * 0.35 + completeness * 0.25 + evidence * 0.25 + schema * 0.15
    )

    return QualityMetrics(
        completeness_score=completeness,
        schema_compliance_score=schema,
        critical_issues=int(_safe_get(summary, "critical_issues")),
        overall_status=summary.get("overall_status", "unknown"),
        quality_score=quality_score,
        logical_consistency_score=logical,
        evidence_support_score=evidence,
        metric_type=MetricType.APPRAISAL,
    )


def _extract_report_metrics(validation_result: dict) -> QualityMetrics:
    """
    Extract metrics from report validation result.

    Quality score composition:
        - 35% accuracy (data correctness paramount)
        - 30% completeness (all core sections present)
        - 10% cross_reference_consistency (table/figure refs valid)
        - 10% data_consistency (bottom-line matches results)
        - 15% schema_compliance (enums, required fields)
    """
    summary = validation_result.get("validation_summary", {})

    accuracy = _safe_get(summary, "accuracy_score")
    completeness = _safe_get(summary, "completeness_score")
    cross_ref = _safe_get(summary, "cross_reference_consistency_score")
    data_cons = _safe_get(summary, "data_consistency_score")
    schema = _safe_get(summary, "schema_compliance_score")

    # Use provided quality_score or compute fallback
    quality_score = summary.get(
        "quality_score",
        accuracy * 0.35 + completeness * 0.30 + cross_ref * 0.10 + data_cons * 0.10 + schema * 0.15,
    )

    return QualityMetrics(
        completeness_score=completeness,
        accuracy_score=accuracy,
        schema_compliance_score=schema,
        critical_issues=int(_safe_get(summary, "critical_issues")),
        overall_status=summary.get("overall_status", "unknown"),
        quality_score=quality_score,
        cross_reference_consistency_score=cross_ref,
        data_consistency_score=data_cons,
        metric_type=MetricType.REPORT,
    )


def extract_metrics(validation_result: dict | None, metric_type: MetricType) -> QualityMetrics:
    """
    Extract quality metrics from validation result based on type.

    This is the unified entry point that replaces the three separate
    _extract_*_metrics() functions in orchestrator.py.

    Args:
        validation_result: Validation JSON with verification_summary or validation_summary.
            Can be None or empty dict - returns default metrics in that case.
        metric_type: Type of metrics to extract (EXTRACTION, APPRAISAL, REPORT)

    Returns:
        QualityMetrics: Unified metrics structure. Returns default (zero) metrics
            if validation_result is None or empty.

    Example:
        >>> validation = {
        ...     'verification_summary': {
        ...         'completeness_score': 0.92,
        ...         'accuracy_score': 0.98,
        ...         'schema_compliance_score': 0.97,
        ...         'critical_issues': 0
        ...     }
        ... }
        >>> metrics = extract_metrics(validation, MetricType.EXTRACTION)
        >>> metrics.quality_score
        0.95  # (0.92*0.4 + 0.98*0.4 + 0.97*0.2)
        >>> extract_metrics(None, MetricType.EXTRACTION).quality_score
        0.0  # Default for missing input
    """
    # Handle None or empty input gracefully
    if not validation_result:
        return QualityMetrics(metric_type=metric_type, overall_status="missing")

    extractors = {
        MetricType.EXTRACTION: _extract_extraction_metrics,
        MetricType.APPRAISAL: _extract_appraisal_metrics,
        MetricType.REPORT: _extract_report_metrics,
    }

    extractor = extractors.get(metric_type)
    if extractor is None:
        raise ValueError(f"Unknown metric type: {metric_type}")

    return extractor(validation_result)


def extract_extraction_metrics_as_dict(validation_result: dict | None) -> dict:
    """
    Extract extraction metrics and return as dict for backward compatibility.

    This wrapper function replaces the duplicate _extract_metrics() functions
    in orchestrator.py and steps/validation.py.

    Returns dict with 'overall_quality' key for backward compatibility.
    """
    metrics = extract_metrics(validation_result, MetricType.EXTRACTION)
    result = metrics.to_dict()
    # Add backward-compatible 'overall_quality' key (alias for quality_score)
    result["overall_quality"] = metrics.quality_score
    return result


def extract_appraisal_metrics_as_dict(validation_result: dict | None) -> dict:
    """
    Extract appraisal metrics and return as dict for backward compatibility.

    This wrapper function replaces the duplicate _extract_appraisal_metrics()
    functions in orchestrator.py and steps/appraisal.py.
    """
    metrics = extract_metrics(validation_result, MetricType.APPRAISAL)
    return metrics.to_dict()


def extract_report_metrics_as_dict(validation_result: dict | None) -> dict:
    """
    Extract report metrics and return as dict for backward compatibility.

    This wrapper function replaces the duplicate _extract_report_metrics()
    functions in orchestrator.py and steps/report.py.
    """
    metrics = extract_metrics(validation_result, MetricType.REPORT)
    return metrics.to_dict()
