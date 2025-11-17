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
from src.pipeline.orchestrator import STEP_REPORT_GENERATION


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


# Note: Full integration tests with LLM mocking will be added separately
# These basic tests verify the structure and file management functionality
