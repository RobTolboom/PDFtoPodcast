# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unified tests for appraisal helper functions.

Tests cover:
- is_appraisal_quality_sufficient() quality assessment
- _get_appraisal_prompt_name() routing
- _extract_appraisal_metrics() metric extraction
- _select_best_appraisal_iteration() best selection

Note: Full integration testing is in test_appraisal_full_loop.py
These unit tests focus on edge cases and internal logic.
"""

import pytest

from src.pipeline.orchestrator import (
    UnsupportedPublicationType,
    _extract_appraisal_metrics,
    _get_appraisal_prompt_name,
    _select_best_appraisal_iteration,
    is_appraisal_quality_sufficient,
)


class TestAppraisalQualityAssessment:
    """Test appraisal quality threshold checking."""

    def test_quality_sufficient_all_thresholds_met(self):
        """Test quality passes when all thresholds met."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.95,
                "completeness_score": 0.90,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 1.0,
                "critical_issues": 0,
            }
        }
        assert is_appraisal_quality_sufficient(validation) is True

    def test_quality_insufficient_single_threshold_fail(self):
        """Test quality fails when any threshold not met."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.85,  # Below 0.90
                "completeness_score": 0.90,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 1.0,
                "critical_issues": 0,
            }
        }
        assert is_appraisal_quality_sufficient(validation) is False

    def test_quality_fails_with_critical_issues(self):
        """Test quality fails when critical issues exist."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.95,
                "completeness_score": 0.90,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 1.0,
                "critical_issues": 1,  # Not allowed
            }
        }
        assert is_appraisal_quality_sufficient(validation) is False

    def test_quality_with_custom_thresholds(self):
        """Test custom thresholds override defaults."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.70,
                "completeness_score": 0.70,
                "evidence_support_score": 0.70,
                "schema_compliance_score": 0.70,
                "critical_issues": 0,
            }
        }

        custom_thresholds = {
            "logical_consistency_score": 0.65,
            "completeness_score": 0.65,
            "evidence_support_score": 0.65,
            "schema_compliance_score": 0.65,
            "critical_issues": 0,
        }

        assert is_appraisal_quality_sufficient(validation, custom_thresholds) is True

    def test_quality_none_and_missing(self):
        """Test edge cases: None, empty dict, missing fields."""
        assert is_appraisal_quality_sufficient(None) is False
        assert is_appraisal_quality_sufficient({}) is False
        assert is_appraisal_quality_sufficient({"validation_summary": {}}) is False


class TestAppraisalPromptRouting:
    """Test publication type to prompt mapping."""

    def test_all_supported_types_route_correctly(self):
        """Test all 6 supported types route to correct prompts."""
        routing = {
            "interventional_trial": "Appraisal-interventional",
            "observational_analytic": "Appraisal-observational",
            "evidence_synthesis": "Appraisal-evidence-synthesis",
            "prediction_prognosis": "Appraisal-prediction",
            "diagnostic": "Appraisal-prediction",  # Shared with prediction
            "editorials_opinion": "Appraisal-editorials",
        }

        for pub_type, expected_prompt in routing.items():
            assert _get_appraisal_prompt_name(pub_type) == expected_prompt

    def test_unsupported_type_raises_exception(self):
        """Test unsupported types raise UnsupportedPublicationType."""
        with pytest.raises(UnsupportedPublicationType) as exc:
            _get_appraisal_prompt_name("overig")

        assert "overig" in str(exc.value)
        assert "not supported" in str(exc.value).lower()


class TestAppraisalMetricsExtraction:
    """Test metric extraction from validation results."""

    def test_extract_all_metrics_present(self):
        """Test extraction when all metrics present."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.95,
                "completeness_score": 0.90,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 1.0,
                "quality_score": 0.94,
                "critical_issues": 0,
                "overall_status": "passed",
            }
        }

        metrics = _extract_appraisal_metrics(validation)

        assert metrics["logical_consistency_score"] == 0.95
        assert metrics["completeness_score"] == 0.90
        assert metrics["evidence_support_score"] == 0.92
        assert metrics["schema_compliance_score"] == 1.0
        assert metrics["quality_score"] == 0.94
        assert metrics["critical_issues"] == 0
        assert metrics["overall_status"] == "passed"

    def test_extract_computes_quality_score_fallback(self):
        """Test quality_score computed when missing."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.80,
                "completeness_score": 0.90,
                "evidence_support_score": 0.85,
                "schema_compliance_score": 1.0,
                # No quality_score
            }
        }

        metrics = _extract_appraisal_metrics(validation)

        # Should compute: 0.80*0.35 + 0.90*0.25 + 0.85*0.25 + 1.0*0.15 = 0.8675
        expected = 0.80 * 0.35 + 0.90 * 0.25 + 0.85 * 0.25 + 1.0 * 0.15
        assert abs(metrics["quality_score"] - expected) < 0.001

    def test_extract_defaults_missing_values(self):
        """Test defaults when validation_summary missing or empty."""
        assert _extract_appraisal_metrics({})["quality_score"] == 0.0
        assert _extract_appraisal_metrics({"validation_summary": {}})["critical_issues"] == 0


class TestBestAppraisalSelection:
    """Test best iteration selection logic."""

    def test_select_best_by_quality_score(self):
        """Test selection picks highest quality score."""
        iterations = [
            {
                "iteration_num": 0,
                "appraisal": {"study_id": "iter0"},
                "metrics": {
                    "quality_score": 0.75,
                    "critical_issues": 0,
                    "completeness_score": 0.80,
                },
            },
            {
                "iteration_num": 1,
                "appraisal": {"study_id": "iter1"},
                "metrics": {
                    "quality_score": 0.90,
                    "critical_issues": 0,
                    "completeness_score": 0.85,
                },  # Best
            },
            {
                "iteration_num": 2,
                "appraisal": {"study_id": "iter2"},
                "metrics": {
                    "quality_score": 0.82,
                    "critical_issues": 0,
                    "completeness_score": 0.83,
                },
            },
        ]

        best = _select_best_appraisal_iteration(iterations)
        assert best["iteration_num"] == 1

    def test_select_filters_critical_issues(self):
        """Test critical issues eliminate iterations from selection."""
        iterations = [
            {
                "iteration_num": 0,
                "appraisal": {"study_id": "iter0"},
                "metrics": {
                    "quality_score": 0.95,
                    "critical_issues": 2,
                    "completeness_score": 0.90,
                },  # Highest but has issues
            },
            {
                "iteration_num": 1,
                "appraisal": {"study_id": "iter1"},
                "metrics": {
                    "quality_score": 0.80,
                    "critical_issues": 0,
                    "completeness_score": 0.85,
                },  # Selected
            },
        ]

        best = _select_best_appraisal_iteration(iterations)
        assert best["iteration_num"] == 1  # Lower quality but no critical issues

    def test_select_tiebreaker_completeness(self):
        """Test tied quality_score uses completeness as tiebreaker."""
        iterations = [
            {
                "iteration_num": 0,
                "appraisal": {},
                "metrics": {
                    "quality_score": 0.85,
                    "critical_issues": 0,
                    "completeness_score": 0.75,
                },
            },
            {
                "iteration_num": 1,
                "appraisal": {},
                "metrics": {
                    "quality_score": 0.85,
                    "critical_issues": 0,
                    "completeness_score": 0.90,
                },  # Higher completeness
            },
        ]

        best = _select_best_appraisal_iteration(iterations)
        assert best["iteration_num"] == 1

    def test_select_single_iteration(self):
        """Test single iteration always selected."""
        iterations = [
            {
                "iteration_num": 0,
                "appraisal": {},
                "metrics": {
                    "quality_score": 0.50,
                    "critical_issues": 5,
                    "completeness_score": 0.40,
                },  # Bad but only option
            }
        ]

        best = _select_best_appraisal_iteration(iterations)
        assert best["iteration_num"] == 0
        assert best["selection_reason"] == "only_iteration"

    def test_select_empty_raises_error(self):
        """Test empty list raises ValueError."""
        with pytest.raises(ValueError):
            _select_best_appraisal_iteration([])
