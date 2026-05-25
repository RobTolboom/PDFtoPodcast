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


@pytest.fixture(scope="module")
def interventional_bundled_schema():
    """Load the bundled interventional_trial schema (all $refs resolved inline)."""
    with open("schemas/interventional_trial_bundled.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def contrast_result_schema_it(interventional_bundled_schema):
    """Wrap ContrastResult as a standalone schema with $defs so $refs resolve."""
    cr_def = interventional_bundled_schema["$defs"]["ContrastResult"]
    return {"$defs": interventional_bundled_schema["$defs"], **cr_def}


@pytest.fixture(scope="module")
def observational_bundled_schema():
    """Load the bundled observational_analytic schema."""
    with open("schemas/observational_analytic_bundled.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def contrast_result_schema_oa(observational_bundled_schema):
    """Wrap ContrastResult as a standalone schema with $defs so $refs resolve."""
    cr_def = observational_bundled_schema["$defs"]["ContrastResult"]
    return {"$defs": observational_bundled_schema["$defs"], **cr_def}


class TestContrastResultEffectOptional:
    """ContrastResult.effect must be optional in both pub-type schemas."""

    def test_it_contrast_without_effect_valid(self, contrast_result_schema_it):
        """interventional_trial: ContrastResult with no effect field must be valid."""
        data = {"outcome_id": "O1", "comparison_id": "C1"}
        validate(data, contrast_result_schema_it)  # should NOT raise after fix

    def test_it_contrast_with_full_effect_valid(self, contrast_result_schema_it):
        """interventional_trial: ContrastResult with a complete effect is still valid."""
        data = {
            "outcome_id": "O1",
            "comparison_id": "C1",
            "effect": {
                "type": "RR",
                "point": 0.57,
                "p_value": "<0.001",
                "favors": "treatment_or_exposure",
            },
        }
        validate(data, contrast_result_schema_it)

    def test_oa_contrast_without_effect_valid(self, contrast_result_schema_oa):
        """observational_analytic: ContrastResult with no effect field must be valid."""
        data = {"outcome_id": "O1", "comparison_id": "C1"}
        validate(data, contrast_result_schema_oa)  # should NOT raise after fix

    def test_oa_contrast_with_full_effect_valid(self, contrast_result_schema_oa):
        """observational_analytic: ContrastResult with a complete effect is still valid."""
        data = {
            "outcome_id": "O1",
            "comparison_id": "C1",
            "effect": {"type": "HR", "point": 0.72, "favors": "treatment_or_exposure"},
        }
        validate(data, contrast_result_schema_oa)
