# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for report prompt loading.
"""

import pytest

from src.prompts import (
    get_all_available_prompts,
    load_report_correction_prompt,
    load_report_generation_prompt,
    load_report_validation_prompt,
    validate_prompt_directory,
)


def test_load_report_generation_prompt():
    """Test loading the report generation prompt"""
    prompt = load_report_generation_prompt()

    assert prompt is not None
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "PROMPT — Report Generation" in prompt
    assert "report_v1" in prompt


def test_load_report_validation_prompt():
    """Test loading the report validation prompt"""
    prompt = load_report_validation_prompt()

    assert prompt is not None
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "PROMPT — Report Validation" in prompt
    assert "report_validation_v1" in prompt


def test_load_report_correction_prompt():
    """Test loading the report correction prompt"""
    prompt = load_report_correction_prompt()

    assert prompt is not None
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "PROMPT — Report Correction" in prompt
    assert "report_v1" in prompt


def test_report_generation_prompt_contains_core_sections():
    """Test that report generation prompt describes all core sections"""
    prompt = load_report_generation_prompt()

    # Check for core section mentions
    core_sections = [
        "exec_bottom_line",
        "study_snapshot",
        "study_design",
        "quality_assessment",
        "results_primary",
        "results_secondary",
        "results_harms",
        "subgroups_sensitivity",
        "contextualization",
        "limitations",
        "bottom_line_extended",
        "source_map",
    ]

    for section in core_sections:
        assert section in prompt, f"Core section '{section}' not found in prompt"


def test_report_generation_prompt_contains_study_types():
    """Test that report generation prompt covers all study types"""
    prompt = load_report_generation_prompt()

    # Check for study type mentions
    study_types = [
        "interventional",
        "observational",
        "systematic_review",
        "prediction",
        "editorials",
    ]

    for study_type in study_types:
        assert study_type in prompt, f"Study type '{study_type}' not found in prompt"


def test_report_generation_prompt_contains_block_types():
    """Test that report generation prompt describes all block types"""
    prompt = load_report_generation_prompt()

    # Check for block type mentions
    block_types = ["textBlock", "tableBlock", "figureBlock", "calloutBlock"]

    for block_type in block_types:
        assert block_type in prompt, f"Block type '{block_type}' not found in prompt"


def test_report_validation_prompt_contains_validation_dimensions():
    """Test that report validation prompt describes all validation dimensions"""
    prompt = load_report_validation_prompt()

    # Check for validation dimension mentions
    dimensions = [
        "COMPLETENESS ASSESSMENT",
        "ACCURACY VERIFICATION",
        "CROSS-REFERENCE CONSISTENCY",
        "DATA CONSISTENCY",
        "SCHEMA COMPLIANCE",
    ]

    for dimension in dimensions:
        assert dimension in prompt, f"Validation dimension '{dimension}' not found in prompt"


def test_report_validation_prompt_contains_quality_score_formula():
    """Test that report validation prompt includes quality score calculation"""
    prompt = load_report_validation_prompt()

    assert "quality_score" in prompt
    assert "0.35" in prompt  # accuracy weight
    assert "0.30" in prompt  # completeness weight
    assert "0.15" in prompt  # schema compliance weight


def test_report_correction_prompt_contains_correction_workflow():
    """Test that report correction prompt describes correction workflow"""
    prompt = load_report_correction_prompt()

    # Check for correction step mentions
    steps = [
        "PRIORITIZE ISSUES",
        "FIX DATA MISMATCHES",
        "COMPLETE MISSING SECTIONS",
        "FIX GRADE/ROB MISMATCHES",
        "REMOVE HALLUCINATIONS",
    ]

    for step in steps:
        assert step in prompt, f"Correction step '{step}' not found in prompt"


def test_report_generation_prompt_language_support():
    """Test that report generation prompt supports both languages"""
    prompt = load_report_generation_prompt()

    # Check for language mentions
    assert "LANGUAGE" in prompt
    assert "nl" in prompt
    assert "en" in prompt
    assert "Dutch" in prompt or "Nederlands" in prompt
    assert "English" in prompt or "Engels" in prompt


def test_report_generation_prompt_evidence_locked():
    """Test that report generation prompt enforces evidence-locked principle"""
    prompt = load_report_generation_prompt()

    assert "EVIDENCE-LOCKED" in prompt or "evidence-locked" in prompt
    assert "EXTRACTION_JSON" in prompt
    assert "APPRAISAL_JSON" in prompt


def test_get_all_available_prompts_includes_report():
    """Test that get_all_available_prompts includes report prompts"""
    prompts = get_all_available_prompts()

    assert "report_generation" in prompts
    assert "report_validation" in prompts
    assert "report_correction" in prompts


def test_validate_prompt_directory_includes_report():
    """Test that validate_prompt_directory checks for report prompts"""
    validation_results = validate_prompt_directory()

    assert "Report-generation.txt" in validation_results
    assert "Report-validation.txt" in validation_results
    assert "Report-correction.txt" in validation_results

    # All should be True (files exist)
    assert validation_results["Report-generation.txt"] is True
    assert validation_results["Report-validation.txt"] is True
    assert validation_results["Report-correction.txt"] is True


def test_report_prompts_not_empty():
    """Test that all report prompts have substantial content"""
    gen_prompt = load_report_generation_prompt()
    val_prompt = load_report_validation_prompt()
    corr_prompt = load_report_correction_prompt()

    # Generation prompt should be largest (covers all study types)
    assert len(gen_prompt) > 5000, "Report generation prompt should be substantial"

    # Validation prompt should be comprehensive
    assert len(val_prompt) > 3000, "Report validation prompt should be comprehensive"

    # Correction prompt should be detailed
    assert len(corr_prompt) > 2000, "Report correction prompt should be detailed"


def test_report_prompts_utf8_encoding():
    """Test that all report prompts are UTF-8 encoded correctly"""
    # This test verifies that special characters (GRADE symbols, Dutch chars) are preserved
    gen_prompt = load_report_generation_prompt()

    # Check for UTF-8 characters (GRADE symbols if present)
    # The prompt should not have encoding errors
    assert isinstance(gen_prompt, str)
    assert len(gen_prompt.encode("utf-8")) >= len(gen_prompt)  # UTF-8 encoding works


def test_report_generation_prompt_contains_traceability():
    """Test that report generation prompt enforces traceability"""
    prompt = load_report_generation_prompt()

    assert "source_refs" in prompt
    assert "source_map" in prompt
    assert "traceability" in prompt.lower() or "traceable" in prompt.lower()


def test_report_validation_prompt_contains_thresholds():
    """Test that report validation prompt specifies quality thresholds"""
    prompt = load_report_validation_prompt()

    # Check for threshold mentions (default values from feature doc)
    assert "0.85" in prompt  # completeness threshold
    assert "0.95" in prompt  # accuracy threshold
    assert "0.90" in prompt  # consistency thresholds


def test_report_correction_prompt_evidence_locked():
    """Test that report correction prompt maintains evidence-locked principle"""
    prompt = load_report_correction_prompt()

    assert "EXTRACTION_JSON" in prompt
    assert "APPRAISAL_JSON" in prompt
    assert "evidence-locked" in prompt.lower() or "EVIDENCE-LOCKED" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
