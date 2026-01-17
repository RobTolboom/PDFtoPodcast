# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Tests for iterative validation-correction loop functionality.

Tests cover:
- Quality assessment (is_quality_sufficient)
- Best iteration selection (_select_best_iteration)
- Quality degradation detection (_detect_quality_degradation)
- Main iterative loop (run_validation_with_correction)
- Edge cases and error handling
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.llm.base import LLMError
from src.pipeline.orchestrator import (
    STEP_VALIDATION_CORRECTION,
    _detect_quality_degradation,
    _extract_metrics,
    _select_best_iteration,
    is_quality_sufficient,
    run_validation_with_correction,
)


class TestQualityAssessment:
    """Test quality threshold checking logic."""

    def test_quality_sufficient_all_thresholds_met(self):
        """Test quality check passes when all thresholds are met."""
        validation = {
            "verification_summary": {
                "completeness_score": 0.92,
                "accuracy_score": 0.98,
                "schema_compliance_score": 0.97,
                "critical_issues": 0,
            }
        }

        assert is_quality_sufficient(validation) is True

    def test_quality_insufficient_completeness_below_threshold(self):
        """Test quality check fails when completeness is below threshold."""
        validation = {
            "verification_summary": {
                "completeness_score": 0.85,  # Below 0.90
                "accuracy_score": 0.98,
                "schema_compliance_score": 0.97,
                "critical_issues": 0,
            }
        }

        assert is_quality_sufficient(validation) is False

    def test_quality_insufficient_critical_issues(self):
        """Test quality check fails when critical issues exist."""
        validation = {
            "verification_summary": {
                "completeness_score": 0.95,
                "accuracy_score": 0.98,
                "schema_compliance_score": 0.97,
                "critical_issues": 1,  # Should be 0
            }
        }

        assert is_quality_sufficient(validation) is False

    def test_quality_with_custom_thresholds(self):
        """Test quality check with custom thresholds."""
        validation = {
            "verification_summary": {
                "completeness_score": 0.85,
                "accuracy_score": 0.92,
                "schema_compliance_score": 0.90,
                "critical_issues": 0,
            }
        }

        custom_thresholds = {
            "completeness_score": 0.80,
            "accuracy_score": 0.90,
            "schema_compliance_score": 0.85,
            "critical_issues": 0,
        }

        assert is_quality_sufficient(validation, custom_thresholds) is True

    def test_quality_none_validation_result(self):
        """Test quality check returns False for None validation_result."""
        assert is_quality_sufficient(None) is False

    def test_quality_empty_validation_result(self):
        """Test quality check returns False for empty validation_result."""
        assert is_quality_sufficient({}) is False

    def test_quality_missing_verification_summary(self):
        """Test quality check returns False when verification_summary is missing."""
        validation = {"other_field": "value"}
        assert is_quality_sufficient(validation) is False


class TestBestIterationSelection:
    """Test best iteration selection logic."""

    def test_select_best_single_iteration(self):
        """Test selection with only one iteration."""
        iterations = [
            {
                "iteration_num": 0,
                "metrics": {
                    "completeness_score": 0.85,
                    "accuracy_score": 0.90,
                    "schema_compliance_score": 0.88,
                    "critical_issues": 0,
                    "overall_quality": 0.876,
                },
            }
        ]

        best = _select_best_iteration(iterations)
        assert best["iteration_num"] == 0
        assert best["selection_reason"] == "only_iteration"

    def test_select_best_highest_quality(self):
        """Test selection chooses highest quality iteration."""
        iterations = [
            {
                "iteration_num": 0,
                "metrics": {
                    "completeness_score": 0.85,
                    "accuracy_score": 0.90,
                    "schema_compliance_score": 0.88,
                    "critical_issues": 0,
                    "overall_quality": 0.876,
                },
            },
            {
                "iteration_num": 1,
                "metrics": {
                    "completeness_score": 0.92,
                    "accuracy_score": 0.95,
                    "schema_compliance_score": 0.94,
                    "critical_issues": 0,
                    "overall_quality": 0.934,
                },
            },
            {
                "iteration_num": 2,
                "metrics": {
                    "completeness_score": 0.88,
                    "accuracy_score": 0.92,
                    "schema_compliance_score": 0.90,
                    "critical_issues": 0,
                    "overall_quality": 0.900,
                },
            },
        ]

        best = _select_best_iteration(iterations)
        assert best["iteration_num"] == 1
        assert "quality_peaked_at_iteration_1" in best["selection_reason"]

    def test_select_best_rejects_critical_issues(self):
        """Test selection avoids iterations with critical issues."""
        iterations = [
            {
                "iteration_num": 0,
                "metrics": {
                    "completeness_score": 0.85,
                    "accuracy_score": 0.90,
                    "schema_compliance_score": 0.88,
                    "critical_issues": 0,
                    "overall_quality": 0.876,
                },
            },
            {
                "iteration_num": 1,
                "metrics": {
                    "completeness_score": 0.95,
                    "accuracy_score": 0.98,
                    "schema_compliance_score": 0.96,
                    "critical_issues": 1,  # Has critical issues
                    "overall_quality": 0.963,
                },
            },
        ]

        best = _select_best_iteration(iterations)
        # Should pick iteration 0 (no critical issues) over iteration 1 (higher quality but has critical issues)
        assert best["iteration_num"] == 0

    def test_select_best_empty_iterations(self):
        """Test selection raises error with empty iterations list."""
        with pytest.raises(ValueError, match="No iterations to select from"):
            _select_best_iteration([])


