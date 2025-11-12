# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Tests for backward compatibility of iterative validation-correction feature.

Ensures that:
1. Old validation and correction steps still work
2. New validation_correction step is available
3. ALL_PIPELINE_STEPS contains the new step
4. Old steps are NOT in the default pipeline
"""

from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.orchestrator import (
    ALL_PIPELINE_STEPS,
    STEP_APPRAISAL,
    STEP_CLASSIFICATION,
    STEP_CORRECTION,
    STEP_EXTRACTION,
    STEP_VALIDATION,
    STEP_VALIDATION_CORRECTION,
    run_single_step,
)


class TestBackwardCompatibility:
    """Verify oude API blijft werken."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Create mock dependencies for run_single_step."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        # Create file manager mock
        file_manager = MagicMock()
        file_manager.save_json.return_value = tmp_path / "output.json"

        # Mock classification result
        classification_result = {
            "publication_type": "research_article",
            "metadata": {"title": "Test Article"},
        }

        # Mock extraction result
        extraction_result = {
            "data": {"test_field": "test_value"},
            "metadata": {},
        }

        # Mock validation result (failed)
        validation_result = {
            "verification_summary": {
                "overall_status": "failed",
                "completeness_score": 0.85,
                "accuracy_score": 0.90,
                "schema_compliance_score": 0.88,
                "critical_issues": 2,
            }
        }

        return {
            "pdf_path": pdf_path,
            "max_pages": None,
            "llm_provider": "openai",
            "file_manager": file_manager,
            "progress_callback": None,
            "previous_results": {
                STEP_CLASSIFICATION: classification_result,
                STEP_EXTRACTION: extraction_result,
                STEP_VALIDATION: validation_result,
            },
        }

    @patch("src.pipeline.orchestrator._run_validation_step")
    def test_old_validation_step_still_works(self, mock_validate, mock_dependencies):
        """STEP_VALIDATION moet nog steeds single validation run doen."""
        # Setup mock return value
        expected_result = {
            "verification_summary": {
                "overall_status": "passed",
                "completeness_score": 0.95,
            }
        }
        mock_validate.return_value = expected_result

        # Run old validation step
        result = run_single_step(
            step_name=STEP_VALIDATION,
            pdf_path=mock_dependencies["pdf_path"],
            max_pages=mock_dependencies["max_pages"],
            llm_provider=mock_dependencies["llm_provider"],
            file_manager=mock_dependencies["file_manager"],
            previous_results={
                STEP_CLASSIFICATION: mock_dependencies["previous_results"][STEP_CLASSIFICATION],
                STEP_EXTRACTION: mock_dependencies["previous_results"][STEP_EXTRACTION],
            },
        )

        # Should return validation result, NOT loop result
        assert "verification_summary" in result
        assert "iterations" not in result  # Old API doesn't have iterations
        assert result == expected_result

    @patch("src.pipeline.orchestrator._run_correction_step")
    def test_old_correction_step_still_works(self, mock_correct, mock_dependencies):
        """STEP_CORRECTION moet nog steeds single correction run doen."""
        # Setup mock return value
        corrected_extraction = {"data": {"corrected_field": "corrected_value"}}
        final_validation = {"verification_summary": {"overall_status": "passed"}}
        mock_correct.return_value = (corrected_extraction, final_validation)

        # Run old correction step
        result = run_single_step(
            step_name=STEP_CORRECTION,
            pdf_path=mock_dependencies["pdf_path"],
            max_pages=mock_dependencies["max_pages"],
            llm_provider=mock_dependencies["llm_provider"],
            file_manager=mock_dependencies["file_manager"],
            previous_results=mock_dependencies["previous_results"],
        )

        # Should return dict with both corrected extraction and validation
        assert "extraction_corrected" in result
        assert "validation_corrected" in result
        assert result["extraction_corrected"] == corrected_extraction
        assert result["validation_corrected"] == final_validation

    @patch("src.pipeline.orchestrator.run_validation_with_correction")
    def test_new_combined_step_returns_loop_result(self, mock_loop, mock_dependencies):
        """STEP_VALIDATION_CORRECTION moet iterative loop result returnen."""
        # Setup mock return value
        expected_result = {
            "final_status": "passed",
            "iteration_count": 2,
            "best_extraction": {"data": {"best": "data"}},
            "best_validation": {"verification_summary": {"overall_status": "passed"}},
            "iterations": [
                {"iteration_num": 0, "metrics": {"overall_quality": 0.85}},
                {"iteration_num": 1, "metrics": {"overall_quality": 0.95}},
            ],
        }
        mock_loop.return_value = expected_result

        # Run new combined step
        result = run_single_step(
            step_name=STEP_VALIDATION_CORRECTION,
            pdf_path=mock_dependencies["pdf_path"],
            max_pages=mock_dependencies["max_pages"],
            llm_provider=mock_dependencies["llm_provider"],
            file_manager=mock_dependencies["file_manager"],
            previous_results={
                STEP_CLASSIFICATION: mock_dependencies["previous_results"][STEP_CLASSIFICATION],
                STEP_EXTRACTION: mock_dependencies["previous_results"][STEP_EXTRACTION],
            },
        )

        # Should return loop result with iterations
        assert "iterations" in result
        assert "final_status" in result
        assert "best_extraction" in result
        assert "best_validation" in result
        assert result == expected_result

    def test_all_pipeline_steps_includes_new_step(self):
        """ALL_PIPELINE_STEPS moet nieuwe step bevatten."""
        assert STEP_VALIDATION_CORRECTION in ALL_PIPELINE_STEPS

    def test_old_steps_not_in_default_pipeline(self):
        """STEP_VALIDATION en STEP_CORRECTION zijn alleen voor CLI backward compat."""
        # These are NOT in the default pipeline (alleen voor CLI)
        assert STEP_VALIDATION not in ALL_PIPELINE_STEPS
        assert STEP_CORRECTION not in ALL_PIPELINE_STEPS

    def test_new_step_replaces_old_steps_in_pipeline(self):
        """De nieuwe step vervangt validation+correction in default pipeline."""
        expected_steps = [
            STEP_CLASSIFICATION,
            STEP_EXTRACTION,
            STEP_VALIDATION_CORRECTION,
            STEP_APPRAISAL,
        ]
        assert ALL_PIPELINE_STEPS == expected_steps
