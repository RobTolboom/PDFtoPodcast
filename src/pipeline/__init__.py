# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Six-step PDF extraction, appraisal, report generation, and podcast pipeline package.

This package provides the core pipeline that coordinates:
1. Classification - Identify publication type and extract metadata
2. Extraction - Schema-based structured data extraction
3. Validation & Correction - Iterative schema + semantic validation with fixes
4. Appraisal - Critical appraisal (risk of bias, GRADE, applicability)
5. Report Generation - Structured report JSON with LaTeX/WeasyPrint rendering
6. Podcast Generation - Audio script generation from extraction and appraisal data

Main Components:
    - orchestrator: Main pipeline coordination (run_full_pipeline, run_single_step)
    - file_manager: File naming and storage management
    - validation_runner: Dual validation strategy implementation
    - utils: Helper functions (DOI handling, breakpoints, etc.)

Usage:
    >>> from pathlib import Path
    >>> from src.pipeline import run_full_pipeline, run_single_step
    >>> results = run_full_pipeline(
    ...     pdf_path=Path("research_paper.pdf"),
    ...     max_pages=20,
    ...     llm_provider="openai"
    ... )
    >>> results["classification"]["publication_type"]
    'interventional_trial'

Public API:
    - run_full_pipeline: Main pipeline entry point (steps 1-6)
    - run_single_step: Execute individual steps including report_generation
    - PipelineFileManager: File management class
    - run_dual_validation: Dual validation function
    - Utility functions: doi_to_safe_filename, get_file_identifier, etc.
"""

from .file_manager import PipelineFileManager
from .orchestrator import run_full_pipeline, run_single_step, run_validation_with_correction
from .utils import check_breakpoint, doi_to_safe_filename, get_file_identifier, get_next_step
from .validation_runner import SCHEMA_QUALITY_THRESHOLD, run_dual_validation

__all__ = [
    # Main pipeline orchestration
    "run_full_pipeline",
    "run_single_step",
    "run_validation_with_correction",
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
