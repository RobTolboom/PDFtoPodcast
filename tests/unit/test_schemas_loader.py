"""
Unit tests for src/schemas_loader.py

Tests schema loading, caching, and error handling for the PDFtoPodcast extraction pipeline.
"""

from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from src.schemas_loader import (
    _SCHEMA_CACHE,
    SCHEMA_MAPPING,
    SCHEMAS_DIR,
    SchemaLoadError,
    load_schema,
)

pytestmark = pytest.mark.unit


class TestLoadSchema:
    """Test the load_schema() function."""

    def setup_method(self):
        """Clear schema cache before each test."""
        _SCHEMA_CACHE.clear()

    def test_load_classification_schema_success(self):
        """Test loading classification schema successfully."""
        schema = load_schema("classification")

        assert schema is not None
        assert isinstance(schema, dict)
        assert "$schema" in schema
        assert "properties" in schema

    def test_load_interventional_trial_schema_success(self):
        """Test loading interventional trial bundled schema."""
        schema = load_schema("interventional_trial")

        assert schema is not None
        assert isinstance(schema, dict)
        assert "title" in schema
        assert "$defs" in schema  # Bundled schemas have definitions

    def test_load_observational_analytic_schema_success(self):
        """Test loading observational analytic bundled schema."""
        schema = load_schema("observational_analytic")

        assert schema is not None
        assert isinstance(schema, dict)

    def test_load_evidence_synthesis_schema_success(self):
        """Test loading evidence synthesis bundled schema."""
        schema = load_schema("evidence_synthesis")

        assert schema is not None
        assert isinstance(schema, dict)

    def test_load_prediction_prognosis_schema_success(self):
        """Test loading prediction/prognosis bundled schema."""
        schema = load_schema("prediction_prognosis")

        assert schema is not None
        assert isinstance(schema, dict)

    def test_load_editorials_opinion_schema_success(self):
        """Test loading editorials/opinion bundled schema."""
        schema = load_schema("editorials_opinion")

        assert schema is not None
        assert isinstance(schema, dict)

    def test_load_validation_schema_success(self):
        """Test loading validation schema."""
        schema = load_schema("validation")

        assert schema is not None
        assert isinstance(schema, dict)

    def test_load_schema_caches_result(self):
        """Test that schema is cached after first load."""
        # Clear cache
        _SCHEMA_CACHE.clear()

        # First load - should read from file
        schema1 = load_schema("classification")
        assert "classification" in _SCHEMA_CACHE

        # Second load - should use cache (same object reference)
        schema2 = load_schema("classification")
        assert schema1 is schema2

    def test_load_schema_invalid_type_raises_error(self):
        """Test that loading unknown publication type raises SchemaLoadError."""
        with pytest.raises(SchemaLoadError) as exc_info:
            load_schema("nonexistent_type")

        assert "Unknown publication type" in str(exc_info.value)
        assert "nonexistent_type" in str(exc_info.value)

    def test_load_schema_file_not_found_raises_error(self):
        """Test that missing schema file raises SchemaLoadError."""
        _SCHEMA_CACHE.clear()

        with patch("src.schemas_loader.SCHEMAS_DIR", Path("/nonexistent")):
            with pytest.raises(SchemaLoadError) as exc_info:
                load_schema("classification")

            assert "Schema file not found" in str(exc_info.value)

    def test_load_schema_invalid_json_raises_error(self):
        """Test that invalid JSON file raises SchemaLoadError."""
        _SCHEMA_CACHE.clear()

        # Mock file with invalid JSON
        with patch("builtins.open", mock_open(read_data="{ invalid json")):
            with pytest.raises(SchemaLoadError) as exc_info:
                load_schema("classification")

            assert "Invalid JSON in schema file" in str(exc_info.value)

    def test_schema_mapping_contains_all_types(self):
        """Test that SCHEMA_MAPPING has entries for all expected publication types."""
        expected_types = [
            "interventional_trial",
            "observational_analytic",
            "evidence_synthesis",
            "prediction_prognosis",
            "editorials_opinion",
            "classification",
            "validation",
            "appraisal",
            "appraisal_validation",
        ]

        for pub_type in expected_types:
            assert pub_type in SCHEMA_MAPPING

    def test_schemas_dir_is_valid_path(self):
        """Test that SCHEMAS_DIR points to a valid directory."""
        assert SCHEMAS_DIR.exists()
        assert SCHEMAS_DIR.is_dir()

    def test_all_schema_files_exist(self):
        """Test that all schema files referenced in SCHEMA_MAPPING exist."""
        for pub_type, filename in SCHEMA_MAPPING.items():
            schema_path = SCHEMAS_DIR / filename
            assert schema_path.exists(), f"Schema file missing: {filename} for {pub_type}"

    def test_schema_cache_is_dictionary(self):
        """Test that schema cache is properly initialized as dict."""
        assert isinstance(_SCHEMA_CACHE, dict)

    def test_load_schema_error_message_includes_supported_types(self):
        """Test that error message lists all supported types."""
        with pytest.raises(SchemaLoadError) as exc_info:
            load_schema("invalid_type")

        error_msg = str(exc_info.value)
        assert "Supported:" in error_msg
        assert "interventional_trial" in error_msg
        assert "classification" in error_msg
