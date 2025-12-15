"""
Unit tests for the quality module.

Tests cover:
- QualityMetrics dataclass
- MetricType enum
- extract_metrics() function for all types
- safe_score() utility
- quality_rank() function
- select_best_iteration() function
- QualityThresholds dataclass
- is_quality_sufficient() function for all types
"""

import pytest

from src.pipeline.quality import (
    APPRAISAL_THRESHOLDS,
    EXTRACTION_THRESHOLDS,
    REPORT_THRESHOLDS,
    MetricType,
    QualityMetrics,
    QualityThresholds,
    QualityWeights,
    extract_metrics,
    is_quality_sufficient,
    quality_rank,
    safe_score,
)
from src.pipeline.quality.scoring import select_best_iteration


class TestQualityMetrics:
    """Tests for QualityMetrics dataclass."""

    def test_default_values(self):
        """Test that QualityMetrics has sensible defaults."""
        metrics = QualityMetrics()
        assert metrics.completeness_score == 0.0
        assert metrics.accuracy_score == 0.0
        assert metrics.schema_compliance_score == 0.0
        assert metrics.critical_issues == 0
        assert metrics.overall_status == "unknown"
        assert metrics.quality_score == 0.0
        assert metrics.metric_type == MetricType.EXTRACTION

    def test_custom_values(self):
        """Test QualityMetrics with custom values."""
        metrics = QualityMetrics(
            completeness_score=0.95,
            accuracy_score=0.98,
            schema_compliance_score=0.97,
            critical_issues=1,
            overall_status="passed",
            quality_score=0.96,
            metric_type=MetricType.APPRAISAL,
        )
        assert metrics.completeness_score == 0.95
        assert metrics.accuracy_score == 0.98
        assert metrics.critical_issues == 1
        assert metrics.metric_type == MetricType.APPRAISAL

    def test_frozen_immutability(self):
        """Test that QualityMetrics is immutable (frozen)."""
        metrics = QualityMetrics(completeness_score=0.9)
        with pytest.raises(AttributeError):
            metrics.completeness_score = 0.5  # type: ignore

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = QualityMetrics(
            completeness_score=0.95,
            accuracy_score=0.98,
            metric_type=MetricType.EXTRACTION,
        )
        result = metrics.to_dict()
        assert result["completeness_score"] == 0.95
        assert result["accuracy_score"] == 0.98
        assert result["metric_type"] == "extraction"


class TestMetricType:
    """Tests for MetricType enum."""

    def test_enum_values(self):
        """Test that all metric types exist."""
        assert MetricType.EXTRACTION.value == "extraction"
        assert MetricType.APPRAISAL.value == "appraisal"
        assert MetricType.REPORT.value == "report"


