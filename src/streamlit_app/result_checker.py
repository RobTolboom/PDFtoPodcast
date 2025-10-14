# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Result checker for existing pipeline outputs.

This module provides functions to check for existing pipeline results
and retrieve metadata about result files. Used by the Streamlit UI to:
- Show which steps have already been completed
- Allow viewing/deleting existing results
- Skip already completed steps if desired

File Naming Conventions:
    All result files follow the pattern: {identifier}-{step}.json
    - identifier: PDF filename stem (without .pdf extension)
    - step: Pipeline step name (classification, extraction, validation, correction)

    Special case for correction step: Uses -extraction-corrected.json suffix

Storage Location:
    All result files are stored in the tmp/ directory at project root.
    This directory is typically .gitignored to avoid committing large JSON files.

Example File Structure:
    tmp/
    ├── paper_2024-classification.json
    ├── paper_2024-extraction.json
    ├── paper_2024-validation.json
    └── paper_2024-extraction-corrected.json
"""

from datetime import datetime
from pathlib import Path


def get_identifier_from_pdf_path(pdf_path: str) -> str | None:
    """
    Extract identifier from PDF path for finding related result files.

    The identifier is used to create consistent filenames for all pipeline
    steps: {identifier}-{step}.json

    Args:
        pdf_path: Path to the PDF file (str or Path)

    Returns:
        PDF filename stem (without extension) or None if path is empty

    Example:
        >>> identifier = get_identifier_from_pdf_path("tmp/uploaded/paper.pdf")
        >>> print(identifier)
        'paper'
        >>> result_file = f"tmp/{identifier}-classification.json"
    """
    if not pdf_path:
        return None
    return Path(pdf_path).stem


def check_existing_results(identifier: str | None) -> dict:
    """
    Check which pipeline steps have existing results for this identifier.

    Args:
        identifier: File identifier (PDF filename stem)

    Returns:
        Dictionary with step names as keys and boolean existence flags as values

    Example:
        >>> results = check_existing_results("paper")
        >>> print(results)
        {
            'classification': True,
            'extraction': True,
            'validation': False,
            'correction': False
        }
    """
    if not identifier:
        return {
            "classification": False,
            "extraction": False,
            "validation": False,
            "correction": False,
        }

    tmp_dir = Path("tmp")
    results = {
        "classification": (tmp_dir / f"{identifier}-classification.json").exists(),
        "extraction": (tmp_dir / f"{identifier}-extraction.json").exists(),
        "validation": (tmp_dir / f"{identifier}-validation.json").exists(),
        "correction": (tmp_dir / f"{identifier}-extraction-corrected.json").exists(),
    }
    return results


def get_result_file_info(identifier: str, step: str) -> dict | None:
    """
    Get metadata about a result file if it exists.

    Args:
        identifier: File identifier (PDF filename stem)
        step: Pipeline step name ('classification', 'extraction', 'validation', 'correction')

    Returns:
        Dictionary with file metadata if file exists:
            - path: Full path to result file
            - size_kb: File size in kilobytes
            - modified: Last modified timestamp (formatted string)
        None if file doesn't exist or step is invalid

    Example:
        >>> info = get_result_file_info("paper", "classification")
        >>> if info:
        ...     print(f"Size: {info['size_kb']:.1f} KB")
        ...     print(f"Modified: {info['modified']}")
        Size: 3.2 KB
        Modified: 2025-01-09 12:34:56
    """
    tmp_dir = Path("tmp")

    # Map step names to filenames
    file_map = {
        "classification": f"{identifier}-classification.json",
        "extraction": f"{identifier}-extraction.json",
        "validation": f"{identifier}-validation.json",
        "correction": f"{identifier}-extraction-corrected.json",
    }

    if step not in file_map:
        return None

    file_path = tmp_dir / file_map[step]
    if not file_path.exists():
        return None

    # Get file statistics
    stat = file_path.stat()
    return {
        "path": str(file_path),
        "size_kb": stat.st_size / 1024,
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }
