# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Tests for appraisal quality assessment logic.

Tests cover:
- is_appraisal_quality_sufficient() with all thresholds
- Custom threshold support
- Edge cases (None, empty dict, missing scores)
- _get_appraisal_prompt_name() routing for all publication types
- UnsupportedPublicationType exception handling
"""

import pytest

from src.pipeline.steps.appraisal import (
    APPRAISAL_QUALITY_THRESHOLDS,
    UnsupportedPublicationType,
    _get_appraisal_prompt_name,
    is_appraisal_quality_sufficient,
)


class TestAppraisalQualityAssessment:
    """Test appraisal quality threshold checking logic."""

    def test_quality_sufficient_all_thresholds_met(self):
        """Test quality check passes when all appraisal thresholds are met."""
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

    def test_quality_insufficient_logical_consistency_below_threshold(self):
        """Test quality check fails when logical consistency is below threshold (0.90)."""
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

    def test_quality_insufficient_completeness_below_threshold(self):
        """Test quality check fails when completeness is below threshold (0.85)."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.95,
                "completeness_score": 0.80,  # Below 0.85
                "evidence_support_score": 0.92,
                "schema_compliance_score": 1.0,
                "critical_issues": 0,
            }
        }

        assert is_appraisal_quality_sufficient(validation) is False

    def test_quality_insufficient_evidence_support_below_threshold(self):
        """Test quality check fails when evidence support is below threshold (0.90)."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.95,
                "completeness_score": 0.90,
                "evidence_support_score": 0.85,  # Below 0.90
                "schema_compliance_score": 1.0,
                "critical_issues": 0,
            }
        }

        assert is_appraisal_quality_sufficient(validation) is False

    def test_quality_insufficient_schema_compliance_below_threshold(self):
        """Test quality check fails when schema compliance is below threshold (0.95)."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.95,
                "completeness_score": 0.90,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 0.90,  # Below 0.95
                "critical_issues": 0,
            }
        }

        assert is_appraisal_quality_sufficient(validation) is False

    def test_quality_insufficient_critical_issues(self):
        """Test quality check fails when critical issues exist."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.95,
                "completeness_score": 0.90,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 1.0,
                "critical_issues": 1,  # Should be 0
            }
        }

        assert is_appraisal_quality_sufficient(validation) is False

    def test_quality_with_custom_thresholds(self):
        """Test quality check with custom thresholds."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.85,
                "completeness_score": 0.80,
                "evidence_support_score": 0.85,
                "schema_compliance_score": 0.90,
                "critical_issues": 0,
            }
        }

        custom_thresholds = {
            "logical_consistency_score": 0.80,
            "completeness_score": 0.75,
            "evidence_support_score": 0.80,
            "schema_compliance_score": 0.85,
            "critical_issues": 0,
        }

        assert is_appraisal_quality_sufficient(validation, custom_thresholds) is True

    def test_quality_none_validation_result(self):
        """Test quality check returns False for None validation_result."""
        assert is_appraisal_quality_sufficient(None) is False

    def test_quality_empty_validation_result(self):
        """Test quality check returns False for empty validation_result."""
        assert is_appraisal_quality_sufficient({}) is False

    def test_quality_missing_validation_summary(self):
        """Test quality check returns False when validation_summary is missing."""
        validation = {"other_field": "value"}
        assert is_appraisal_quality_sufficient(validation) is False

    def test_quality_empty_validation_summary(self):
        """Test quality check returns False when validation_summary is empty dict."""
        validation = {"validation_summary": {}}
        assert is_appraisal_quality_sufficient(validation) is False

    def test_quality_missing_individual_scores(self):
        """Test quality check fails when individual scores are missing."""
        # Missing logical_consistency_score → defaults to 0 → fails threshold
        validation = {
            "validation_summary": {
                "completeness_score": 0.90,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 1.0,
                "critical_issues": 0,
            }
        }
        assert is_appraisal_quality_sufficient(validation) is False

    def test_quality_none_score_values(self):
        """Test quality check handles None score values (treated as 0)."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": None,  # Treated as 0
                "completeness_score": 0.90,
                "evidence_support_score": 0.92,
                "schema_compliance_score": 1.0,
                "critical_issues": 0,
            }
        }
        assert is_appraisal_quality_sufficient(validation) is False

    def test_quality_exact_threshold_values(self):
        """Test quality check passes when scores exactly match thresholds."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": 0.90,  # Exact match
                "completeness_score": 0.85,  # Exact match
                "evidence_support_score": 0.90,  # Exact match
                "schema_compliance_score": 0.95,  # Exact match
                "critical_issues": 0,
            }
        }
        assert is_appraisal_quality_sufficient(validation) is True

    def test_quality_uses_default_thresholds(self):
        """Test quality check uses APPRAISAL_QUALITY_THRESHOLDS by default."""
        validation = {
            "validation_summary": {
                "logical_consistency_score": APPRAISAL_QUALITY_THRESHOLDS[
                    "logical_consistency_score"
                ],
                "completeness_score": APPRAISAL_QUALITY_THRESHOLDS["completeness_score"],
                "evidence_support_score": APPRAISAL_QUALITY_THRESHOLDS["evidence_support_score"],
                "schema_compliance_score": APPRAISAL_QUALITY_THRESHOLDS["schema_compliance_score"],
                "critical_issues": APPRAISAL_QUALITY_THRESHOLDS["critical_issues"],
            }
        }
        assert is_appraisal_quality_sufficient(validation) is True


