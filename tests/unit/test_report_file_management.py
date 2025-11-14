# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for report-specific file management methods.

Tests the report iteration saving/loading methods in PipelineFileManager:
- save_report_iteration()
- load_report_iteration()
- save_best_report()
- get_report_iterations()
- save_report_pdf()
"""

import json

import pytest

from src.pipeline.file_manager import PipelineFileManager

pytestmark = pytest.mark.unit


class TestReportIterationManagement:
    """Test report iteration save/load methods."""

    def test_save_report_iteration_creates_files(self, tmp_path):
        """Test that save_report_iteration creates correctly named files."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        report = {"metadata": {"title": "Test Report"}, "sections": []}
        validation = {"validation_summary": {"quality_score": 0.90}}

        report_path, validation_path = manager.save_report_iteration(1, report, validation)

        assert report_path == tmp_path / "study-report1.json"
        assert validation_path == tmp_path / "study-report_validation1.json"
        assert report_path.exists()
        assert validation_path.exists()

    def test_save_report_iteration_without_validation(self, tmp_path):
        """Test saving report iteration without validation."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        report = {"metadata": {"title": "Test Report"}}

        report_path, validation_path = manager.save_report_iteration(1, report, None)

        assert report_path.exists()
        assert validation_path is None

    def test_save_report_iteration_content_correct(self, tmp_path):
        """Test that saved report content is correct."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        report = {"metadata": {"title": "Test"}, "layout": {"language": "nl"}}
        validation = {"validation_summary": {"quality_score": 0.92}}

        report_path, validation_path = manager.save_report_iteration(2, report, validation)

        # Verify report content
        with open(report_path) as f:
            loaded_report = json.load(f)
        assert loaded_report == report

        # Verify validation content
        with open(validation_path) as f:
            loaded_validation = json.load(f)
        assert loaded_validation == validation

    def test_load_report_iteration_returns_both_files(self, tmp_path):
        """Test that load_report_iteration loads both report and validation."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Save first
        report = {"data": "test_report"}
        validation = {"quality_score": 0.88}
        manager.save_report_iteration(1, report, validation)

        # Load back
        loaded_report, loaded_validation = manager.load_report_iteration(1)

        assert loaded_report == report
        assert loaded_validation == validation

    def test_load_report_iteration_without_validation(self, tmp_path):
        """Test loading report iteration when validation doesn't exist."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Save report without validation
        report = {"data": "test"}
        manager.save_report_iteration(1, report, None)

        # Load back
        loaded_report, loaded_validation = manager.load_report_iteration(1)

        assert loaded_report == report
        assert loaded_validation is None

    def test_load_report_iteration_nonexistent_returns_none(self, tmp_path):
        """Test loading non-existent iteration returns None for both."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        loaded_report, loaded_validation = manager.load_report_iteration(99)

        assert loaded_report is None
        assert loaded_validation is None


class TestBestReportManagement:
    """Test best report save/load functionality."""

    def test_save_best_report_creates_files(self, tmp_path):
        """Test that save_best_report creates correctly named files."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        report = {"metadata": {"title": "Best Report"}}
        validation = {"validation_summary": {"quality_score": 0.95}}

        report_path, validation_path = manager.save_best_report(report, validation)

        assert report_path == tmp_path / "study-report-best.json"
        assert validation_path == tmp_path / "study-report_validation-best.json"
        assert report_path.exists()
        assert validation_path.exists()

    def test_save_best_report_content_correct(self, tmp_path):
        """Test that best report content is saved correctly."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        report = {"metadata": {"final": True}, "sections": [{"id": "s1"}]}
        validation = {"validation_summary": {"quality_score": 0.97, "status": "passed"}}

        report_path, validation_path = manager.save_best_report(report, validation)

        # Verify content
        with open(report_path) as f:
            loaded = json.load(f)
        assert loaded == report
        assert loaded["metadata"]["final"] is True

        with open(validation_path) as f:
            loaded_val = json.load(f)
        assert loaded_val["validation_summary"]["quality_score"] == 0.97


class TestReportIterationsListing:
    """Test get_report_iterations method."""

    def test_get_report_iterations_empty_when_none_exist(self, tmp_path):
        """Test get_report_iterations returns empty list when no iterations."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        iterations = manager.get_report_iterations()

        assert iterations == []

    def test_get_report_iterations_finds_all_iterations(self, tmp_path):
        """Test get_report_iterations finds all saved iterations."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Save multiple iterations
        for i in [1, 2, 3]:
            report = {"iteration": i, "data": f"report_{i}"}
            validation = {"quality_score": 0.80 + i * 0.05}
            manager.save_report_iteration(i, report, validation)

        iterations = manager.get_report_iterations()

        assert len(iterations) == 3
        assert iterations[0]["iteration"] == 1
        assert iterations[1]["iteration"] == 2
        assert iterations[2]["iteration"] == 3

    def test_get_report_iterations_includes_metadata(self, tmp_path):
        """Test get_report_iterations includes required metadata."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        report = {"metadata": {"title": "Test"}}
        validation = {
            "validation_summary": {
                "quality_score": 0.92,
                "completeness_score": 0.88,
                "accuracy_score": 0.95,
            }
        }
        manager.save_report_iteration(1, report, validation)

        iterations = manager.get_report_iterations()

        assert len(iterations) == 1
        iteration = iterations[0]
        assert "iteration" in iteration
        assert "report" in iteration
        assert "validation" in iteration
        assert "quality_score" in iteration
        assert iteration["quality_score"] == 0.92

    def test_get_report_iterations_sorted_by_iteration_number(self, tmp_path):
        """Test iterations are sorted by iteration number."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Save in random order
        for i in [3, 1, 2]:
            report = {"iteration": i}
            validation = {"validation_summary": {"quality_score": 0.80}}
            manager.save_report_iteration(i, report, validation)

        iterations = manager.get_report_iterations()

        assert iterations[0]["iteration"] == 1
        assert iterations[1]["iteration"] == 2
        assert iterations[2]["iteration"] == 3


class TestReportPDFSaving:
    """Test save_report_pdf method."""

    def test_save_report_pdf_creates_file(self, tmp_path):
        """Test that save_report_pdf creates correctly named PDF file."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Create a dummy PDF file to copy
        source_pdf = tmp_path / "source.pdf"
        source_pdf.write_bytes(b"%PDF-1.4 dummy content")

        final_path = manager.save_report_pdf(source_pdf)

        assert final_path == tmp_path / "study-report.pdf"
        assert final_path.exists()
        assert final_path.read_bytes() == b"%PDF-1.4 dummy content"

    def test_save_report_pdf_overwrites_existing(self, tmp_path):
        """Test that save_report_pdf overwrites existing PDF."""
        pdf_path = tmp_path / "study.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Create first PDF
        source_pdf1 = tmp_path / "source1.pdf"
        source_pdf1.write_bytes(b"PDF version 1")
        manager.save_report_pdf(source_pdf1)

        # Create second PDF and save again
        source_pdf2 = tmp_path / "source2.pdf"
        source_pdf2.write_bytes(b"PDF version 2")
        final_path = manager.save_report_pdf(source_pdf2)

        # Should have overwritten
        assert final_path.read_bytes() == b"PDF version 2"