class TestExtractMetrics:
    """Tests for extract_metrics() function."""

    def test_extract_extraction_metrics(self):
        """Test extracting metrics from extraction validation."""
        validation = {
            "verification_summary": {
                "completeness_score": 0.92,
                "accuracy_score": 0.98,
                "schema_compliance_score": 0.97,
                "critical_issues": 0,
                "total_issues": 2,
                "overall_status": "passed",
            }
        }
        metrics = extract_metrics(validation, MetricType.EXTRACTION)

        assert metrics.completeness_score == 0.92
        assert metrics.accuracy_score == 0.98
        assert metrics.schema_compliance_score == 0.97
        assert metrics.critical_issues == 0
        assert metrics.total_issues == 2
        assert metrics.overall_status == "passed"
        # Quality score: 0.92*0.4 + 0.98*0.4 + 0.97*0.2 = 0.954
        assert abs(metrics.quality_score - 0.954) < 0.001
        assert metrics.metric_type == MetricType.EXTRACTION

    def test_extract_appraisal_metrics(self):
        """Test extracting metrics from appraisal validation."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.95,
                "completeness_score": 0.90,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 1.0,
                "critical_issues": 0,
                "overall_status": "passed",
                "quality_score": 0.94,
            }
        }
        metrics = extract_metrics(validation, MetricType.APPRAISAL)

        assert metrics.logical_consistency_score == 0.95
        assert metrics.completeness_score == 0.90
        assert metrics.evidence_support_score == 0.92
        assert metrics.schema_compliance_score == 1.0
        assert metrics.quality_score == 0.94  # Uses provided score
        assert metrics.metric_type == MetricType.APPRAISAL

    def test_extract_appraisal_metrics_compute_fallback(self):
        """Test that appraisal computes quality_score if not provided."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.95,
                "completeness_score": 0.90,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 1.0,
                "critical_issues": 0,
            }
        }
        metrics = extract_metrics(validation, MetricType.APPRAISAL)

        # Computed: 0.95*0.35 + 0.90*0.25 + 0.92*0.25 + 1.0*0.15 = 0.9375
        assert abs(metrics.quality_score - 0.9375) < 0.001

    def test_extract_report_metrics(self):
        """Test extracting metrics from report validation."""
        validation = {
            "validation_summary": {
                "completeness_score": 0.90,
                "accuracy_score": 0.95,
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.88,
                "schema_compliance_score": 1.0,
                "critical_issues": 0,
                "overall_status": "passed",
            }
        }
        metrics = extract_metrics(validation, MetricType.REPORT)

        assert metrics.completeness_score == 0.90
        assert metrics.accuracy_score == 0.95
        assert metrics.cross_reference_consistency_score == 0.92
        assert metrics.data_consistency_score == 0.88
        assert metrics.schema_compliance_score == 1.0
        assert metrics.metric_type == MetricType.REPORT

    def test_extract_empty_validation(self):
        """Test extracting from empty validation result."""
        metrics = extract_metrics({}, MetricType.EXTRACTION)

        assert metrics.completeness_score == 0.0
        assert metrics.accuracy_score == 0.0
        assert metrics.quality_score == 0.0

    def test_extract_missing_summary(self):
        """Test extracting when summary is missing."""
        validation = {"other_field": "value"}
        metrics = extract_metrics(validation, MetricType.EXTRACTION)

        assert metrics.completeness_score == 0.0
        assert metrics.quality_score == 0.0

    def test_invalid_metric_type(self):
        """Test that invalid metric type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown metric type"):
            extract_metrics({}, "invalid")  # type: ignore


class TestSafeScore:
    """Tests for safe_score() utility function."""

    def test_existing_score(self):
        """Test extracting existing score."""
        summary = {"completeness_score": 0.95}
        assert safe_score(summary, "completeness_score") == 0.95

    def test_missing_score_default(self):
        """Test default value for missing score."""
        summary = {}
        assert safe_score(summary, "completeness_score") == 0.0
        assert safe_score(summary, "completeness_score", 0.5) == 0.5

    def test_none_value(self):
        """Test handling of None value."""
        summary = {"completeness_score": None}
        assert safe_score(summary, "completeness_score") == 0.0

    def test_integer_value(self):
        """Test handling of integer value."""
        summary = {"critical_issues": 2}
        assert safe_score(summary, "critical_issues") == 2

    def test_invalid_type(self):
        """Test handling of invalid type (string)."""
        summary = {"completeness_score": "invalid"}
        assert safe_score(summary, "completeness_score") == 0.0


class TestQualityRank:
    """Tests for quality_rank() function."""

    def test_basic_ranking(self):
        """Test basic quality ranking."""
        iteration = {
            "iteration_num": 0,
            "metrics": {
                "quality_score": 0.85,
                "completeness_score": 0.90,
                "critical_issues": 0,
            },
        }
        rank = quality_rank(iteration, MetricType.EXTRACTION)

        assert rank[0] is True  # No critical issues
        assert rank[1] == 0.85  # Quality score
        assert rank[2] == 0.90  # Completeness tiebreaker
        assert rank[3] == 0  # Negative iteration (prefer earlier)

    def test_critical_issues_priority(self):
        """Test that no critical issues ranks higher."""
        iter_clean = {"iteration_num": 0, "metrics": {"quality_score": 0.80, "critical_issues": 0}}
        iter_issues = {"iteration_num": 1, "metrics": {"quality_score": 0.90, "critical_issues": 1}}

        rank_clean = quality_rank(iter_clean, MetricType.EXTRACTION)
        rank_issues = quality_rank(iter_issues, MetricType.EXTRACTION)

        # Clean should rank higher despite lower quality score
        assert rank_clean > rank_issues

    def test_quality_score_priority(self):
        """Test that higher quality score ranks higher (when no critical issues)."""
        iter_low = {"iteration_num": 0, "metrics": {"quality_score": 0.80, "critical_issues": 0}}
        iter_high = {"iteration_num": 1, "metrics": {"quality_score": 0.90, "critical_issues": 0}}

        rank_low = quality_rank(iter_low, MetricType.EXTRACTION)
        rank_high = quality_rank(iter_high, MetricType.EXTRACTION)

        assert rank_high > rank_low

    def test_extraction_computes_quality_score(self):
        """Test that extraction computes quality_score from components if missing."""
        iteration = {
            "iteration_num": 0,
            "metrics": {
                "completeness_score": 0.90,
                "accuracy_score": 0.95,
                "schema_compliance_score": 1.0,
                "critical_issues": 0,
            },
        }
        rank = quality_rank(iteration, MetricType.EXTRACTION)

        # quality_score = 0.90*0.4 + 0.95*0.4 + 1.0*0.2 = 0.94
        assert abs(rank[1] - 0.94) < 0.001


class TestSelectBestIteration:
    """Tests for select_best_iteration() function."""

    def test_single_iteration(self):
        """Test selection with single iteration."""
        iterations = [
            {"iteration_num": 0, "metrics": {"quality_score": 0.85, "critical_issues": 0}}
        ]
        best = select_best_iteration(iterations, MetricType.EXTRACTION)

        assert best["iteration_num"] == 0
        assert best["selection_reason"] == "only_iteration"

    def test_select_highest_quality(self):
        """Test that highest quality iteration is selected."""
        iterations = [
            {"iteration_num": 0, "metrics": {"quality_score": 0.85, "critical_issues": 0}},
            {"iteration_num": 1, "metrics": {"quality_score": 0.92, "critical_issues": 0}},
            {"iteration_num": 2, "metrics": {"quality_score": 0.89, "critical_issues": 0}},
        ]
        best = select_best_iteration(iterations, MetricType.EXTRACTION)

        assert best["iteration_num"] == 1
        assert best["selection_reason"] == "quality_peaked_at_iteration_1"

    def test_skip_critical_issues(self):
        """Test that iterations with critical issues are skipped."""
        iterations = [
            {"iteration_num": 0, "metrics": {"quality_score": 0.85, "critical_issues": 0}},
            {"iteration_num": 1, "metrics": {"quality_score": 0.95, "critical_issues": 1}},
        ]
        best = select_best_iteration(iterations, MetricType.EXTRACTION)

        assert best["iteration_num"] == 0

    def test_final_iteration_best(self):
        """Test selection reason when final iteration is best."""
        iterations = [
            {"iteration_num": 0, "metrics": {"quality_score": 0.85, "critical_issues": 0}},
            {"iteration_num": 1, "metrics": {"quality_score": 0.92, "critical_issues": 0}},
        ]
        best = select_best_iteration(iterations, MetricType.EXTRACTION)

        assert best["iteration_num"] == 1
        assert best["selection_reason"] == "final_iteration_best"

    def test_empty_iterations_raises(self):
        """Test that empty iterations list raises ValueError."""
        with pytest.raises(ValueError, match="No iterations"):
            select_best_iteration([], MetricType.EXTRACTION)

    def test_report_prefers_accuracy_tiebreaker(self):
        """Test that report type uses accuracy as tiebreaker."""
        iterations = [
            {
                "iteration_num": 0,
                "metrics": {
                    "quality_score": 0.90,
                    "completeness_score": 0.95,
                    "accuracy_score": 0.85,
                    "critical_issues": 0,
                },
            },
            {
                "iteration_num": 1,
                "metrics": {
                    "quality_score": 0.90,
                    "completeness_score": 0.85,
                    "accuracy_score": 0.95,
                    "critical_issues": 0,
                },
            },
        ]
        best = select_best_iteration(iterations, MetricType.REPORT)

        # Should prefer iteration 1 (higher accuracy)
        assert best["iteration_num"] == 1


class TestQualityThresholds:
    """Tests for QualityThresholds dataclass."""

    def test_extraction_thresholds(self):
        """Test extraction threshold values."""
        assert EXTRACTION_THRESHOLDS.completeness_score == 0.90
        assert EXTRACTION_THRESHOLDS.accuracy_score == 0.95
        assert EXTRACTION_THRESHOLDS.schema_compliance_score == 0.95
        assert EXTRACTION_THRESHOLDS.critical_issues == 0

    def test_appraisal_thresholds(self):
        """Test appraisal threshold values."""
        assert APPRAISAL_THRESHOLDS.logical_consistency_score == 0.90
        assert APPRAISAL_THRESHOLDS.completeness_score == 0.85
        assert APPRAISAL_THRESHOLDS.evidence_support_score == 0.90
        assert APPRAISAL_THRESHOLDS.schema_compliance_score == 0.95
        assert APPRAISAL_THRESHOLDS.critical_issues == 0

    def test_report_thresholds(self):
        """Test report threshold values."""
        assert REPORT_THRESHOLDS.completeness_score == 0.85
        assert REPORT_THRESHOLDS.accuracy_score == 0.95
        assert REPORT_THRESHOLDS.cross_reference_consistency_score == 0.90
        assert REPORT_THRESHOLDS.data_consistency_score == 0.90
        assert REPORT_THRESHOLDS.schema_compliance_score == 0.95
        assert REPORT_THRESHOLDS.critical_issues == 0


class TestIsQualitySufficient:
    """Tests for is_quality_sufficient() function."""

    def test_extraction_passes(self):
        """Test extraction validation that passes all thresholds."""
        validation = {
            "verification_summary": {
                "completeness_score": 0.92,
                "accuracy_score": 0.98,
                "schema_compliance_score": 0.97,
                "critical_issues": 0,
            }
        }
        assert is_quality_sufficient(validation, MetricType.EXTRACTION) is True

    def test_extraction_fails_completeness(self):
        """Test extraction fails when completeness too low."""
        validation = {
            "verification_summary": {
                "completeness_score": 0.85,  # Below 0.90 threshold
                "accuracy_score": 0.98,
                "schema_compliance_score": 0.97,
                "critical_issues": 0,
            }
        }
        assert is_quality_sufficient(validation, MetricType.EXTRACTION) is False

    def test_extraction_fails_critical_issues(self):
        """Test extraction fails when critical issues present."""
        validation = {
            "verification_summary": {
                "completeness_score": 0.92,
                "accuracy_score": 0.98,
                "schema_compliance_score": 0.97,
                "critical_issues": 1,  # Above 0 threshold
            }
        }
        assert is_quality_sufficient(validation, MetricType.EXTRACTION) is False

    def test_appraisal_passes(self):
        """Test appraisal validation that passes all thresholds."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.92,
                "completeness_score": 0.88,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 0.97,
                "critical_issues": 0,
            }
        }
        assert is_quality_sufficient(validation, MetricType.APPRAISAL) is True

    def test_appraisal_fails_logical_consistency(self):
        """Test appraisal fails when logical consistency too low."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.85,  # Below 0.90 threshold
                "completeness_score": 0.88,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 0.97,
                "critical_issues": 0,
            }
        }
        assert is_quality_sufficient(validation, MetricType.APPRAISAL) is False

    def test_report_passes(self):
        """Test report validation that passes all thresholds."""
        validation = {
            "validation_summary": {
                "completeness_score": 0.88,
                "accuracy_score": 0.97,
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.92,
                "schema_compliance_score": 0.97,
                "critical_issues": 0,
            }
        }
        assert is_quality_sufficient(validation, MetricType.REPORT) is True

    def test_report_fails_data_consistency(self):
        """Test report fails when data consistency too low."""
        validation = {
            "validation_summary": {
                "completeness_score": 0.88,
                "accuracy_score": 0.97,
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.85,  # Below 0.90 threshold
                "schema_compliance_score": 0.97,
                "critical_issues": 0,
            }
        }
        assert is_quality_sufficient(validation, MetricType.REPORT) is False

    def test_none_validation_result(self):
        """Test that None validation result returns False."""
        assert is_quality_sufficient(None, MetricType.EXTRACTION) is False
        assert is_quality_sufficient(None, MetricType.APPRAISAL) is False
        assert is_quality_sufficient(None, MetricType.REPORT) is False

    def test_empty_validation_result(self):
        """Test that empty validation result returns False."""
        assert is_quality_sufficient({}, MetricType.EXTRACTION) is False

    def test_missing_summary(self):
        """Test that missing summary returns False."""
        validation = {"other_field": "value"}
        assert is_quality_sufficient(validation, MetricType.EXTRACTION) is False

    def test_custom_thresholds(self):
        """Test using custom thresholds."""
        validation = {
            "verification_summary": {
                "completeness_score": 0.80,
                "accuracy_score": 0.85,
                "schema_compliance_score": 0.90,
                "critical_issues": 0,
            }
        }
        # Fails default thresholds
        assert is_quality_sufficient(validation, MetricType.EXTRACTION) is False

        # Passes with lower custom thresholds
        custom = QualityThresholds(
            completeness_score=0.75,
            accuracy_score=0.80,
            schema_compliance_score=0.85,
            critical_issues=0,
        )
        assert is_quality_sufficient(validation, MetricType.EXTRACTION, custom) is True


class TestQualityWeights:
    """Tests for QualityWeights dataclass."""

    def test_default_values(self):
        """Test default weight values are zero."""
        weights = QualityWeights()
        assert weights.completeness == 0.0
        assert weights.accuracy == 0.0
        assert weights.schema_compliance == 0.0

    def test_custom_weights(self):
        """Test custom weight values."""
        weights = QualityWeights(
            completeness=0.4,
            accuracy=0.4,
            schema_compliance=0.2,
        )
        assert weights.completeness == 0.4
        assert weights.accuracy == 0.4
        assert weights.schema_compliance == 0.2

    def test_frozen_immutability(self):
        """Test that QualityWeights is immutable."""
        weights = QualityWeights(completeness=0.4)
        with pytest.raises(AttributeError):
            weights.completeness = 0.5  # type: ignore
