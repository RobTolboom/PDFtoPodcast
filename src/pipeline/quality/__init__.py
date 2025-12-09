"""
Quality assessment module for iterative correction loops.

This module provides unified quality scoring, metrics extraction, and threshold
checking for all pipeline stages (extraction, appraisal, report generation).

Public API:
    - QualityMetrics: Dataclass for unified quality metrics
    - QualityThresholds: Dataclass for quality thresholds
    - MetricType: Enum for metric types (EXTRACTION, APPRAISAL, REPORT)
    - extract_metrics(): Extract metrics from validation result
    - safe_score(): Safely extract numeric scores from dict
    - quality_rank(): Create sortable quality tuple for iteration ranking
    - is_quality_sufficient(): Check if quality meets thresholds
    - EXTRACTION_THRESHOLDS: Default thresholds for extraction
    - APPRAISAL_THRESHOLDS: Default thresholds for appraisal
    - REPORT_THRESHOLDS: Default thresholds for report generation
"""

from .metrics import (
    MetricType,
    QualityMetrics,
    extract_appraisal_metrics_as_dict,
    extract_extraction_metrics_as_dict,
    extract_metrics,
    extract_report_metrics_as_dict,
)
from .scoring import QualityWeights, quality_rank, safe_score
from .thresholds import (
    APPRAISAL_THRESHOLDS,
    EXTRACTION_THRESHOLDS,
    REPORT_THRESHOLDS,
    QualityThresholds,
    is_quality_sufficient,
)

__all__ = [
    # Dataclasses
    "QualityMetrics",
    "QualityThresholds",
    "QualityWeights",
    # Enums
    "MetricType",
    # Functions
    "extract_metrics",
    "extract_extraction_metrics_as_dict",
    "extract_appraisal_metrics_as_dict",
    "extract_report_metrics_as_dict",
    "safe_score",
    "quality_rank",
    "is_quality_sufficient",
    # Constants
    "EXTRACTION_THRESHOLDS",
    "APPRAISAL_THRESHOLDS",
    "REPORT_THRESHOLDS",
]
