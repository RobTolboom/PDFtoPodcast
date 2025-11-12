# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

# prompts.py
"""
Prompt loading utilities for the PDFtoPodcast extraction pipeline.

This module provides functions to load prompt templates from the prompts/ directory
for the four-step extraction pipeline:
1. Classification - Identify publication type and extract metadata
2. Extraction - Extract detailed data based on publication type
3. Validation - Verify quality and completeness of extracted data
4. Correction - Fix issues identified during validation
"""

from pathlib import Path

# Base directory for prompts
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class PromptLoadError(Exception):
    """Error loading prompt files"""

    pass


def load_classification_prompt() -> str:
    """Load the classification prompt from Classification.txt"""
    prompt_file = PROMPTS_DIR / "Classification.txt"

    if not prompt_file.exists():
        raise PromptLoadError(f"Classification prompt not found: {prompt_file}")

    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        raise PromptLoadError(f"Error reading classification prompt: {e}") from e


def load_extraction_prompt(publication_type: str) -> str:
    """Load appropriate extraction prompt based on publication type"""

    # Map publication types to prompt files
    prompt_mapping = {
        "interventional_trial": "Extraction-prompt-interventional.txt",
        "observational_analytic": "Extraction-prompt-observational.txt",
        "evidence_synthesis": "Extraction-prompt-evidence-synthesis.txt",
        "prediction_prognosis": "Extraction-prompt-prediction.txt",
        "editorials_opinion": "Extraction-prompt-editorials.txt",
    }

    if publication_type == "overig":
        raise PromptLoadError(
            "No specialized extraction prompt available for publication type 'overig'"
        )

    if publication_type not in prompt_mapping:
        raise PromptLoadError(
            f"Unknown publication type: {publication_type}. Supported: {list(prompt_mapping.keys())}"
        )

    prompt_file = PROMPTS_DIR / prompt_mapping[publication_type]

    if not prompt_file.exists():
        raise PromptLoadError(f"Extraction prompt not found: {prompt_file}")

    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        raise PromptLoadError(f"Error reading extraction prompt: {e}") from e


def load_validation_prompt() -> str:
    """Load the validation prompt from Extraction-validation.txt"""
    prompt_file = PROMPTS_DIR / "Extraction-validation.txt"

    if not prompt_file.exists():
        raise PromptLoadError(f"Validation prompt not found: {prompt_file}")

    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        raise PromptLoadError(f"Error reading validation prompt: {e}") from e


def load_correction_prompt() -> str:
    """Load the correction prompt from Extraction-correction.txt"""
    prompt_file = PROMPTS_DIR / "Extraction-correction.txt"

    if not prompt_file.exists():
        raise PromptLoadError(f"Correction prompt not found: {prompt_file}")

    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        raise PromptLoadError(f"Error reading correction prompt: {e}") from e


def get_all_available_prompts() -> dict[str, str]:
    """
    Get a dictionary of all available prompts with their descriptions.

    Returns:
        Dictionary mapping prompt names to descriptions for successfully loaded prompts.
        Prompts that fail to load are silently skipped.
    """
    prompts = {}

    # Check classification prompt
    try:
        load_classification_prompt()
        prompts["classification"] = "Publication type classification and metadata extraction"
    except PromptLoadError:
        pass

    # Check validation prompt
    try:
        load_validation_prompt()
        prompts["validation"] = "Quality validation and verification of extracted data"
    except PromptLoadError:
        pass

    # Check correction prompt
    try:
        load_correction_prompt()
        prompts["correction"] = "Extraction correction based on validation feedback"
    except PromptLoadError:
        pass

    # Check extraction prompts for each publication type
    extraction_types = [
        "interventional_trial",
        "observational_analytic",
        "evidence_synthesis",
        "prediction_prognosis",
        "editorials_opinion",
    ]

    for pub_type in extraction_types:
        try:
            load_extraction_prompt(pub_type)
            prompts[f"extraction_{pub_type}"] = f"Data extraction for {pub_type} publications"
        except PromptLoadError:
            pass

    return prompts


