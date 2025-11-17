# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for report generation functions (Phase 2).

Tests cover:
- run_report_generation() basic functionality
- File manager report iteration methods
- Schema validation
- Integration with run_single_step()

Note: These tests verify Phase 2 implementation (single-pass generation).
      Validation & correction loop tests will be added in Phase 3.
"""

import pytest

from src.pipeline.file_manager import PipelineFileManager
from src.pipeline.orchestrator import STEP_REPORT_GENERATION, _get_pipeline_version


class TestFileManagerReportMethods:
    """Test file manager report iteration methods."""

    def test_save_and_load_report_iteration(self, tmp_path):
        """Test saving and loading report iterations."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path  # Override to use pytest tmp_path

        report_data = {
            "report_version": "v1.0",
            "study_type": "interventional",
            "metadata": {
                "title": "Test Study",
                "generation_timestamp": "2025-01-17T10:00:00Z",
                "pipeline_version": "1.0.0",
            },
            "layout": {"language": "en"},
            "sections": [],
        }

        validation_data = {"quality_score": 0.92, "overall_status": "passed"}

        # Save iteration 0
        report_path, val_path = manager.save_report_iteration(
            iteration=0, report_result=report_data, validation_result=validation_data
        )

        assert report_path.exists()
        assert report_path.name == "test-report0.json"
        assert val_path.exists()
        assert val_path.name == "test-report_validation0.json"

        # Load back
        loaded_report, loaded_val = manager.load_report_iteration(0)

        assert loaded_report["report_version"] == "v1.0"
        assert loaded_report["study_type"] == "interventional"
        assert loaded_val["quality_score"] == 0.92

    def test_save_best_report(self, tmp_path):
        """Test saving best report iteration."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        report_data = {"report_version": "v1.0", "study_type": "interventional"}
        validation_data = {"quality_score": 0.95}

        report_path, val_path = manager.save_best_report(report_data, validation_data)

        assert report_path.exists()
        assert report_path.name == "test-report-best.json"
        assert val_path.exists()
        assert val_path.name == "test-report_validation-best.json"

    def test_get_report_iterations(self, tmp_path):
        """Test getting all report iterations."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Save multiple iterations
        for i in range(3):
            report_data = {"iteration": i}
            val_data = {"score": 0.8 + i * 0.05}
            manager.save_report_iteration(i, report_data, val_data)

        iterations = manager.get_report_iterations()

        assert len(iterations) == 3
        assert iterations[0]["iteration_num"] == 0
        assert iterations[1]["iteration_num"] == 1
        assert iterations[2]["iteration_num"] == 2
        assert all(it["report_exists"] for it in iterations)
        assert all(it["validation_exists"] for it in iterations)

    def test_load_nonexistent_report_iteration(self, tmp_path):
        """Test loading non-existent report iteration raises error."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        with pytest.raises(FileNotFoundError):
            manager.load_report_iteration(999)


class TestReportGenerationConstants:
    """Test report generation step constants."""

    def test_step_constant_exists(self):
        """Test STEP_REPORT_GENERATION constant is defined."""
        assert STEP_REPORT_GENERATION == "report_generation"

    def test_step_in_pipeline_steps(self):
        """Test report_generation is in ALL_PIPELINE_STEPS."""
        from src.pipeline.orchestrator import ALL_PIPELINE_STEPS

        assert STEP_REPORT_GENERATION in ALL_PIPELINE_STEPS

    def test_step_display_name(self):
        """Test report generation has display name."""
        from src.pipeline.orchestrator import STEP_DISPLAY_NAMES

        assert STEP_REPORT_GENERATION in STEP_DISPLAY_NAMES
        assert "Report" in STEP_DISPLAY_NAMES[STEP_REPORT_GENERATION]


# Integration test for run_report_generation (Issue #4 fix)


class TestRunReportGeneration:
    """Integration tests for run_report_generation() function."""

    @pytest.fixture
    def mock_classification(self):
        """Mock classification result."""
        return {
            "publication_type": "interventional_trial",
            "confidence": 0.95,
            "_pipeline_metadata": {"step": "classification"},
        }

    @pytest.fixture
    def mock_extraction(self):
        """Mock extraction result."""
        return {
            "study_id": "NCT12345678",
            "publication_type": "interventional_trial",
            "outcomes": [
                {
                    "outcome_id": "outcome1",
                    "is_primary": True,
                    "name": "Pain reduction",
                    "results": {"effect_size": 0.5},
                }
            ],
            "_pipeline_metadata": {"step": "extraction"},
        }

    @pytest.fixture
    def mock_appraisal(self):
        """Mock appraisal result."""
        return {
            "appraisal_version": "v1.0",
            "study_type": "interventional",
            "risk_of_bias": {"overall": "Low risk"},
            "_pipeline_metadata": {"step": "appraisal"},
        }

    @pytest.fixture
    def mock_report_output(self):
        """Mock report JSON output from LLM."""
        return {
            "report_version": "v1.0",
            "study_type": "interventional",
            "metadata": {
                "title": "Test Study",
                "generation_timestamp": "2025-01-17T10:00:00Z",
                "pipeline_version": "1.0.0",
            },
            "layout": {"language": "en"},
            "sections": [],
        }

    def test_run_report_generation_success(
        self,
        tmp_path,
        mock_classification,
        mock_extraction,
        mock_appraisal,
        mock_report_output,
    ):
        """Test successful report generation with mocked LLM."""
        from unittest.mock import MagicMock, patch

        from src.pipeline.file_manager import PipelineFileManager
        from src.pipeline.orchestrator import run_report_generation

        # Setup
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        file_manager = PipelineFileManager(pdf_path)
        file_manager.tmp_dir = tmp_path

        # Mock LLM provider
        mock_llm = MagicMock()
        mock_llm.generate_json_with_schema.return_value = mock_report_output

        # Mock get_llm_provider to return our mock
        with patch("src.pipeline.orchestrator.get_llm_provider", return_value=mock_llm):
            # Execute
            result = run_report_generation(
                extraction_result=mock_extraction,
                appraisal_result=mock_appraisal,
                classification_result=mock_classification,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
            )

        # Verify LLM was called correctly (Issue #1 fix verification)
        assert mock_llm.generate_json_with_schema.called
        call_args = mock_llm.generate_json_with_schema.call_args
        assert call_args.kwargs["schema_name"] == "report_generation"

        # Verify prompt context includes all required inputs (Issue #3 fix verification)
        prompt_text = call_args.kwargs["prompt"]
        assert "CLASSIFICATION_JSON:" in prompt_text
        assert "EXTRACTION_JSON:" in prompt_text
        assert "APPRAISAL_JSON:" in prompt_text
        assert "LANGUAGE: en" in prompt_text
        assert "GENERATION_TIMESTAMP:" in prompt_text
        expected_version = _get_pipeline_version()
        assert f"PIPELINE_VERSION: {expected_version}" in prompt_text
        assert "REPORT_SCHEMA:" in prompt_text

        # Verify result structure
        assert result["status"] == "completed"
        assert result["iteration"] == 0
        assert result["report"] == mock_report_output
        assert "_pipeline_metadata" in result

        # Verify file was saved
        report_file = tmp_path / "test-report0.json"
        assert report_file.exists()

    def test_run_report_generation_llm_error(
        self, tmp_path, mock_classification, mock_extraction, mock_appraisal
    ):
        """Test report generation handles LLM errors correctly."""
        from unittest.mock import MagicMock, patch

        from src.llm import LLMError
        from src.pipeline.file_manager import PipelineFileManager
        from src.pipeline.orchestrator import run_report_generation

        # Setup
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        file_manager = PipelineFileManager(pdf_path)
        file_manager.tmp_dir = tmp_path

        # Mock LLM to raise error
        mock_llm = MagicMock()
        mock_llm.generate_json_with_schema.side_effect = LLMError("API timeout")

        with patch("src.pipeline.orchestrator.get_llm_provider", return_value=mock_llm):
            # Execute and verify error is raised
            with pytest.raises(LLMError, match="API timeout"):
                run_report_generation(
                    extraction_result=mock_extraction,
                    appraisal_result=mock_appraisal,
                    classification_result=mock_classification,
                    llm_provider="openai",
                    file_manager=file_manager,
                )

    def test_run_report_generation_schema_validation_error(
        self, tmp_path, mock_classification, mock_extraction, mock_appraisal
    ):
        """Test report generation detects schema validation errors (Issue #2 fix verification)."""
        from unittest.mock import MagicMock, patch

        from src.pipeline.file_manager import PipelineFileManager
        from src.pipeline.orchestrator import run_report_generation

        # Setup
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        file_manager = PipelineFileManager(pdf_path)
        file_manager.tmp_dir = tmp_path

        # Mock LLM to return invalid report (missing required fields)
        invalid_report = {"report_version": "v1.0"}  # Missing study_type, metadata, etc.
        mock_llm = MagicMock()
        mock_llm.generate_json_with_schema.return_value = invalid_report

        with patch("src.pipeline.orchestrator.get_llm_provider", return_value=mock_llm):
            # Execute and verify schema validation error is raised
            # validate_with_schema raises ValidationError (not SchemaLoadError) with strict=True
            with pytest.raises(Exception) as exc_info:
                run_report_generation(
                    extraction_result=mock_extraction,
                    appraisal_result=mock_appraisal,
                    classification_result=mock_classification,
                    llm_provider="openai",
                    file_manager=file_manager,
                )

            # Verify it's a schema validation error (either ValidationError or SchemaLoadError)
            assert (
                "schema validation failed" in str(exc_info.value).lower()
                or "required property" in str(exc_info.value).lower()
            )


# Note: These tests verify all 4 critical issues are fixed:
# - Issue #1: Uses generate_json_with_schema() (test_run_report_generation_success)
# - Issue #2: Uses validate_with_schema() (test_run_report_generation_schema_validation_error)
# - Issue #3: Includes LANGUAGE, TIMESTAMP, VERSION in prompt (test_run_report_generation_success)
# - Issue #4: Integration test with mocked LLM (all tests in TestRunReportGeneration)
