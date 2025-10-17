"""
Unit tests for src/pipeline/file_manager.py

Tests file management for pipeline outputs.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.pipeline.file_manager import PipelineFileManager

pytestmark = pytest.mark.unit


class TestPipelineFileManager:
    """Test the PipelineFileManager class."""

    def test_init_creates_tmp_directory(self, tmp_path):
        """Test that initialization creates tmp directory."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch.object(Path, "mkdir"):
            manager = PipelineFileManager(pdf_path)

            # Verify tmp directory would be created
            assert manager.tmp_dir == Path("tmp")

    def test_pdf_stem_extracted_correctly(self, tmp_path):
        """Test that PDF filename stem is extracted correctly."""
        pdf_path = tmp_path / "research_paper.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)

        assert manager.pdf_stem == "research_paper"
        assert manager.identifier == "research_paper"

    def test_pdf_stem_with_multiple_dots(self, tmp_path):
        """Test filename with multiple dots (e.g., paper.v2.final.pdf)."""
        pdf_path = tmp_path / "paper.v2.final.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)

        assert manager.pdf_stem == "paper.v2.final"

    def test_save_json_creates_correct_filename(self, tmp_path):
        """Test that save_json creates correctly named file."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path  # Use tmp_path for testing

        data = {"type": "interventional_trial"}
        filepath = manager.save_json(data, "classification")

        expected_path = tmp_path / "test-classification.json"
        assert filepath == expected_path
        assert filepath.exists()

    def test_save_json_writes_valid_json(self, tmp_path):
        """Test that save_json writes valid JSON content."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        data = {"name": "John", "age": 30, "nested": {"key": "value"}}
        filepath = manager.save_json(data, "extraction")

        # Read back and verify
        with open(filepath) as f:
            loaded_data = json.load(f)

        assert loaded_data == data

    def test_save_and_load_json_roundtrip(self, tmp_path):
        """Test that saved JSON can be read back correctly."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Save data first
        data = {"result": "success", "count": 42}
        filepath = manager.save_json(data, "validation")

        # Load it back manually to verify
        with open(filepath) as f:
            loaded = json.load(f)

        assert loaded == data

    def test_get_filename_returns_correct_path(self, tmp_path):
        """Test that get_filename constructs correct file path."""
        pdf_path = tmp_path / "study_paper.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        filepath = manager.get_filename("extraction")

        expected = tmp_path / "study_paper-extraction.json"
        assert filepath == expected

    def test_get_filename_with_status(self, tmp_path):
        """Test that get_filename with status creates correct filename."""
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        filepath = manager.get_filename("extraction", "corrected")

        expected = tmp_path / "paper-extraction-corrected.json"
        assert filepath == expected

    def test_identifier_property(self, tmp_path):
        """Test that identifier property returns PDF stem."""
        pdf_path = tmp_path / "my_document.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)

        assert manager.identifier == "my_document"
        assert manager.identifier == manager.pdf_stem

    def test_load_json_returns_data_when_file_exists(self, tmp_path):
        """Test that load_json returns data when file exists."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Save data first
        data = {"publication_type": "interventional_trial", "doi": "10.1234/test"}
        manager.save_json(data, "classification")

        # Load it back
        loaded_data = manager.load_json("classification")

        assert loaded_data is not None
        assert loaded_data == data

    def test_load_json_returns_none_when_file_not_exists(self, tmp_path):
        """Test that load_json returns None when file doesn't exist."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Try to load non-existent file
        result = manager.load_json("nonexistent_step")

        assert result is None

    def test_load_json_with_status_suffix(self, tmp_path):
        """Test that load_json works with status suffix."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Save data with status
        data = {"corrected": True, "validation_passed": True}
        manager.save_json(data, "extraction", "corrected")

        # Load it back with status
        loaded_data = manager.load_json("extraction", "corrected")

        assert loaded_data is not None
        assert loaded_data["corrected"] is True

    def test_load_json_save_and_load_roundtrip(self, tmp_path):
        """Test complete save and load roundtrip using load_json method."""
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.touch()

        manager = PipelineFileManager(pdf_path)
        manager.tmp_dir = tmp_path

        # Save complex data
        data = {
            "is_valid": True,
            "quality_score": 0.95,
            "errors": [],
            "nested": {"field": "value"},
        }
        manager.save_json(data, "validation")

        # Load using load_json method
        loaded = manager.load_json("validation")

        assert loaded == data
        assert loaded["quality_score"] == 0.95
        assert loaded["nested"]["field"] == "value"
