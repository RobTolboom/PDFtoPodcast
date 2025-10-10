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

    def get_filename(self, step: str, status: str = "") -> Path:
        """
        Generate consistent filenames for pipeline steps.

        Args:
            step: Pipeline step name (e.g., "classification", "extraction")
            status: Optional status suffix (e.g., "corrected", "failed")

        Returns:
            Path to file in tmp directory

        Example:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> manager.get_filename("extraction")
            PosixPath('tmp/paper-extraction.json')
            >>> manager.get_filename("extraction", "corrected")
            PosixPath('tmp/paper-extraction-corrected.json')
        """
        if status:
            filename = f"{self.identifier}-{step}-{status}.json"
        else:
            filename = f"{self.identifier}-{step}.json"

        return self.tmp_dir / filename

    def save_json(self, data: dict[Any, Any], step: str, status: str = "") -> Path:
        """
        Save JSON data with consistent filename-based naming.

        Args:
            data: Dictionary to save as JSON
            step: Pipeline step name
            status: Optional status suffix

        Returns:
            Path to saved JSON file

        Example:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> result = {"publication_type": "interventional_trial"}
            >>> filepath = manager.save_json(result, "classification")
            >>> filepath.exists()
            True
        """
        filepath = self.get_filename(step, status)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath
