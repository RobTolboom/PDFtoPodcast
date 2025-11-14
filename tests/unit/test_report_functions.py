# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for report generation helper functions.

Tests cover:
- is_report_quality_sufficient() quality assessment
- _get_report_prompt_name() routing
- _extract_report_metrics() metric extraction and quality score calculation
- _select_best_report_iteration() best iteration selection

Note: Full integration testing should be in test_report_full_loop.py
These unit tests focus on edge cases and internal logic.
"""

import pytest

from src.pipeline.orchestrator import (
    UnsupportedPublicationType,
    _extract_report_metrics,
    _get_report_prompt_name,
    _select_best_report_iteration,
    is_report_quality_sufficient,
)


class TestReportQualityAssessment:
    """Test report quality threshold checking."""

    def test_quality_sufficient_all_thresholds_met(self):
        """Test quality passes when all thresholds met."""
        validation = {
            "validation_summary": {
                "completeness_score": 0.90,
                "accuracy_score": 0.97,
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.95,
                "schema_compliance_score": 0.98,
                "critical_issues": 0,
            }
        }
        assert is_report_quality_sufficient(validation) is True

    def test_quality_insufficient_single_threshold_fail(self):
        """Test quality fails when any threshold not met."""
        validation = {
            "validation_summary": {
                "completeness_score": 0.80,  # Below 0.85
                "accuracy_score": 0.97,
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.95,
                "schema_compliance_score": 0.98,
                "critical_issues": 0,
            }
        }
        assert is_report_quality_sufficient(validation) is False

    def test_quality_fails_with_critical_issues(self):
        """Test quality fails when critical issues exist."""
        validation = {
            "validation_summary": {
                "completeness_score": 0.90,
                "accuracy_score": 0.97,
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.95,
                "schema_compliance_score": 0.98,
                "critical_issues": 1,  # Not allowed
            }
        }
        assert is_report_quality_sufficient(validation) is False

    def test_quality_with_custom_thresholds(self):
        """Test custom thresholds override defaults."""
        validation = {
            "validation_summary": {
                "completeness_score": 0.70,
                "accuracy_score": 0.80,
                "cross_reference_consistency_score": 0.75,
                "data_consistency_score": 0.75,
                "schema_compliance_score": 0.85,
                "critical_issues": 0,
            }
        }

        custom_thresholds = {
            "completeness_score": 0.65,
            "accuracy_score": 0.75,
            "cross_reference_consistency_score": 0.70,
            "data_consistency_score": 0.70,
            "schema_compliance_score": 0.80,
            "critical_issues": 0,
        }

        assert is_report_quality_sufficient(validation, custom_thresholds) is True

    def test_quality_none_and_missing(self):
        """Test edge cases: None, empty dict, missing fields."""
        assert is_report_quality_sufficient(None) is False
        assert is_report_quality_sufficient({}) is False
        assert is_report_quality_sufficient({"validation_summary": {}}) is False


class TestReportPromptRouting:
    """Test publication type to prompt mapping."""

    def test_all_supported_types_route_correctly(self):
        """Test all 5 supported types route to correct prompts."""
        routing = {
            "interventional_trial": "Report-generation-rct",
            "observational_analytic": "Report-generation-observational",
            "evidence_synthesis": "Report-generation-systematic-review",
            "prediction_prognosis": "Report-generation-prediction",
            "editorials_opinion": "Report-generation-editorials",
        }

        for pub_type, expected_prompt in routing.items():
            assert _get_report_prompt_name(pub_type) == expected_prompt

    def test_unsupported_type_raises_exception(self):
        """Test unsupported types raise UnsupportedPublicationType."""
        with pytest.raises(UnsupportedPublicationType) as exc:
            _get_report_prompt_name("overig")

        assert "overig" in str(exc.value)
        assert "not supported" in str(exc.value).lower()


class TestReportMetricsExtraction:
    """Test metric extraction from validation results."""

    def test_extract_all_metrics_present(self):
        """Test extraction when all metrics present."""
        validation = {
            "validation_summary": {
                "completeness_score": 0.90,
                "accuracy_score": 0.96,
                "cross_reference_consistency_score": 0.92,
                "data_consistency_score": 0.94,
                "schema_compliance_score": 0.98,
                "critical_issues": 0,
                "overall_status": "passed",
            }
        }

        metrics = _extract_report_metrics(validation)

        assert metrics["completeness_score"] == 0.90
        assert metrics["accuracy_score"] == 0.96
        assert metrics["cross_reference_consistency_score"] == 0.92
        assert metrics["data_consistency_score"] == 0.94
        assert metrics["schema_compliance_score"] == 0.98
        assert metrics["critical_issues"] == 0

    def test_extract_calculates_quality_score_correctly(self):
        """Test quality score calculation using formula."""
        validation = {
            "validation_summary": {
                "completeness_score": 0.90,  # weight 0.30
                "accuracy_score": 1.00,  # weight 0.35
                "cross_reference_consistency_score": 0.80,  # weight 0.10
                "data_consistency_score": 0.90,  # weight 0.10
                "schema_compliance_score": 1.00,  # weight 0.15
            }
        }

        metrics = _extract_report_metrics(validation)

        # Expected: 0.35*1.00 + 0.30*0.90 + 0.10*0.80 + 0.10*0.90 + 0.15*1.00
        # = 0.35 + 0.27 + 0.08 + 0.09 + 0.15 = 0.94
        expected_quality = 0.94
        assert abs(metrics["quality_score"] - expected_quality) < 0.001

    def test_extract_missing_fields_returns_zeros(self):
        """Test extraction with missing fields returns 0.0."""
        validation = {
            "validation_summary": {
                "completeness_score": 0.90,
                # Missing other scores
            }
        }

        metrics = _extract_report_metrics(validation)

        assert metrics["completeness_score"] == 0.90
        assert metrics["accuracy_score"] == 0.0
        assert metrics["cross_reference_consistency_score"] == 0.0
        assert metrics["data_consistency_score"] == 0.0
        assert metrics["schema_compliance_score"] == 0.0
        assert metrics["critical_issues"] == 0

    def test_extract_none_validation_returns_zeros(self):
        """Test None validation returns all zeros."""
        metrics = _extract_report_metrics(None)

        assert metrics["completeness_score"] == 0.0
        assert metrics["accuracy_score"] == 0.0
        assert metrics["quality_score"] == 0.0
        assert metrics["critical_issues"] == 0

    def test_extract_empty_validation_returns_zeros(self):
        """Test empty validation dict returns all zeros."""
        metrics = _extract_report_metrics({})

        assert metrics["completeness_score"] == 0.0
        assert metrics["accuracy_score"] == 0.0
        assert metrics["quality_score"] == 0.0


class TestBestReportSelection:
    """Test selecting best report iteration."""

    def test_select_best_by_quality_score(self):
        """Test selects iteration with highest quality score."""
        iterations = [
            {
                "iteration": 1,
                "quality_score": 0.85,
                "completeness_score": 0.80,
                "report": {"metadata": {"title": "v1"}},
            },
            {
                "iteration": 2,
                "quality_score": 0.92,
                "completeness_score": 0.90,
                "report": {"metadata": {"title": "v2"}},
            },
            {
                "iteration": 3,
                "quality_score": 0.88,
                "completeness_score": 0.85,
                "report": {"metadata": {"title": "v3"}},
            },
        ]

        best = _select_best_report_iteration(iterations)

        assert best["iteration"] == 2
        assert best["quality_score"] == 0.92
        assert best["report"]["metadata"]["title"] == "v2"

    def test_select_first_when_equal_scores(self):
        """Test selects first iteration when scores are equal."""
        iterations = [
            {"iteration": 1, "quality_score": 0.90, "report": {"id": "first"}},
            {"iteration": 2, "quality_score": 0.90, "report": {"id": "second"}},
        ]

        best = _select_best_report_iteration(iterations)

        assert best["iteration"] == 1
        assert best["report"]["id"] == "first"

    def test_select_single_iteration(self):
        """Test with single iteration returns that iteration."""
        iterations = [{"iteration": 1, "quality_score": 0.75, "report": {"data": "test"}}]

        best = _select_best_report_iteration(iterations)

        assert best["iteration"] == 1
        assert best["quality_score"] == 0.75

    def test_select_empty_list_returns_none(self):
        """Test empty list returns None."""
        best = _select_best_report_iteration([])
        assert best is None

    def test_select_handles_missing_quality_score(self):
        """Test iterations without quality_score default to 0.0."""
        iterations = [
            {"iteration": 1, "report": {"data": "v1"}},  # No quality_score
            {"iteration": 2, "quality_score": 0.50, "report": {"data": "v2"}},
        ]

        best = _select_best_report_iteration(iterations)

        # Should select iteration 2 with explicit quality_score
        assert best["iteration"] == 2
