"""
Unit tests for src/validation.py

Tests validation logic for extracted data quality assurance.
"""

import pytest

from src.validation import (
    ValidationError,
    check_required_fields,
    validate_extraction_quality,
    validate_with_schema,
)

pytestmark = pytest.mark.unit


class TestValidateWithSchema:
    """Test the validate_with_schema() function."""

    def test_validate_with_schema_valid_data(self):
        """Test validation succeeds with valid data."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            "required": ["name"],
        }
        data = {"name": "John Doe", "age": 30}

        is_valid, errors = validate_with_schema(data, schema, strict=False)

        assert is_valid is True
        assert errors == []

    def test_validate_with_schema_invalid_data_non_strict(self):
        """Test validation returns errors in non-strict mode."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        data = {}  # Missing required field

        is_valid, errors = validate_with_schema(data, schema, strict=False)

        assert is_valid is False
        assert len(errors) > 0
        assert any("name" in error.lower() for error in errors)

    def test_validate_with_schema_invalid_data_strict_raises_error(self):
        """Test validation raises ValidationError in strict mode."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        data = {}

        with pytest.raises(ValidationError) as exc_info:
            validate_with_schema(data, schema, strict=True)

        assert "Schema validation failed" in str(exc_info.value)

    def test_validate_with_schema_type_mismatch(self):
        """Test validation catches type mismatches."""
        schema = {"type": "object", "properties": {"age": {"type": "number"}}}
        data = {"age": "not a number"}

        is_valid, errors = validate_with_schema(data, schema, strict=False)

        assert is_valid is False
        assert len(errors) > 0

    def test_validate_with_schema_nested_properties(self):
        """Test validation with nested object properties."""
        schema = {
            "type": "object",
            "properties": {
                "person": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
                    "required": ["name"],
                }
            },
            "required": ["person"],
        }
        data = {"person": {"name": "John", "age": 30}}

        is_valid, errors = validate_with_schema(data, schema, strict=False)

        assert is_valid is True
        assert errors == []


class TestCheckRequiredFields:
    """Test the check_required_fields() function."""

    def test_check_required_fields_all_present(self):
        """Test that all required fields present returns True."""
        data = {"name": "John", "email": "john@example.com", "age": 30}
        required = ["name", "email"]

        all_present, missing = check_required_fields(data, required)

        assert all_present is True
        assert missing == []

    def test_check_required_fields_some_missing(self):
        """Test that missing fields are detected."""
        data = {"name": "John"}
        required = ["name", "email", "age"]

        all_present, missing = check_required_fields(data, required)

        assert all_present is False
        assert "email" in missing
        assert "age" in missing
        assert "name" not in missing

    def test_check_required_fields_none_values_treated_as_missing(self):
        """Test that None values are treated as missing."""
        data = {"name": "John", "email": None}
        required = ["name", "email"]

        all_present, missing = check_required_fields(data, required)

        assert all_present is False
        assert "email" in missing
        assert "name" not in missing

    def test_check_required_fields_empty_required_list(self):
        """Test that empty required list returns True."""
        data = {"name": "John"}
        required = []

        all_present, missing = check_required_fields(data, required)

        assert all_present is True
        assert missing == []

    def test_check_required_fields_empty_data_dict(self):
        """Test that empty data with required fields returns all as missing."""
        data = {}
        required = ["name", "email"]

        all_present, missing = check_required_fields(data, required)

        assert all_present is False
        assert set(missing) == {"name", "email"}


class TestValidationError:
    """Test the ValidationError exception."""

    def test_validation_error_is_exception(self):
        """Test that ValidationError is a proper exception."""
        error = ValidationError("Test error")

        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_validation_error_can_be_raised(self):
        """Test that ValidationError can be raised and caught."""
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("Validation failed")

        assert "Validation failed" in str(exc_info.value)


class TestValidateExtractionQualityScoring:
    """Test proportional schema scoring in validate_extraction_quality."""

    def test_no_errors_gives_full_schema_score(self):
        """With no schema errors, schema_score component should be 1.0."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"},
            },
            "required": ["name"],
        }
        data = {"name": "Test", "age": 30}

        result = validate_extraction_quality(data, schema)

        assert result["schema_compliant"] is True
        # quality_score = 1.0 * 0.5 + completeness * 0.5
        assert result["quality_score"] >= 0.5  # At least schema component

    def test_few_errors_gives_proportional_score(self):
        """A few schema errors should give proportional score, not binary 0."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"},
                "email": {"type": "string"},
                "city": {"type": "string"},
                "country": {"type": "string"},
            },
            "required": ["name"],
        }
        # age is wrong type - 1 error out of 5 properties
        data = {
            "name": "Test",
            "age": "not_a_number",
            "email": "a@b.com",
            "city": "X",
            "country": "Y",
        }

        result = validate_extraction_quality(data, schema)

        assert result["schema_compliant"] is False
        # Should NOT be 0.0 + completeness*0.5 (old binary scoring)
        # Should be proportional: schema_score ~= 1 - 1/5 = 0.8
        # quality_score = 0.8 * 0.5 + completeness * 0.5
        assert result["quality_score"] > 0.5  # Must be above binary floor

    def test_all_errors_gives_low_score(self):
        """Many errors relative to fields should give low score."""
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        }
        data = {"a": "x", "b": "y"}  # 2 errors out of 2 fields

        result = validate_extraction_quality(data, schema)

        # 2 errors / 2 fields = 0.0 schema score
        assert result["quality_score"] <= 0.5
