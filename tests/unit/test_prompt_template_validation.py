"""
Prompt template validation tests focused on placeholder coverage.

These tests ensure that appraisal prompts include the placeholders required
by the orchestration layer before invoking the LLM providers. Missing
placeholders would cause runtime failures (e.g., undefined format variables)
or incomplete context for the LLM.
"""

from __future__ import annotations

import pytest

from src.prompts import PROMPTS_DIR

pytestmark = pytest.mark.unit


APPRAISAL_PROMPT_REQUIREMENTS = [
    ("Appraisal-interventional.txt", {"EXTRACTED_JSON"}),
    ("Appraisal-observational.txt", {"EXTRACTED_JSON"}),
    ("Appraisal-evidence-synthesis.txt", {"EXTRACTED_JSON"}),
    ("Appraisal-prediction.txt", {"EXTRACTED_JSON"}),
    ("Appraisal-editorials.txt", {"EXTRACTED_JSON"}),
]

APPRAISAL_SYSTEM_PROMPT_REQUIREMENTS = [
    (
        "Appraisal-validation.txt",
        {"APPRAISAL_JSON", "EXTRACTION_JSON", "APPRAISAL_SCHEMA"},
    ),
    (
        "Appraisal-correction.txt",
        {"VALIDATION_REPORT", "ORIGINAL_APPRAISAL", "EXTRACTION_JSON", "APPRAISAL_SCHEMA"},
    ),
]


def _read_prompt(filename: str) -> str:
    """Read prompt text and fail fast if file is missing."""
    path = PROMPTS_DIR / filename
    assert path.exists(), f"Expected prompt file missing: {filename}"
    content = path.read_text(encoding="utf-8")
    assert content.strip(), f"Prompt file is empty: {filename}"
    return content


class TestAppraisalPromptPlaceholders:
    """Validate that appraisal prompts keep the placeholders the pipeline depends on."""

    @pytest.mark.parametrize(("filename", "required"), APPRAISAL_PROMPT_REQUIREMENTS)
    def test_appraisal_prompts_include_extracted_json_placeholder(
        self, filename: str, required: set[str]
    ):
        """Every appraisal prompt must reference EXTRACTED_JSON for context."""
        content = _read_prompt(filename)
        for placeholder in required:
            assert (
                placeholder in content
            ), f"Prompt {filename} is missing placeholder: {placeholder}"

    @pytest.mark.parametrize(("filename", "required"), APPRAISAL_SYSTEM_PROMPT_REQUIREMENTS)
    def test_appraisal_system_prompts_include_required_placeholders(
        self, filename: str, required: set[str]
    ):
        """
        Validation and correction prompts must expose all pipeline placeholders.

        Missing placeholders would break f-string replacements performed prior to
        sending the prompt to the LLM.
        """
        content = _read_prompt(filename)
        for placeholder in required:
            assert (
                placeholder in content
            ), f"Prompt {filename} is missing placeholder: {placeholder}"

    def test_appraisal_validation_prompt_lists_all_placeholders_together(self):
        """Regression test: ensure the validation prompt documents every input block."""
        content = _read_prompt("Appraisal-validation.txt")
        lines = content.splitlines()
        # Focus on the introductory block (first 20 lines) where inputs should be documented
        inputs_block = "\n".join(lines[:20])
        for placeholder in ("APPRAISAL_JSON", "EXTRACTION_JSON", "APPRAISAL_SCHEMA"):
            assert (
                placeholder in inputs_block
            ), f"Placeholder {placeholder} should be documented at the start of the prompt"