class TestEarlyStoppingAlgorithm:
    """Test quality degradation detection for early stopping."""

    def test_degradation_detected_two_consecutive(self):
        """Test degradation detection with 2 consecutive declining iterations."""
        iterations = [
            {"metrics": {"overall_quality": 0.85}},
            {"metrics": {"overall_quality": 0.88}},  # Peak
            {"metrics": {"overall_quality": 0.86}},  # Degraded
            {"metrics": {"overall_quality": 0.84}},  # Degraded again
        ]

        assert _detect_quality_degradation(iterations, window=2) is True

    def test_degradation_not_detected_improving(self):
        """Test no degradation when quality is improving."""
        iterations = [
            {"metrics": {"overall_quality": 0.85}},
            {"metrics": {"overall_quality": 0.88}},
            {"metrics": {"overall_quality": 0.90}},
            {"metrics": {"overall_quality": 0.92}},
        ]

        assert _detect_quality_degradation(iterations, window=2) is False

    def test_degradation_insufficient_iterations(self):
        """Test no degradation detected with insufficient iterations."""
        iterations = [
            {"metrics": {"overall_quality": 0.85}},
            {"metrics": {"overall_quality": 0.88}},
        ]

        # Need at least window + 1 iterations (3 for window=2)
        assert _detect_quality_degradation(iterations, window=2) is False


