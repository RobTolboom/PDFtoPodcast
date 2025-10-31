# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Integration tests for iterative validation-correction loop.

Tests the complete validation-correction workflow to ensure:
1. correction_notes is added during correction
2. correction_notes is properly stripped from final results
3. No metadata leaks into final extraction data
"""

from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.file_manager import PipelineFileManager
from src.pipeline.orchestrator import run_validation_with_correction

pytestmark = pytest.mark.integration


class TestIterativeValidationCorrection:
    """Integration tests for validation-correction loop metadata handling."""

    @pytest.fixture
    def mock_extraction(self):
        """Mock extraction data with incomplete fields."""
        return {
            "publication_type": "interventional_trial",
            "metadata": {
                "title": "Test Study",
                "authors": ["Smith J"],
            },
            "study_design": {
                "design_label": "RCT",
                # Missing some fields to trigger quality issues
            },
            "outcomes": [],  # Empty outcomes list
        }

    @pytest.fixture
    def mock_validation_low_quality(self):
        """Mock validation result with low quality scores."""
        return {
            "overall_quality": 0.70,
            "completeness_score": 0.75,
            "accuracy_score": 0.80,
            "schema_compliance_score": 0.90,
            "critical_issues": 0,
            "missing_fields": ["outcomes"],
            "issues": [
                {
                    "severity": "warning",
                    "message": "Outcomes section is incomplete",
                    "field": "outcomes",
                }
            ],
        }

    @pytest.fixture
    def mock_validation_high_quality(self):
        """Mock validation result with high quality scores (passes thresholds)."""
        return {
            "overall_quality": 0.96,
            "completeness_score": 0.95,
            "accuracy_score": 0.97,
            "schema_compliance_score": 0.98,
            "critical_issues": 0,
            "missing_fields": [],
            "issues": [],
        }

    @pytest.fixture
    def mock_corrected_extraction(self):
        """Mock corrected extraction with correction_notes added."""
        return {
            "publication_type": "interventional_trial",
            "metadata": {
                "title": "Test Study",
                "authors": ["Smith J"],
            },
            "study_design": {
                "design_label": "RCT",
                "design_details": "Randomized controlled trial",
            },
            "outcomes": [
                {
                    "outcome_id": "o1",
                    "label": "Primary outcome",
                }
            ],
            # This field should be stripped before final return
            "correction_notes": "Added missing outcomes and study design details",
        }

    @pytest.fixture
    def file_manager(self, tmp_path):
        """Create a temporary file manager for testing."""
        return PipelineFileManager(
            pdf_path=str(tmp_path / "test.pdf"),
            output_dir=str(tmp_path / "output"),
        )

    @patch("src.pipeline.orchestrator.run_correction")
    @patch("src.pipeline.orchestrator.run_validation")
    def test_correction_notes_stripped_from_final_result(
        self,
        mock_run_validation,
        mock_run_correction,
        mock_extraction,
        mock_validation_low_quality,
        mock_validation_high_quality,
        mock_corrected_extraction,
        file_manager,
    ):
        """
        Test that correction_notes is properly stripped from final results.

        Workflow:
        1. Initial extraction has low quality
        2. Correction adds correction_notes field
        3. After correction, validation passes
        4. Final result should NOT contain correction_notes
        """
        # Setup mocks
        # First validation: low quality (triggers correction)
        # Second validation: high quality (passes thresholds)
        mock_run_validation.side_effect = [
            mock_validation_low_quality,
            mock_validation_high_quality,
        ]

        # Correction returns extraction WITH correction_notes
        mock_run_correction.return_value = mock_corrected_extraction

        # Mock LLM provider
        mock_llm = MagicMock()
        mock_llm.__class__.__name__ = "OpenAIProvider"

        # Run validation-correction loop
        result = run_validation_with_correction(
            extraction_data=mock_extraction,
            publication_type="interventional_trial",
            llm_provider=mock_llm,
            file_manager=file_manager,
            max_iterations=3,
        )

        # Verify correction_notes is NOT in final result
        assert (
            "correction_notes" not in result["best_extraction"]
        ), "correction_notes should be stripped from best_extraction"

        # Verify other fields are present
        assert result["best_extraction"]["publication_type"] == "interventional_trial"
        assert "outcomes" in result["best_extraction"]
        assert len(result["best_extraction"]["outcomes"]) == 1

        # Verify iterations were tracked
        assert result["total_iterations"] >= 1
        assert result["quality_sufficient"] is True

    @patch("src.pipeline.orchestrator.run_correction")
    @patch("src.pipeline.orchestrator.run_validation")
    def test_correction_notes_stripped_from_all_iterations(
        self,
        mock_run_validation,
        mock_run_correction,
        mock_extraction,
        mock_validation_low_quality,
        mock_validation_high_quality,
        mock_corrected_extraction,
        file_manager,
    ):
        """
        Test that correction_notes is stripped from all stored iterations.

        This ensures that iterations[] array doesn't contain correction_notes
        in any iteration's extraction data.
        """
        # Setup: run 2 iterations before passing
        mock_run_validation.side_effect = [
            mock_validation_low_quality,  # Iteration 0 validation
            mock_validation_low_quality,  # Iteration 1 post-correction validation
            mock_validation_high_quality,  # Iteration 2 post-correction validation (passes)
        ]

        mock_run_correction.return_value = mock_corrected_extraction

        mock_llm = MagicMock()
        mock_llm.__class__.__name__ = "OpenAIProvider"

        result = run_validation_with_correction(
            extraction_data=mock_extraction,
            publication_type="interventional_trial",
            llm_provider=mock_llm,
            file_manager=file_manager,
            max_iterations=3,
        )

        # Check that NONE of the stored iterations contain correction_notes
        for i, iteration in enumerate(result["iterations"]):
            assert (
                "correction_notes" not in iteration["extraction"]
            ), f"Iteration {i} extraction should not contain correction_notes"

    @patch("src.pipeline.orchestrator.run_correction")
    @patch("src.pipeline.orchestrator.run_validation")
    def test_metadata_fields_stripped_from_final_result(
        self,
        mock_run_validation,
        mock_run_correction,
        mock_extraction,
        mock_validation_high_quality,
        file_manager,
    ):
        """
        Test that all metadata fields are stripped from final results.

        Ensures usage, _metadata, _pipeline_metadata, and correction_notes
        are all removed before returning final results.
        """
        # Add metadata to corrected extraction
        corrected_with_metadata = {
            "publication_type": "interventional_trial",
            "metadata": {"title": "Test Study"},
            "study_design": {"design_label": "RCT"},
            "outcomes": [{"outcome_id": "o1", "label": "Primary"}],
            # All these should be stripped
            "usage": {"input_tokens": 1000, "output_tokens": 500},
            "_metadata": {"response_id": "resp_123", "model": "gpt-5"},
            "_pipeline_metadata": {"step": "correction", "timestamp": "2025-10-31T10:00:00Z"},
            "correction_notes": "Corrections applied",
        }

        mock_run_validation.return_value = mock_validation_high_quality
        mock_run_correction.return_value = corrected_with_metadata

        mock_llm = MagicMock()
        mock_llm.__class__.__name__ = "OpenAIProvider"

        result = run_validation_with_correction(
            extraction_data=mock_extraction,
            publication_type="interventional_trial",
            llm_provider=mock_llm,
            file_manager=file_manager,
            max_iterations=3,
        )

        # Verify ALL metadata fields are stripped from best_extraction
        best = result["best_extraction"]
        assert "usage" not in best, "usage should be stripped"
        assert "_metadata" not in best, "_metadata should be stripped"
        assert "_pipeline_metadata" not in best, "_pipeline_metadata should be stripped"
        assert "correction_notes" not in best, "correction_notes should be stripped"

        # Verify schema fields are preserved
        assert "publication_type" in best
        assert "metadata" in best
        assert "study_design" in best
        assert "outcomes" in best
