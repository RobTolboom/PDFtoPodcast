# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Four-step PDF extraction pipeline package.

This package provides the core extraction pipeline that coordinates:
1. Classification - Identify publication type and extract metadata
2. Extraction - Schema-based structured data extraction
3. Validation - Dual validation (schema + conditional LLM semantic)
4. Correction - Fix issues identified during validation

Main Components:
    - orchestrator: Main pipeline coordination (run_four_step_pipeline)
    - file_manager: File naming and storage management
    - validation_runner: Dual validation strategy implementation
    - utils: Helper functions (DOI handling, breakpoints, etc.)

Usage:
    >>> from pathlib import Path
    >>> from src.pipeline import run_four_step_pipeline
    >>> results = run_four_step_pipeline(
    ...     pdf_path=Path("research_paper.pdf"),
    ...     max_pages=20,
    ...     llm_provider="openai"
    ... )
    >>> results["classification"]["publication_type"]
    'interventional_trial'

Public API:
    - run_four_step_pipeline: Main pipeline entry point
    - PipelineFileManager: File management class
    - run_dual_validation: Dual validation function
    - Utility functions: doi_to_safe_filename, get_file_identifier, etc.
"""

from .file_manager import PipelineFileManager
from .orchestrator import run_four_step_pipeline
from .utils import check_breakpoint, doi_to_safe_filename, get_file_identifier, get_next_step
from .validation_runner import SCHEMA_QUALITY_THRESHOLD, run_dual_validation

__all__ = [
    # Main pipeline orchestration
    "run_four_step_pipeline",
    # File management
    "PipelineFileManager",
    # Validation
    "run_dual_validation",
    "SCHEMA_QUALITY_THRESHOLD",
    # Utilities
    "doi_to_safe_filename",
    "get_file_identifier",
    "get_next_step",
    "check_breakpoint",
]