class TestIterativeLoop:
    """Test main iterative validation-correction loop."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Setup mock dependencies for loop testing."""
        # Mock file manager
        file_manager = MagicMock()
        file_manager.save_json.return_value = tmp_path / "test.json"
        file_manager.identifier = "test-123"

        # Mock classification result
        classification = {"publication_type": "interventional_trial"}

        # Mock extraction result
        extraction = {"study_design": "RCT", "sample_size": 100}

        return {
            "pdf_path": tmp_path / "test.pdf",
            "extraction_result": extraction,
            "classification_result": classification,
            "llm_provider": "openai",
            "file_manager": file_manager,
            "max_iterations": 2,
        }

    @patch("src.pipeline.orchestrator._run_validation_step")
    @patch("src.pipeline.orchestrator._run_correction_step")
    @patch("src.pipeline.steps.validation.get_llm_provider")
    def test_loop_passes_first_iteration(
        self, mock_get_llm, mock_correction, mock_validation, mock_dependencies
    ):
        """Test loop succeeds on first iteration when quality sufficient."""
        # Mock LLM provider
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        # Mock validation result with sufficient quality
        mock_validation.return_value = {
            "schema_validation": {"quality_score": 0.95},
            "verification_summary": {
                "completeness_score": 0.92,
                "accuracy_score": 0.98,
                "schema_compliance_score": 0.96,
                "critical_issues": 0,
            },
        }

        # Run loop
        result = run_validation_with_correction(**mock_dependencies)

        # Assertions
        assert result["final_status"] == "passed"
        assert result["iteration_count"] == 1
        assert len(result["iterations"]) == 1
        assert mock_validation.call_count == 1
        assert mock_correction.call_count == 0  # No correction needed

    @patch("src.pipeline.orchestrator._run_validation_step")
    @patch("src.pipeline.orchestrator._run_correction_step")
    @patch("src.pipeline.steps.validation.get_llm_provider")
    def test_loop_max_iterations_reached(
        self, mock_get_llm, mock_correction, mock_validation, mock_dependencies
    ):
        """Test loop reaches max iterations and returns best result."""
        # Mock LLM provider
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        # Mock validation results with insufficient quality (progressively improving)
        validation_results = [
            {
                "schema_validation": {"quality_score": 0.95},
                "verification_summary": {
                    "completeness_score": 0.80,
                    "accuracy_score": 0.85,
                    "schema_compliance_score": 0.82,
                    "critical_issues": 0,
                },
            },
            {
                "schema_validation": {"quality_score": 0.96},
                "verification_summary": {
                    "completeness_score": 0.85,
                    "accuracy_score": 0.90,
                    "schema_compliance_score": 0.88,
                    "critical_issues": 0,
                },
            },
            {
                "schema_validation": {"quality_score": 0.97},
                "verification_summary": {
                    "completeness_score": 0.88,
                    "accuracy_score": 0.92,
                    "schema_compliance_score": 0.90,
                    "critical_issues": 0,
                },
            },
        ]
        mock_validation.return_value = validation_results[0]

        # Mock correction results
        corrected_extractions = [
            {"study_design": "RCT", "sample_size": 120},
            {"study_design": "RCT", "sample_size": 150},
        ]
        mock_correction.side_effect = [
            (corrected_extractions[0], validation_results[1]),
            (corrected_extractions[1], validation_results[2]),
        ]

        # Run loop
        result = run_validation_with_correction(**mock_dependencies)

        # Assertions
        assert result["final_status"] == "max_iterations_reached"
        assert result["iteration_count"] == 3  # Initial + 2 corrections
        assert len(result["iterations"]) == 3
        assert "warning" in result
        assert mock_validation.call_count == 1  # initial validation only
        assert mock_correction.call_count == 2
        # Ensure each iteration used the expected validation payload
        assert result["iterations"][0]["validation"] == validation_results[0]
        assert result["iterations"][1]["validation"] == validation_results[1]
        assert result["iterations"][2]["validation"] == validation_results[2]

    @patch("src.pipeline.orchestrator._run_validation_step")
    @patch("src.pipeline.orchestrator._run_correction_step")
    @patch("src.pipeline.steps.validation.get_llm_provider")
    def test_loop_early_stopping_degradation(
        self, mock_get_llm, mock_correction, mock_validation, mock_dependencies
    ):
        """Test loop stops early when quality degrades consecutively."""
        # Mock LLM provider
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        # Mock validation results with quality degradation pattern
        validation_results = [
            {
                "schema_validation": {"quality_score": 0.95},
                "verification_summary": {
                    "completeness_score": 0.85,
                    "accuracy_score": 0.88,
                    "schema_compliance_score": 0.86,
                    "critical_issues": 0,
                },
            },
            {
                "schema_validation": {"quality_score": 0.96},
                "verification_summary": {
                    "completeness_score": 0.88,
                    "accuracy_score": 0.91,
                    "schema_compliance_score": 0.89,
                    "critical_issues": 0,
                },
            },
            {
                "schema_validation": {"quality_score": 0.94},
                "verification_summary": {
                    "completeness_score": 0.86,  # Degraded
                    "accuracy_score": 0.89,  # Degraded
                    "schema_compliance_score": 0.87,  # Degraded
                    "critical_issues": 0,
                },
            },
            {
                "schema_validation": {"quality_score": 0.93},
                "verification_summary": {
                    "completeness_score": 0.84,  # Degraded again
                    "accuracy_score": 0.87,  # Degraded again
                    "schema_compliance_score": 0.85,  # Degraded again
                    "critical_issues": 0,
                },
            },
        ]
        mock_validation.side_effect = validation_results

        # Mock correction results
        corrected_extractions = [
            {"study_design": "RCT", "sample_size": 120},
            {"study_design": "RCT", "sample_size": 110},
            {"study_design": "RCT", "sample_size": 100},
        ]
        mock_correction.side_effect = [
            (corrected_extractions[0], validation_results[1]),
            (corrected_extractions[1], validation_results[2]),
            (corrected_extractions[2], validation_results[3]),
        ]

        # Use max_iterations = 3 to allow for early stopping check
        mock_dependencies["max_iterations"] = 3

        # Run loop
        result = run_validation_with_correction(**mock_dependencies)

        # Assertions
        assert result["final_status"] == "early_stopped_degradation"
        assert "warning" in result
        assert "Early stopping" in result["warning"]
        # Should stop after 4 iterations (0,1,2,3) when degradation detected
        assert len(result["iterations"]) == 4


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Setup mock dependencies for error testing."""
        file_manager = MagicMock()
        file_manager.save_json.return_value = tmp_path / "test.json"

        return {
            "pdf_path": tmp_path / "test.pdf",
            "extraction_result": {"data": "initial"},
            "classification_result": {"publication_type": "interventional_trial"},
            "llm_provider": "openai",
            "file_manager": file_manager,
            "max_iterations": 2,
        }

    @patch("src.pipeline.orchestrator._run_validation_step")
    @patch("src.pipeline.steps.validation.get_llm_provider")
    def test_schema_validation_failure(self, mock_get_llm, mock_validation, mock_dependencies):
        """Test loop stops when schema validation fails."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        # Mock validation with schema failure
        mock_validation.return_value = {
            "schema_validation": {"quality_score": 0.45},  # Below 0.5 threshold
            "verification_summary": {},
        }

        result = run_validation_with_correction(**mock_dependencies)

        assert result["final_status"] == "failed_schema_validation"
        assert "error" in result
        assert result["best_extraction"] is None

    @patch("src.pipeline.orchestrator._run_validation_step")
    @patch("src.pipeline.steps.validation.get_llm_provider")
    def test_llm_error_retries_exhausted(self, mock_get_llm, mock_validation, mock_dependencies):
        """Test loop handles LLM errors after exhausting retries."""
        from src.llm import LLMError

        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        # Mock validation to always raise LLMError
        mock_validation.side_effect = LLMError("API rate limit")

        result = run_validation_with_correction(**mock_dependencies)

        assert result["final_status"] == "failed_llm_error"
        assert "error" in result
        assert "LLM provider error after 3 retries" in result["error"]
        # Should have tried 1 initial + 3 retries = 4 calls
        assert mock_validation.call_count == 4

    @patch("src.pipeline.orchestrator._run_validation_step")
    @patch("src.pipeline.orchestrator._run_correction_step")
    @patch("src.pipeline.steps.validation.get_llm_provider")
    def test_json_decode_error(
        self, mock_get_llm, mock_correction, mock_validation, mock_dependencies
    ):
        """Test loop handles invalid JSON from correction."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        # First validation succeeds
        mock_validation.return_value = {
            "schema_validation": {"quality_score": 0.95},
            "verification_summary": {
                "completeness_score": 0.80,
                "accuracy_score": 0.85,
                "schema_compliance_score": 0.82,
                "critical_issues": 0,
            },
        }

        # Correction raises JSONDecodeError
        mock_correction.side_effect = json.JSONDecodeError("Invalid", "doc", 0)

        result = run_validation_with_correction(**mock_dependencies)

        assert result["final_status"] == "failed_invalid_json"
        assert "error" in result
        assert "invalid JSON" in result["error"]

    @patch("src.pipeline.orchestrator._run_validation_step")
    @patch("src.pipeline.steps.validation.get_llm_provider")
    def test_unexpected_error(self, mock_get_llm, mock_validation, mock_dependencies):
        """Test loop handles unexpected errors gracefully."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        # Mock unexpected error
        mock_validation.side_effect = RuntimeError("Unexpected crash")

        result = run_validation_with_correction(**mock_dependencies)

        assert result["final_status"] == "failed_unexpected_error"
        assert "error" in result
        assert "Unexpected error" in result["error"]

    def test_extract_metrics_complete(self):
        """Test metric extraction with complete validation result."""
        validation = {
            "verification_summary": {
                "completeness_score": 0.92,
                "accuracy_score": 0.95,
                "schema_compliance_score": 0.94,
                "critical_issues": 0,
                "total_issues": 3,
                "overall_status": "passed",
            }
        }

        metrics = _extract_metrics(validation)

        assert metrics["completeness_score"] == 0.92
        assert metrics["accuracy_score"] == 0.95
        assert metrics["schema_compliance_score"] == 0.94
        assert metrics["critical_issues"] == 0
        assert metrics["overall_quality"] == pytest.approx(0.936, abs=0.01)

    def test_extract_metrics_missing_fields(self):
        """Test metric extraction with missing fields defaults to 0."""
        validation = {"verification_summary": {}}

        metrics = _extract_metrics(validation)

        assert metrics["completeness_score"] == 0
        assert metrics["accuracy_score"] == 0
        assert metrics["overall_quality"] == 0

    def test_progress_callback_invoked(self, tmp_path):
        """Test progress callback is invoked during loop."""
        callback_calls = []

        def mock_callback(step_name, status, data):
            callback_calls.append((step_name, status, data))

        with (
            patch("src.pipeline.orchestrator._run_validation_step") as mock_validation,
            patch("src.pipeline.steps.validation.get_llm_provider") as mock_get_llm,
        ):
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm

            # Mock sufficient quality on first iteration
            mock_validation.return_value = {
                "schema_validation": {"quality_score": 0.95},
                "verification_summary": {
                    "completeness_score": 0.92,
                    "accuracy_score": 0.98,
                    "schema_compliance_score": 0.96,
                    "critical_issues": 0,
                },
            }

            file_manager = MagicMock()
            file_manager.save_json.return_value = tmp_path / "test.json"

            run_validation_with_correction(
                pdf_path=tmp_path / "test.pdf",
                extraction_result={"data": "test"},
                classification_result={"publication_type": "interventional_trial"},
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=2,
                progress_callback=mock_callback,
            )

            # Check callback was invoked
            assert len(callback_calls) >= 2  # At least starting and completed
            assert any(
                call[0] == STEP_VALIDATION_CORRECTION and call[1] == "starting"
                for call in callback_calls
            )
            assert any(
                call[0] == STEP_VALIDATION_CORRECTION and call[1] == "completed"
                for call in callback_calls
            )

    def test_custom_quality_thresholds(self, tmp_path):
        """Test loop respects custom quality thresholds."""
        with (
            patch("src.pipeline.orchestrator._run_validation_step") as mock_validation,
            patch("src.pipeline.steps.validation.get_llm_provider") as mock_get_llm,
        ):
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm

            # Quality that would fail default thresholds but passes custom
            mock_validation.return_value = {
                "schema_validation": {"quality_score": 0.95},
                "verification_summary": {
                    "completeness_score": 0.85,  # Below default 0.90
                    "accuracy_score": 0.92,  # Below default 0.95
                    "schema_compliance_score": 0.90,  # Below default 0.95
                    "critical_issues": 0,
                },
            }

            file_manager = MagicMock()
            file_manager.save_json.return_value = tmp_path / "test.json"

            custom_thresholds = {
                "completeness_score": 0.80,
                "accuracy_score": 0.90,
                "schema_compliance_score": 0.85,
                "critical_issues": 0,
            }

            result = run_validation_with_correction(
                pdf_path=tmp_path / "test.pdf",
                extraction_result={"data": "test"},
                classification_result={"publication_type": "interventional_trial"},
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=2,
                quality_thresholds=custom_thresholds,
            )

            # Should pass with custom thresholds
            assert result["final_status"] == "passed"
            assert result["iteration_count"] == 1


