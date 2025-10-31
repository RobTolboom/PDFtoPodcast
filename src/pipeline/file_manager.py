# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
File management for pipeline intermediate and final outputs.

This module provides the PipelineFileManager class for consistent
filename-based file naming and storage throughout the extraction pipeline.
"""

import json
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


class PipelineFileManager:
    """
    Manages filename-based file naming and storage for pipeline outputs.

    Uses PDF filename as the permanent identifier to create consistent naming:
    {pdf_filename}-{step}.json for all intermediate and final outputs.

    Attributes:
        pdf_path: Path to source PDF file
        pdf_stem: PDF filename without extension
        tmp_dir: Directory for temporary/intermediate files
        identifier: File identifier used in all output filenames

    Example:
        >>> from pathlib import Path
        >>> manager = PipelineFileManager(Path("research_paper.pdf"))
        >>> manager.identifier
        'research_paper'
        >>> filepath = manager.save_json({"type": "trial"}, "classification")
        >>> print(filepath)
        tmp/research_paper-classification.json
    """

    def __init__(self, pdf_path: Path):
        """
        Initialize file manager for a PDF.

        Args:
            pdf_path: Path to the PDF file being processed

        Note:
            Creates tmp/ directory if it doesn't exist.
            Prints the file identifier to console for tracking.
        """
        self.pdf_path = pdf_path
        self.pdf_stem = pdf_path.stem

        # Create tmp directory
        self.tmp_dir = Path("tmp")
        self.tmp_dir.mkdir(exist_ok=True)

        # Use PDF filename as permanent identifier (no DOI renaming)
        # This creates consistent naming: {pdf_filename}-{step}.json
        self.identifier = pdf_path.stem
        console.print(f"[blue]📁 File identifier: {self.identifier}[/blue]")

    def get_filename(
        self, step: str, iteration_number: int | None = None, status: str = ""
    ) -> Path:
        """
        Generate consistent filenames for pipeline steps.

        Args:
            step: Pipeline step name (e.g., "classification", "extraction", "validation")
            iteration_number: Optional iteration number for validation-correction loop (0, 1, 2, ...)
            status: Optional status suffix for special cases (e.g., "failed")

        Returns:
            Path to file in tmp directory

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> manager.get_filename("classification")
            PosixPath('tmp/paper-classification.json')
            >>> manager.get_filename("extraction", iteration_number=0)
            PosixPath('tmp/paper-extraction0.json')
            >>> manager.get_filename("validation", iteration_number=2)
            PosixPath('tmp/paper-validation2.json')
            >>> manager.get_filename("extraction", status="failed")
            PosixPath('tmp/paper-extraction-failed.json')
        """
        # Build filename parts
        parts = [self.identifier, step]

        # Add iteration number if provided (extraction0, validation1, etc.)
        if iteration_number is not None:
            parts[-1] = f"{step}{iteration_number}"

        # Add status if provided (for failed cases)
        if status:
            parts.append(status)

        filename = "-".join(parts) + ".json"
        return self.tmp_dir / filename

    def save_json(
        self, data: dict[Any, Any], step: str, iteration_number: int | None = None, status: str = ""
    ) -> Path:
        """
        Save JSON data with consistent filename-based naming.

        Args:
            data: Dictionary to save as JSON
            step: Pipeline step name
            iteration_number: Optional iteration number for validation-correction loop
            status: Optional status suffix

        Returns:
            Path to saved JSON file

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> result = {"publication_type": "interventional_trial"}
            >>> filepath = manager.save_json(result, "classification")
            >>> filepath.exists()
            True
            >>> extraction = {"data": "test"}
            >>> filepath = manager.save_json(extraction, "extraction", iteration_number=0)
            >>> filepath.name
            'paper-extraction0.json'
        """
        filepath = self.get_filename(step, iteration_number, status)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath

    def load_json(
        self, step: str, iteration_number: int | None = None, status: str = ""
    ) -> dict[str, Any] | None:
        """
        Load JSON data from file if it exists.

        Args:
            step: Pipeline step name
            iteration_number: Optional iteration number for validation-correction loop
            status: Optional status suffix

        Returns:
            Dictionary with loaded data, or None if file doesn't exist

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> # Save data first
            >>> manager.save_json({"type": "trial"}, "classification")
            PosixPath('tmp/paper-classification.json')
            >>> # Load it back
            >>> result = manager.load_json("classification")
            >>> result["type"]
            'trial'
            >>> # Load iteration file
            >>> manager.save_json({"data": "v1"}, "extraction", iteration_number=1)
            PosixPath('tmp/paper-extraction1.json')
            >>> result = manager.load_json("extraction", iteration_number=1)
            >>> result["data"]
            'v1'
            >>> # Non-existent file returns None
            >>> manager.load_json("nonexistent")
            None
        """
        filepath = self.get_filename(step, iteration_number, status)
        if not filepath.exists():
            return None

        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