def load_appraisal_prompt(publication_type: str) -> str:
    """
    Load appropriate appraisal prompt based on publication type.

    Args:
        publication_type: Publication type from classification result

    Returns:
        Appraisal prompt text

    Raises:
        PromptLoadError: If publication type not supported or prompt file not found

    Note:
        The 'diagnostic' publication type uses the same prompt as 'prediction_prognosis'
        (Appraisal-prediction.txt) as both PROBAST and QUADAS tools have similar structure.
    """
    # Map publication types to appraisal prompt files
    prompt_mapping = {
        "interventional_trial": "Appraisal-interventional.txt",
        "observational_analytic": "Appraisal-observational.txt",
        "evidence_synthesis": "Appraisal-evidence-synthesis.txt",
        "prediction_prognosis": "Appraisal-prediction.txt",
        "diagnostic": "Appraisal-prediction.txt",  # Shared prompt (PROBAST/QUADAS)
        "editorials_opinion": "Appraisal-editorials.txt",
    }

    if publication_type == "overig":
        raise PromptLoadError("No appraisal prompt available for publication type 'overig'")

    if publication_type not in prompt_mapping:
        raise PromptLoadError(
            f"Unknown publication type: {publication_type}. Supported: {list(prompt_mapping.keys())}"
        )

    prompt_file = PROMPTS_DIR / prompt_mapping[publication_type]

    if not prompt_file.exists():
        raise PromptLoadError(f"Appraisal prompt not found: {prompt_file}")

    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        raise PromptLoadError(f"Error reading appraisal prompt: {e}") from e


def load_appraisal_validation_prompt() -> str:
    """
    Load the appraisal validation prompt from Appraisal-validation.txt.

    Returns:
        Appraisal validation prompt text

    Raises:
        PromptLoadError: If prompt file not found or cannot be read
    """
    prompt_file = PROMPTS_DIR / "Appraisal-validation.txt"

    if not prompt_file.exists():
        raise PromptLoadError(f"Appraisal validation prompt not found: {prompt_file}")

    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        raise PromptLoadError(f"Error reading appraisal validation prompt: {e}") from e


def load_appraisal_correction_prompt() -> str:
    """
    Load the appraisal correction prompt from Appraisal-correction.txt.

    Returns:
        Appraisal correction prompt text

    Raises:
        PromptLoadError: If prompt file not found or cannot be read
    """
    prompt_file = PROMPTS_DIR / "Appraisal-correction.txt"

    if not prompt_file.exists():
        raise PromptLoadError(f"Appraisal correction prompt not found: {prompt_file}")

    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        raise PromptLoadError(f"Error reading appraisal correction prompt: {e}") from e


def validate_prompt_directory() -> dict[str, bool]:
    """
    Validate that all expected prompt files are present in the prompts directory.

    Returns:
        Dictionary mapping filenames to boolean indicating if file exists.
    """
    expected_files = [
        "Classification.txt",
        "Extraction-validation.txt",
        "Extraction-correction.txt",
        "Extraction-prompt-interventional.txt",
        "Extraction-prompt-observational.txt",
        "Extraction-prompt-evidence-synthesis.txt",
        "Extraction-prompt-prediction.txt",
        "Extraction-prompt-editorials.txt",
        # Appraisal prompts
        "Appraisal-interventional.txt",
        "Appraisal-observational.txt",
        "Appraisal-evidence-synthesis.txt",
        "Appraisal-prediction.txt",
        "Appraisal-editorials.txt",
        "Appraisal-validation.txt",
        "Appraisal-correction.txt",
    ]

    validation_results = {}

    for filename in expected_files:
        file_path = PROMPTS_DIR / filename
        validation_results[filename] = file_path.exists()

    return validation_results