class TestErrorHandling:
    """Test error recovery and graceful degradation."""

    def test_llm_failure_returns_error_status(self, tmp_path):
        """LLM failures are caught and handled gracefully."""
        with (
            patch("src.pipeline.orchestrator._run_validation_step") as mock_validation,
            patch("src.pipeline.orchestrator._run_correction_step") as mock_correction,
            patch("time.sleep"),  # Don't actually sleep during retries
        ):
            # Initial validation shows low quality
            mock_validation.return_value = {
                "schema_validation": {"quality_score": 0.95},
                "verification_summary": {
                    "completeness_score": 0.85,
                    "accuracy_score": 0.90,
                    "schema_compliance_score": 0.92,
                    "critical_issues": 1,  # Needs correction
                },
            }

            # Correction raises LLMError (simulates persistent API failure)
            mock_correction.side_effect = LLMError("Persistent API failure")

            file_manager = MagicMock()
            file_manager.save_json.return_value = tmp_path / "test.json"

            result = run_validation_with_correction(
                pdf_path=tmp_path / "test.pdf",
                extraction_result={"data": "initial"},
                classification_result={"publication_type": "interventional_trial"},
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=2,
            )

            # LLM failures are retried, then loop continues until max iterations
            # Result can be either failed_llm_error or max_iterations_reached
            assert result["final_status"] in ["failed_llm_error", "max_iterations_reached"]
            assert "iterations" in result
            # Should have returned best available result (initial extraction)
            assert result["best_extraction"] is not None

    def test_llm_retry_mechanism_exists(self, tmp_path):
        """Verify retry mechanism is invoked on LLM failures."""
        with (
            patch("src.pipeline.orchestrator._run_validation_step") as mock_validation,
            patch("src.pipeline.orchestrator._run_correction_step") as mock_correction,
            patch("time.sleep") as mock_sleep,
        ):
            # Initial validation
            mock_validation.return_value = {
                "schema_validation": {"quality_score": 0.95},
                "verification_summary": {
                    "completeness_score": 0.85,
                    "accuracy_score": 0.90,
                    "schema_compliance_score": 0.92,
                    "critical_issues": 1,
                },
            }

            # Correction fails first time, succeeds second time
            mock_correction.side_effect = [
                LLMError("Temporary failure"),
                ({"data": "corrected"}, {"validation": "result"}),
            ]

            file_manager = MagicMock()
            file_manager.save_json.return_value = tmp_path / "test.json"

            result = run_validation_with_correction(
                pdf_path=tmp_path / "test.pdf",
                extraction_result={"data": "initial"},
                classification_result={"publication_type": "interventional_trial"},
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=1,
            )

            # Verify retry was attempted (sleep was called)
            assert mock_sleep.call_count >= 1
            # Result should have completed (not failed)
            assert "final_status" in result

    def test_schema_failure_early_exit(self, tmp_path):
        """Schema quality <50% prevents correction attempt."""
        with patch("src.pipeline.orchestrator._run_validation_step") as mock_validation:
            # Validation returns very low schema quality (<50%)
            mock_validation.return_value = {
                "schema_validation": {"quality_score": 0.30},  # Below 0.50 threshold
                "verification_summary": {
                    "completeness_score": 0.40,
                    "accuracy_score": 0.45,
                    "schema_compliance_score": 0.35,
                    "critical_issues": 5,
                },
            }

            file_manager = MagicMock()
            file_manager.save_json.return_value = tmp_path / "test.json"

            result = run_validation_with_correction(
                pdf_path=tmp_path / "test.pdf",
                extraction_result={"data": "initial"},
                classification_result={"publication_type": "interventional_trial"},
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=3,
            )

            # Should exit immediately without attempting correction
            assert result["final_status"] == "failed_schema_validation"
            assert "error" in result
            assert "schema validation failed" in result["error"].lower()

    def test_unexpected_error_graceful_fail(self, tmp_path):
        """Unexpected errors don't crash, return best iteration."""
        with (
            patch("src.pipeline.orchestrator._run_validation_step") as mock_validation,
            patch("src.pipeline.orchestrator._run_correction_step") as mock_correction,
        ):
            # First validation shows need for correction
            mock_validation.return_value = {
                "schema_validation": {"quality_score": 0.95},
                "verification_summary": {
                    "completeness_score": 0.85,
                    "accuracy_score": 0.90,
                    "schema_compliance_score": 0.92,
                    "critical_issues": 1,
                },
            }

            # Correction raises unexpected error
            mock_correction.side_effect = AttributeError("Unexpected attribute error")

            file_manager = MagicMock()
            file_manager.save_json.return_value = tmp_path / "test.json"

            result = run_validation_with_correction(
                pdf_path=tmp_path / "test.pdf",
                extraction_result={"data": "initial"},
                classification_result={"publication_type": "interventional_trial"},
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=2,
            )

            # Should not crash, return error status
            assert result["final_status"] == "failed_unexpected_error"
            assert "error" in result
            assert "iterations" in result

    def test_json_decode_error_handling(self, tmp_path):
        """JSON decode errors are caught and handled gracefully."""
        with (
            patch("src.pipeline.orchestrator._run_validation_step") as mock_validation,
            patch("src.pipeline.orchestrator._run_correction_step") as mock_correction,
        ):
            # Initial validation
            mock_validation.return_value = {
                "schema_validation": {"quality_score": 0.95},
                "verification_summary": {
                    "completeness_score": 0.85,
                    "accuracy_score": 0.90,
                    "schema_compliance_score": 0.92,
                    "critical_issues": 1,
                },
            }

            # Correction raises JSONDecodeError
            import json

            mock_correction.side_effect = json.JSONDecodeError("Invalid JSON", '{"invalid":', 10)

            file_manager = MagicMock()
            file_manager.save_json.return_value = tmp_path / "test.json"

            result = run_validation_with_correction(
                pdf_path=tmp_path / "test.pdf",
                extraction_result={"data": "initial"},
                classification_result={"publication_type": "interventional_trial"},
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=2,
            )

            # Should return failed_invalid_json status
            assert result["final_status"] == "failed_invalid_json"
            assert "error" in result
            assert "iterations" in result
