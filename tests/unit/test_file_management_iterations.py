# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Tests for iterative validation-correction file naming and persistence.

Verifies that iteration files are saved with correct naming pattern:
- Iteration 0: no suffix (extraction.json, validation.json)
- Iteration N: _correctedN suffix (extraction_corrected1.json, etc.)
"""

import json
from pathlib import Path

from src.pipeline.file_manager import PipelineFileManager


class TestIterationFileNaming:
    """Test dat iteration files correct benaamd worden."""

    def test_iteration_0_no_suffix(self, tmp_path):
        """Iteration 0 krijgt geen suffix."""
        # Create a dummy PDF path - FileManager extracts identifier from filename
        pdf_path = tmp_path / "test-123.pdf"
        pdf_path.touch()  # Create empty file

        fm = PipelineFileManager(pdf_path)

        path = fm.save_json({"test": "data"}, "validation", status=None)
        assert path.name == "test-123-validation.json"

    def test_iteration_1_corrected_suffix(self, tmp_path):
        """Iteration 1 krijgt corrected1 suffix (met -)."""
        pdf_path = tmp_path / "test-123.pdf"
        pdf_path.touch()

        fm = PipelineFileManager(pdf_path)

        path = fm.save_json({"test": "data"}, "extraction", status="corrected1")
        assert path.name == "test-123-extraction-corrected1.json"

    def test_all_iterations_saved(self, tmp_path):
        """Simuleer volledige loop - alle files moeten er zijn."""
        pdf_path = tmp_path / "test-123.pdf"
        pdf_path.touch()

        fm = PipelineFileManager(pdf_path)
        max_iterations = 3

        # Save iteration 0
        fm.save_json({"iter": 0}, "validation", status=None)
        fm.save_json({"iter": 0}, "extraction", status=None)

        # Save iterations 1-3
        for i in range(1, max_iterations + 1):
            fm.save_json({"iter": i}, "validation", status=f"corrected{i}")
            fm.save_json({"iter": i}, "extraction", status=f"corrected{i}")

        # Verify all files exist (FileManager adds - between step and status)
        # FileManager saves to tmp/ directory relative to CWD, not tmp_path
        expected_files = [
            "test-123-validation.json",
            "test-123-extraction.json",
            "test-123-validation-corrected1.json",
            "test-123-extraction-corrected1.json",
            "test-123-validation-corrected2.json",
            "test-123-extraction-corrected2.json",
            "test-123-validation-corrected3.json",
            "test-123-extraction-corrected3.json",
        ]

        # FileManager saves to tmp/ directory in current working directory
        output_dir = Path("tmp")

        for filename in expected_files:
            filepath = output_dir / filename
            assert filepath.exists(), f"Missing file: {filename}"

            # Verify JSON is valid
            with open(filepath) as f:
                data = json.load(f)
                assert "iter" in data

            # Clean up test files
            filepath.unlink()
