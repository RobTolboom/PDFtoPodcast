"""
Unit tests for src/pipeline/utils.py

Tests utility functions for the pipeline.
"""

from pathlib import Path

import pytest

from src.pipeline.utils import doi_to_safe_filename, get_file_identifier, get_next_step

pytestmark = pytest.mark.unit


class TestDoiToSafeFilename:
    """Test the doi_to_safe_filename() function."""

    def test_doi_with_slashes_and_dots(self):
        """Test converting DOI with slashes and dots."""
        doi = "10.1234/example.2025"

        safe = doi_to_safe_filename(doi)

        assert safe == "10-1234-example-2025"

    def test_doi_with_prefix(self):
        """Test removing 'doi:' prefix."""
        doi = "doi:10.1234/test"

        safe = doi_to_safe_filename(doi)

        assert safe == "10-1234-test"

    def test_doi_with_uppercase_prefix(self):
        """Test removing 'DOI:' prefix (case insensitive)."""
        doi = "DOI:10.1234/test"

        safe = doi_to_safe_filename(doi)

        assert safe == "10-1234-test"

    def test_doi_with_colons(self):
        """Test replacing colons in DOI."""
        doi = "10.1234:example:2025"

        safe = doi_to_safe_filename(doi)

        assert safe == "10-1234-example-2025"


class TestGetFileIdentifier:
    """Test the get_file_identifier() function."""

    def test_get_identifier_with_doi(self):
        """Test getting identifier when DOI is present."""
        classification = {"metadata": {"doi": "10.1234/test"}}
        pdf_path = Path("paper.pdf")

        identifier = get_file_identifier(classification, pdf_path)

        assert identifier == "10-1234-test"

    def test_get_identifier_without_doi_uses_fallback(self):
        """Test fallback to PDF name + timestamp when no DOI."""
        classification = {"metadata": {}}
        pdf_path = Path("research_paper.pdf")

        identifier = get_file_identifier(classification, pdf_path)

        # Should start with PDF stem and contain timestamp
        assert identifier.startswith("research_paper_")
        assert len(identifier) > len("research_paper_")

    def test_get_identifier_without_metadata_uses_fallback(self):
        """Test fallback when metadata field is missing."""
        classification = {}
        pdf_path = Path("study.pdf")

        identifier = get_file_identifier(classification, pdf_path)

        assert identifier.startswith("study_")


class TestGetNextStep:
    """Test the get_next_step() function."""

    def test_next_step_after_classification(self):
        """Test getting next step after classification."""
        next_step = get_next_step("classification")

        assert next_step == "extraction"

    def test_next_step_after_extraction(self):
        """Test getting next step after extraction."""
        next_step = get_next_step("extraction")

        assert next_step == "validation"

    def test_next_step_after_validation(self):
        """Test getting next step after validation."""
        next_step = get_next_step("validation")

        assert next_step == "correction"

    def test_next_step_after_correction_is_none(self):
        """Test that correction is the last step."""
        next_step = get_next_step("correction")

        assert next_step == "None"

    def test_next_step_invalid_step_returns_none(self):
        """Test that invalid step name returns 'None'."""
        next_step = get_next_step("invalid_step")

        assert next_step == "None"
