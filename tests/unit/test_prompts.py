"""
Unit tests for src/prompts.py

Tests prompt loading utilities for the PDFtoPodcast extraction pipeline.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.prompts import (
    PROMPTS_DIR,
    PromptLoadError,
    load_classification_prompt,
    load_correction_prompt,
    load_extraction_prompt,
    load_podcast_generation_prompt,
    load_podcast_summary_prompt,
    load_validation_prompt,
)

pytestmark = pytest.mark.unit


class TestLoadClassificationPrompt:
    """Test the load_classification_prompt() function."""

    def test_load_classification_prompt_success(self):
        """Test loading classification prompt successfully."""
        prompt = load_classification_prompt()

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_load_classification_prompt_returns_non_empty_string(self):
        """Test that classification prompt contains actual content."""
        prompt = load_classification_prompt()

        # Should contain medical publication type classification instructions
        assert len(prompt) > 100  # Reasonable minimum length

    def test_load_classification_prompt_file_not_found_raises_error(self):
        """Test that missing classification prompt file raises PromptLoadError."""
        with patch("src.prompts.PROMPTS_DIR", Path("/nonexistent")):
            with pytest.raises(PromptLoadError) as exc_info:
                load_classification_prompt()

            assert "Classification prompt not found" in str(exc_info.value)

    def test_load_classification_prompt_read_error_raises_error(self):
        """Test that file read error raises PromptLoadError."""
        with patch("pathlib.Path.read_text", side_effect=PermissionError("Access denied")):
            with pytest.raises(PromptLoadError) as exc_info:
                load_classification_prompt()

            assert "Error reading classification prompt" in str(exc_info.value)


class TestLoadExtractionPrompt:
    """Test the load_extraction_prompt() function."""

    def test_load_extraction_prompt_interventional_trial(self):
        """Test loading interventional trial extraction prompt."""
        prompt = load_extraction_prompt("interventional_trial")

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_load_extraction_prompt_observational_analytic(self):
        """Test loading observational analytic extraction prompt."""
        prompt = load_extraction_prompt("observational_analytic")

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_load_extraction_prompt_evidence_synthesis(self):
        """Test loading evidence synthesis extraction prompt."""
        prompt = load_extraction_prompt("evidence_synthesis")

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_load_extraction_prompt_prediction_prognosis(self):
        """Test loading prediction/prognosis extraction prompt."""
        prompt = load_extraction_prompt("prediction_prognosis")

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_load_extraction_prompt_editorials_opinion(self):
        """Test loading editorials/opinion extraction prompt."""
        prompt = load_extraction_prompt("editorials_opinion")

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_load_extraction_prompt_overig_raises_error(self):
        """Test that 'overig' type raises PromptLoadError (no specialized prompt)."""
        with pytest.raises(PromptLoadError) as exc_info:
            load_extraction_prompt("overig")

        assert "No specialized extraction prompt" in str(exc_info.value)
        assert "overig" in str(exc_info.value)

    def test_load_extraction_prompt_unknown_type_raises_error(self):
        """Test that unknown publication type raises PromptLoadError."""
        with pytest.raises(PromptLoadError) as exc_info:
            load_extraction_prompt("unknown_type")

        assert "Unknown publication type" in str(exc_info.value)
        assert "unknown_type" in str(exc_info.value)

    def test_load_extraction_prompt_file_not_found_raises_error(self):
        """Test that missing extraction prompt file raises PromptLoadError."""
        with patch("src.prompts.PROMPTS_DIR", Path("/nonexistent")):
            with pytest.raises(PromptLoadError) as exc_info:
                load_extraction_prompt("interventional_trial")

            assert "Extraction prompt not found" in str(exc_info.value)

    def test_load_extraction_prompt_error_includes_supported_types(self):
        """Test that error message lists supported types."""
        with pytest.raises(PromptLoadError) as exc_info:
            load_extraction_prompt("invalid_type")

        error_msg = str(exc_info.value)
        assert "Supported:" in error_msg
        assert "interventional_trial" in error_msg


class TestLoadValidationPrompt:
    """Test the load_validation_prompt() function."""

    def test_load_validation_prompt_success(self):
        """Test loading validation prompt successfully."""
        prompt = load_validation_prompt()

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_load_validation_prompt_returns_non_empty_string(self):
        """Test that validation prompt contains actual content."""
        prompt = load_validation_prompt()

        assert len(prompt) > 100

    def test_load_validation_prompt_file_not_found_raises_error(self):
        """Test that missing validation prompt file raises PromptLoadError."""
        with patch("src.prompts.PROMPTS_DIR", Path("/nonexistent")):
            with pytest.raises(PromptLoadError) as exc_info:
                load_validation_prompt()

            assert "Validation prompt not found" in str(exc_info.value)


class TestLoadCorrectionPrompt:
    """Test the load_correction_prompt() function."""

    def test_load_correction_prompt_success(self):
        """Test loading correction prompt successfully."""
        prompt = load_correction_prompt()

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_load_correction_prompt_returns_non_empty_string(self):
        """Test that correction prompt contains actual content."""
        prompt = load_correction_prompt()

        assert len(prompt) > 100

    def test_load_correction_prompt_file_not_found_raises_error(self):
        """Test that missing correction prompt file raises PromptLoadError."""
        with patch("src.prompts.PROMPTS_DIR", Path("/nonexistent")):
            with pytest.raises(PromptLoadError) as exc_info:
                load_correction_prompt()

            assert "Correction prompt not found" in str(exc_info.value)


class TestLoadPodcastGenerationPrompt:
    """Tests for podcast generation prompt loading."""

    def test_load_podcast_generation_prompt_success(self):
        """Test that podcast generation prompt loads successfully."""
        prompt = load_podcast_generation_prompt()
        assert prompt is not None
        assert len(prompt) > 0

    def test_load_podcast_generation_prompt_contains_required_sections(self):
        """Test that podcast prompt contains key instruction sections."""
        prompt = load_podcast_generation_prompt()
        # Check for key sections mentioned in feature spec
        assert "EXTRACTION_JSON" in prompt or "extraction" in prompt.lower()
        assert "APPRAISAL_JSON" in prompt or "appraisal" in prompt.lower()

    def test_load_podcast_generation_prompt_file_not_found_raises_error(self):
        """Test that missing podcast prompt file raises PromptLoadError."""
        with patch("src.prompts.PROMPTS_DIR", Path("/nonexistent")):
            with pytest.raises(PromptLoadError) as exc_info:
                load_podcast_generation_prompt()

            assert "Podcast generation prompt not found" in str(exc_info.value)


class TestLoadPodcastSummaryPrompt:
    """Tests for podcast summary prompt loading."""

    def test_load_podcast_summary_prompt_success(self):
        """Test that podcast summary prompt loads successfully."""
        prompt = load_podcast_summary_prompt()
        assert prompt is not None
        assert len(prompt) > 0

    def test_load_podcast_summary_prompt_contains_required_sections(self):
        """Test that podcast summary prompt contains key instruction sections."""
        prompt = load_podcast_summary_prompt()
        assert "citation" in prompt.lower()
        assert "synopsis" in prompt.lower()
        assert "study_at_a_glance" in prompt.lower() or "study at a glance" in prompt.lower()

    def test_load_podcast_summary_prompt_file_not_found_raises_error(self):
        """Test that missing podcast summary prompt raises PromptLoadError."""
        with patch("src.prompts.PROMPTS_DIR", Path("/nonexistent")):
            with pytest.raises(PromptLoadError) as exc_info:
                load_podcast_summary_prompt()
            assert "Podcast summary prompt not found" in str(exc_info.value)


class TestPromptsModuleConstants:
    """Test module-level constants and configuration."""

    def test_prompts_dir_exists(self):
        """Test that PROMPTS_DIR points to valid directory."""
        assert PROMPTS_DIR.exists()
        assert PROMPTS_DIR.is_dir()

    def test_classification_prompt_file_exists(self):
        """Test that Classification.txt file exists."""
        classification_file = PROMPTS_DIR / "Classification.txt"
        assert classification_file.exists()
        assert classification_file.is_file()

    def test_validation_prompt_file_exists(self):
        """Test that Extraction-validation.txt file exists."""
        validation_file = PROMPTS_DIR / "Extraction-validation.txt"
        assert validation_file.exists()
        assert validation_file.is_file()

    def test_correction_prompt_file_exists(self):
        """Test that Extraction-correction.txt file exists."""
        correction_file = PROMPTS_DIR / "Extraction-correction.txt"
        assert correction_file.exists()
        assert correction_file.is_file()

    def test_all_extraction_prompt_files_exist(self):
        """Test that all extraction prompt files exist."""
        expected_files = [
            "Extraction-prompt-interventional.txt",
            "Extraction-prompt-observational.txt",
            "Extraction-prompt-evidence-synthesis.txt",
            "Extraction-prompt-prediction.txt",
            "Extraction-prompt-editorials.txt",
        ]

        for filename in expected_files:
            prompt_file = PROMPTS_DIR / filename
            assert prompt_file.exists(), f"Missing prompt file: {filename}"
            assert prompt_file.is_file()
