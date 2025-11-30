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
            'correction': False,
            'validation_correction': False
        }
    """
    if not identifier:
        return {
            "classification": False,
            "extraction": False,
            "validation": False,
            "correction": False,
            "validation_correction": False,
            "appraisal": False,
            "report_generation": False,
            "podcast_generation": False,
        }

    tmp_dir = Path("tmp")
    results = {
        "classification": (tmp_dir / f"{identifier}-classification.json").exists(),
        "extraction": (tmp_dir / f"{identifier}-extraction0.json").exists(),
        "validation": (tmp_dir / f"{identifier}-validation0.json").exists(),
        "correction": (tmp_dir / f"{identifier}-extraction1.json").exists(),
        "validation_correction": any(tmp_dir.glob(f"{identifier}-validation[0-9]*.json")),
        "appraisal": any(tmp_dir.glob(f"{identifier}-appraisal[0-9]*.json")),
        "report_generation": any(tmp_dir.glob(f"{identifier}-report[0-9]*.json"))
        or (tmp_dir / f"{identifier}-report-best.json").exists(),
        "podcast_generation": (tmp_dir / f"{identifier}-podcast.json").exists(),
    }
    return results


def get_result_file_info(identifier: str, step: str) -> dict | None:
    """
    Get metadata about a result file if it exists.

    Args:
        identifier: File identifier (PDF filename stem)
        step: Pipeline step name ('classification', 'extraction', 'validation', 'correction', 'validation_correction')

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

    # Determine file path based on step
    # For extraction and validation: prefer BEST file, fall back to iteration 0
    # For validation_correction: prefer BEST validation, fall back to most recent

    if step == "extraction":
        # Try best extraction first
        best_path = tmp_dir / f"{identifier}-extraction-best.json"
        if best_path.exists():
            file_path = best_path
        else:
            # Fallback to extraction0
            file_path = tmp_dir / f"{identifier}-extraction0.json"
            if not file_path.exists():
                return None

    elif step == "validation":
        # Try best validation first
        best_path = tmp_dir / f"{identifier}-validation-best.json"
        if best_path.exists():
            file_path = best_path
        else:
            # Fallback to validation0
            file_path = tmp_dir / f"{identifier}-validation0.json"
            if not file_path.exists():
                return None

    elif step == "validation_correction":
        # Try best validation first
        best_path = tmp_dir / f"{identifier}-validation-best.json"
        if best_path.exists():
            file_path = best_path
        else:
            # Fallback: find most recent validation iteration
            validation_files = list(tmp_dir.glob(f"{identifier}-validation[0-9]*.json"))
            if not validation_files:
                return None
            file_path = max(validation_files, key=lambda p: p.stat().st_mtime)

    elif step == "appraisal":
        # Try best appraisal first
        best_path = tmp_dir / f"{identifier}-appraisal-best.json"
        if best_path.exists():
            file_path = best_path
        else:
            # Fallback: appraisal0 or most recent iteration
            appraisal0 = tmp_dir / f"{identifier}-appraisal0.json"
            if appraisal0.exists():
                file_path = appraisal0
            else:
                # Find most recent appraisal iteration
                appraisal_files = list(tmp_dir.glob(f"{identifier}-appraisal[0-9]*.json"))
                if not appraisal_files:
                    return None
                file_path = max(appraisal_files, key=lambda p: p.stat().st_mtime)

    elif step == "report_generation":
        best_path = tmp_dir / f"{identifier}-report-best.json"
        if best_path.exists():
            file_path = best_path
        else:
            report0 = tmp_dir / f"{identifier}-report0.json"
            if report0.exists():
                file_path = report0
            else:
                report_files = list(tmp_dir.glob(f"{identifier}-report[0-9]*.json"))
                if not report_files:
                    return None
                file_path = max(report_files, key=lambda p: p.stat().st_mtime)

    else:
        # Map step names to filenames for other steps
        file_map = {
            "classification": f"{identifier}-classification.json",
            "correction": f"{identifier}-extraction1.json",
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
