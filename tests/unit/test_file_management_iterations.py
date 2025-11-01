# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Tests for iterative validation-correction file naming and persistence.

Verifies that iteration files are saved with correct naming pattern:
- Iteration 0: extraction0.json, validation0.json
- Iteration N: extractionN.json, validationN.json (where N = 1, 2, 3, ...)
"""

import json
from pathlib import Path

from src.pipeline.file_manager import PipelineFileManager


class TestIterationFileNaming:
    """Test dat iteration files correct benaamd worden."""

    def test_iteration_0_numbered(self, tmp_path):
        """Iteration 0 krijgt nummer 0."""
        # Create a dummy PDF path - FileManager extracts identifier from filename
        pdf_path = tmp_path / "test-123.pdf"
        pdf_path.touch()  # Create empty file

        fm = PipelineFileManager(pdf_path)

        path = fm.save_json({"test": "data"}, "validation", iteration_number=0)
        assert path.name == "test-123-validation0.json"

    def test_iteration_1_numbered(self, tmp_path):
        """Iteration 1 krijgt nummer 1."""
        pdf_path = tmp_path / "test-123.pdf"
        pdf_path.touch()

        fm = PipelineFileManager(pdf_path)

        path = fm.save_json({"test": "data"}, "extraction", iteration_number=1)
        assert path.name == "test-123-extraction1.json"

    def test_all_iterations_saved(self, tmp_path):
        """Simuleer volledige loop - alle files moeten er zijn."""
        pdf_path = tmp_path / "test-123.pdf"
        pdf_path.touch()

        fm = PipelineFileManager(pdf_path)
        max_iterations = 3

        # Save iterations 0-3 (all with iteration numbers)
        for i in range(0, max_iterations + 1):
            fm.save_json({"iter": i}, "validation", iteration_number=i)
            fm.save_json({"iter": i}, "extraction", iteration_number=i)

        # Verify all files exist with numbered naming pattern
        # FileManager saves to tmp/ directory relative to CWD, not tmp_path
        expected_files = [
            "test-123-validation0.json",
            "test-123-extraction0.json",
            "test-123-validation1.json",
            "test-123-extraction1.json",
            "test-123-validation2.json",
            "test-123-extraction2.json",
            "test-123-validation3.json",
            "test-123-extraction3.json",
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
