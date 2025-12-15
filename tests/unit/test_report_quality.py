# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for report quality functions (Phase 3).

Tests cover:
- _extract_report_metrics() - metric extraction from validation results
- is_report_quality_sufficient() - quality threshold checking
- _select_best_report_iteration() - iteration selection logic
- Edge cases: missing data, custom thresholds, boundary conditions
"""

import pytest

from src.pipeline.steps.report import (
    REPORT_QUALITY_THRESHOLDS,
    _extract_report_metrics,
    _select_best_report_iteration,
    is_report_quality_sufficient,
)


class TestExtractReportMetrics:
    """Test _extract_report_metrics() function."""

    def test_extract_complete_metrics(self):
        """Test extracting metrics from complete validation result."""
        validation_result = {
            "validation_summary": {
                "completeness_score": 0.85,
                "accuracy_score": 0.95,
                "cross_reference_consistency_score": 0.90,
                "data_consistency_score": 0.88,
                "schema_compliance_score": 0.96,
                "critical_issues": 0,
                "overall_status": "passed",
                "quality_score": 0.91,
            }
        }

        metrics = _extract_report_metrics(validation_result)

        assert metrics["completeness_score"] == 0.85
        assert metrics["accuracy_score"] == 0.95
        assert metrics["cross_reference_consistency_score"] == 0.90
        assert metrics["data_consistency_score"] == 0.88
        assert metrics["schema_compliance_score"] == 0.96
        assert metrics["critical_issues"] == 0
        assert metrics["overall_status"] == "passed"
        assert metrics["quality_score"] == 0.91

    def test_extract_with_missing_quality_score(self):
        """Test metric extraction when quality_score is missing (calculate weighted)."""
        validation_result = {
            "validation_summary": {
                "completeness_score": 0.80,
                "accuracy_score": 0.90,
                "cross_reference_consistency_score": 0.85,
                "data_consistency_score": 0.88,
                "schema_compliance_score": 0.92,
                "critical_issues": 1,
                "overall_status": "warning",
                # No quality_score provided
            }
        }

        metrics = _extract_report_metrics(validation_result)

        # Weighted calculation: 0.90*0.35 + 0.80*0.30 + 0.85*0.10 + 0.88*0.10 + 0.92*0.15
        expected_quality = 0.90 * 0.35 + 0.80 * 0.30 + 0.85 * 0.10 + 0.88 * 0.10 + 0.92 * 0.15
        assert metrics["quality_score"] == pytest.approx(expected_quality, rel=1e-3)
        assert metrics["critical_issues"] == 1
        assert metrics["overall_status"] == "warning"

    def test_extract_with_missing_metrics_defaults_to_zero(self):
        """Test that missing individual metrics default to 0."""
        validation_result = {
            "validation_summary": {
                "accuracy_score": 0.75,
                # Other metrics missing
            }
        }

        metrics = _extract_report_metrics(validation_result)

        assert metrics["completeness_score"] == 0
        assert metrics["accuracy_score"] == 0.75
        assert metrics["cross_reference_consistency_score"] == 0
        assert metrics["data_consistency_score"] == 0
        assert metrics["schema_compliance_score"] == 0
        assert metrics["critical_issues"] == 0
        assert metrics["overall_status"] == "unknown"

    def test_extract_with_empty_validation_summary(self):
        """Test extraction when validation_summary is empty."""
        validation_result = {"validation_summary": {}}

        metrics = _extract_report_metrics(validation_result)

        assert metrics["completeness_score"] == 0
        assert metrics["accuracy_score"] == 0
        assert metrics["quality_score"] == 0
        assert metrics["critical_issues"] == 0
        assert metrics["overall_status"] == "unknown"

    def test_extract_with_no_validation_summary(self):
        """Test extraction when validation_summary key is missing."""
        validation_result = {}

        metrics = _extract_report_metrics(validation_result)

        assert metrics["completeness_score"] == 0
        assert metrics["accuracy_score"] == 0
        assert metrics["overall_status"] == "unknown"


class TestIsReportQualitySufficient:
    """Test is_report_quality_sufficient() function."""

    def test_quality_sufficient_all_thresholds_met(self):
        """Test when all quality thresholds are met."""
        validation_result = {
            "validation_summary": {
                "completeness_score": 0.90,
                "accuracy_score": 0.97,
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.91,
                "schema_compliance_score": 0.96,
                "critical_issues": 0,
            }
        }

        result = is_report_quality_sufficient(validation_result, REPORT_QUALITY_THRESHOLDS)

        assert result is True

    def test_quality_insufficient_completeness(self):
        """Test when completeness is below threshold."""
        validation_result = {
            "validation_summary": {
                "completeness_score": 0.80,  # Below 0.85 threshold
                "accuracy_score": 0.97,
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.91,
                "schema_compliance_score": 0.96,
                "critical_issues": 0,
            }
        }

        result = is_report_quality_sufficient(validation_result, REPORT_QUALITY_THRESHOLDS)

        assert result is False

    def test_quality_insufficient_accuracy(self):
        """Test when accuracy is below threshold."""
        validation_result = {
            "validation_summary": {
                "completeness_score": 0.90,
                "accuracy_score": 0.92,  # Below 0.95 threshold
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.91,
                "schema_compliance_score": 0.96,
                "critical_issues": 0,
            }
        }

        result = is_report_quality_sufficient(validation_result, REPORT_QUALITY_THRESHOLDS)

        assert result is False

    def test_quality_insufficient_critical_issues(self):
        """Test when critical issues exist."""
        validation_result = {
            "validation_summary": {
                "completeness_score": 0.90,
                "accuracy_score": 0.97,
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.91,
                "schema_compliance_score": 0.96,
                "critical_issues": 1,  # Threshold is 0
            }
        }

        result = is_report_quality_sufficient(validation_result, REPORT_QUALITY_THRESHOLDS)

        assert result is False

    def test_quality_at_exact_thresholds(self):
        """Test when metrics are exactly at thresholds (should pass)."""
        validation_result = {
            "validation_summary": {
                "completeness_score": 0.85,  # Exactly at threshold
                "accuracy_score": 0.95,  # Exactly at threshold
                "cross_reference_consistency_score": 0.90,  # Exactly at threshold
                "data_consistency_score": 0.90,  # Exactly at threshold
                "schema_compliance_score": 0.95,  # Exactly at threshold
                "critical_issues": 0,
            }
        }

        result = is_report_quality_sufficient(validation_result, REPORT_QUALITY_THRESHOLDS)

        assert result is True

    def test_quality_with_custom_thresholds(self):
        """Test with custom (more lenient) thresholds."""
        validation_result = {
            "validation_summary": {
                "completeness_score": 0.75,
                "accuracy_score": 0.85,
                "cross_reference_consistency_score": 0.80,
                "data_consistency_score": 0.80,
                "schema_compliance_score": 0.85,
                "critical_issues": 0,
            }
        }

        custom_thresholds = {
            "completeness_score": 0.70,
            "accuracy_score": 0.80,
            "cross_reference_consistency_score": 0.75,
            "data_consistency_score": 0.75,
            "schema_compliance_score": 0.80,
            "critical_issues": 0,
        }

        result = is_report_quality_sufficient(validation_result, custom_thresholds)

        assert result is True

    def test_quality_with_missing_metric_defaults_to_zero(self):
        """Test that missing metrics default to 0 and fail threshold checks."""
        validation_result = {
            "validation_summary": {
                "accuracy_score": 0.97,
                # Other metrics missing - will default to 0
            }
        }

        result = is_report_quality_sufficient(validation_result, REPORT_QUALITY_THRESHOLDS)

        # Should fail because completeness, consistency scores default to 0
        assert result is False


class TestSelectBestReportIteration:
    """Test _select_best_report_iteration() function."""

    def test_select_single_iteration(self):
        """Test selection when only one iteration exists."""
        iterations = [
            {
                "iteration_num": 0,
                "report": {"sections": []},
                "validation": {"validation_summary": {}},
                "metrics": {
                    "quality_score": 0.85,
                    "accuracy_score": 0.90,
                    "critical_issues": 0,
                },
            }
        ]

        best = _select_best_report_iteration(iterations)

        assert best["iteration_num"] == 0
        assert best["metrics"]["quality_score"] == 0.85

    def test_select_best_by_quality_score(self):
        """Test selection prioritizes highest quality score."""
        iterations = [
            {
                "iteration_num": 0,
                "metrics": {
                    "quality_score": 0.75,
                    "accuracy_score": 0.80,
                    "critical_issues": 0,
                },
            },
            {
                "iteration_num": 1,
                "metrics": {
                    "quality_score": 0.90,  # Highest
                    "accuracy_score": 0.92,
                    "critical_issues": 0,
                },
            },
            {
                "iteration_num": 2,
                "metrics": {
                    "quality_score": 0.82,
                    "accuracy_score": 0.85,
                    "critical_issues": 0,
                },
            },
        ]

        best = _select_best_report_iteration(iterations)

        assert best["iteration_num"] == 1
        assert best["metrics"]["quality_score"] == 0.90

    def test_select_prioritizes_zero_critical_issues(self):
        """Test that zero critical issues is prioritized over higher quality score."""
        iterations = [
            {
                "iteration_num": 0,
                "metrics": {
                    "quality_score": 0.95,
                    "accuracy_score": 0.96,
                    "critical_issues": 2,  # Has critical issues
                },
            },
            {
                "iteration_num": 1,
                "metrics": {
                    "quality_score": 0.88,  # Lower quality
                    "accuracy_score": 0.90,
                    "critical_issues": 0,  # But no critical issues
                },
            },
        ]

        best = _select_best_report_iteration(iterations)

        # Should select iteration 1 (no critical issues)
        assert best["iteration_num"] == 1
        assert best["metrics"]["critical_issues"] == 0

    def test_select_by_accuracy_when_quality_tied(self):
        """Test accuracy score breaks ties when quality scores equal."""
        iterations = [
            {
                "iteration_num": 0,
                "metrics": {
                    "quality_score": 0.90,
                    "accuracy_score": 0.92,
                    "critical_issues": 0,
                },
            },
            {
                "iteration_num": 1,
                "metrics": {
                    "quality_score": 0.90,  # Same quality
                    "accuracy_score": 0.96,  # Higher accuracy
                    "critical_issues": 0,
                },
            },
        ]

        best = _select_best_report_iteration(iterations)

        assert best["iteration_num"] == 1
        assert best["metrics"]["accuracy_score"] == 0.96

    def test_select_prefers_earlier_iteration_when_all_equal(self):
        """Test that earlier iteration wins when all metrics equal."""
        iterations = [
            {
                "iteration_num": 0,
                "metrics": {
                    "quality_score": 0.90,
                    "accuracy_score": 0.92,
                    "critical_issues": 0,
                },
            },
            {
                "iteration_num": 1,
                "metrics": {
                    "quality_score": 0.90,  # Same
                    "accuracy_score": 0.92,  # Same
                    "critical_issues": 0,
                },
            },
        ]

        best = _select_best_report_iteration(iterations)

        # Should prefer earlier iteration (0)
        assert best["iteration_num"] == 0
