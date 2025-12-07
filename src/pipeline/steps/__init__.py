# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Pipeline step modules.

This package contains extracted step implementations from orchestrator.py.
Each module handles a specific pipeline step:
- classification: Publication type identification
- extraction: Schema-based data extraction
- validation: Dual validation with iterative correction
- appraisal: Critical appraisal (RoB, GRADE, applicability)
- report: Report generation with iterative correction
- podcast: Audio script generation (re-export from podcast_logic)
"""

from .appraisal import (
    APPRAISAL_QUALITY_THRESHOLDS,
    STEP_APPRAISAL,
    STEP_APPRAISAL_VALIDATION,
    UnsupportedPublicationType,
    is_appraisal_quality_sufficient,
    run_appraisal_single_pass,
    run_appraisal_with_correction,
)
from .classification import run_classification_step
from .extraction import run_extraction_step
from .podcast import run_podcast_generation
from .report import (
    REPORT_QUALITY_THRESHOLDS,
    STEP_REPORT_GENERATION,
    is_report_quality_sufficient,
    run_report_generation,
    run_report_with_correction,
)
from .validation import (
    DEFAULT_QUALITY_THRESHOLDS,
    STEP_CORRECTION,
    STEP_VALIDATION,
    STEP_VALIDATION_CORRECTION,
    is_quality_sufficient,
    run_validation_with_correction,
)

__all__ = [
    # Classification
    "run_classification_step",
    # Extraction
    "run_extraction_step",
    # Validation
    "run_validation_with_correction",
    "is_quality_sufficient",
    "DEFAULT_QUALITY_THRESHOLDS",
    "STEP_VALIDATION",
    "STEP_CORRECTION",
    "STEP_VALIDATION_CORRECTION",
    # Appraisal
    "run_appraisal_with_correction",
    "run_appraisal_single_pass",
    "is_appraisal_quality_sufficient",
    "UnsupportedPublicationType",
    "APPRAISAL_QUALITY_THRESHOLDS",
    "STEP_APPRAISAL",
    "STEP_APPRAISAL_VALIDATION",
    # Report
    "run_report_with_correction",
    "run_report_generation",
    "is_report_quality_sufficient",
    "REPORT_QUALITY_THRESHOLDS",
    "STEP_REPORT_GENERATION",
    # Podcast
    "run_podcast_generation",
]
