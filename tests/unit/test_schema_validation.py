"""
Unit tests for JSON schema structural correctness.

Tests that schemas accept and reject the right data shapes.
Run from project root: pytest tests/unit/test_schema_validation.py -v
"""

import json

import pytest
from jsonschema import ValidationError, validate

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def key_values_schema():
    """Load the key_values sub-schema from FigureSummary in common.schema.json."""
    with open("schemas/common.schema.json") as f:
        schema = json.load(f)
    return schema["$defs"]["FigureSummary"]["properties"]["key_values"]


class TestKeyValuesDepth1Objects:
    """FigureSummary.key_values must accept depth-1 object values."""

    def test_scalar_number_valid(self, key_values_schema):
        """Existing behaviour: scalar number values are valid."""
        validate({"n_screened": 1320, "randomized": 600}, key_values_schema)

    def test_scalar_string_valid(self, key_values_schema):
        """Existing behaviour: scalar string values are valid."""
        validate({"status": "complete"}, key_values_schema)

    def test_depth1_object_valid(self, key_values_schema):
        """Depth-1 object value (CONSORT exclusion breakdown) must be valid."""
        data = {
            "exclusion_reasons": {
                "severe_lung_disease": 65,
                "active_infection": 32,
                "hypersensitivity": 15,
                "other": 8,
            }
        }
        validate(data, key_values_schema)  # should NOT raise after fix

    def test_depth1_object_string_values_valid(self, key_values_schema):
        """Depth-1 object with string values must be valid."""
        data = {"categories": {"a": "low", "b": "high"}}
        validate(data, key_values_schema)

    def test_depth2_object_invalid(self, key_values_schema):
        """Depth-2 object (object whose values are objects) must be rejected."""
        data = {"breakdown": {"sub": {"sub_sub": 1}}}
        with pytest.raises(ValidationError):
            validate(data, key_values_schema)