class TestAppraisalPromptRouting:
    """Test publication type to appraisal prompt mapping."""

    def test_interventional_trial_routing(self):
        """Test interventional trial routes to RoB 2 prompt."""
        assert _get_appraisal_prompt_name("interventional_trial") == "Appraisal-interventional"

    def test_observational_analytic_routing(self):
        """Test observational analytic routes to ROBINS-I prompt."""
        assert _get_appraisal_prompt_name("observational_analytic") == "Appraisal-observational"

    def test_evidence_synthesis_routing(self):
        """Test evidence synthesis routes to AMSTAR 2 + ROBIS prompt."""
        assert _get_appraisal_prompt_name("evidence_synthesis") == "Appraisal-evidence-synthesis"

    def test_prediction_prognosis_routing(self):
        """Test prediction/prognosis routes to PROBAST prompt."""
        assert _get_appraisal_prompt_name("prediction_prognosis") == "Appraisal-prediction"

    def test_diagnostic_routing(self):
        """Test diagnostic routes to prediction prompt (shared PROBAST/QUADAS)."""
        assert _get_appraisal_prompt_name("diagnostic") == "Appraisal-prediction"

    def test_editorials_opinion_routing(self):
        """Test editorials/opinion routes to argument quality prompt."""
        assert _get_appraisal_prompt_name("editorials_opinion") == "Appraisal-editorials"

    def test_unsupported_publication_type(self):
        """Test unsupported publication type raises exception."""
        with pytest.raises(UnsupportedPublicationType) as exc_info:
            _get_appraisal_prompt_name("overig")

        assert "overig" in str(exc_info.value)
        assert "not supported" in str(exc_info.value).lower()

    def test_unsupported_type_includes_supported_types_in_message(self):
        """Test exception message includes list of supported types."""
        with pytest.raises(UnsupportedPublicationType) as exc_info:
            _get_appraisal_prompt_name("unknown_type")

        message = str(exc_info.value)
        assert "interventional_trial" in message
        assert "observational_analytic" in message
        assert "evidence_synthesis" in message
        assert "prediction_prognosis" in message

    def test_unsupported_type_exception_has_publication_type_attribute(self):
        """Test exception has publication_type attribute."""
        try:
            _get_appraisal_prompt_name("invalid")
        except UnsupportedPublicationType as e:
            assert e.publication_type == "invalid"

    def test_empty_publication_type(self):
        """Test empty string publication type raises exception."""
        with pytest.raises(UnsupportedPublicationType):
            _get_appraisal_prompt_name("")

    def test_none_publication_type(self):
        """Test None publication type raises exception (dict lookup fails)."""
        with pytest.raises((UnsupportedPublicationType, TypeError)):
            _get_appraisal_prompt_name(None)

    def test_case_sensitive_routing(self):
        """Test routing is case-sensitive."""
        with pytest.raises(UnsupportedPublicationType):
            _get_appraisal_prompt_name("Interventional_Trial")  # Wrong case
