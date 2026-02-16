"""
Unit tests for src/pipeline/schema_repair.py

Tests deterministic post-correction schema repair logic.
"""

import pytest

from src.pipeline.schema_repair import repair_schema_violations

pytestmark = pytest.mark.unit


# --- Minimal schema fragments for testing ---

SIMPLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "outcomes": {
            "type": "array",
            "items": {"$ref": "#/$defs/Outcome"},
        },
        "arms": {
            "type": "array",
            "items": {"$ref": "#/$defs/Arm"},
        },
        "nested_obj": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "value": {"type": "number"},
            },
        },
    },
    "$defs": {
        "Outcome": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "outcome_id": {"type": "string"},
                "name": {"type": "string"},
                "type": {"type": "string"},
            },
        },
        "Arm": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "arm_id": {"type": "string"},
                "label": {"type": "string"},
                "size": {"type": "integer"},
            },
        },
    },
}


class TestRepairArrayItems:
    """Test restoration of string array items to objects."""

    def test_string_items_restored_from_original(self):
        """When outcomes are strings but should be objects, restore from original."""
        data = {
            "title": "Test Study",
            "outcomes": ["O1", "O2"],
        }
        original = {
            "title": "Test Study",
            "outcomes": [
                {"outcome_id": "O1", "name": "Primary outcome", "type": "continuous"},
                {"outcome_id": "O2", "name": "Secondary outcome", "type": "binary"},
            ],
        }

        result = repair_schema_violations(data, SIMPLE_SCHEMA, original)

        assert len(result["outcomes"]) == 2
        assert result["outcomes"][0]["outcome_id"] == "O1"
        assert result["outcomes"][0]["name"] == "Primary outcome"
        assert result["outcomes"][1]["outcome_id"] == "O2"
        assert result["outcomes"][1]["name"] == "Secondary outcome"

    def test_object_items_preserved(self):
        """When outcomes are already objects, don't modify them."""
        data = {
            "title": "Test Study",
            "outcomes": [
                {"outcome_id": "O1", "name": "Primary outcome", "type": "continuous"},
            ],
        }

        result = repair_schema_violations(data, SIMPLE_SCHEMA, data)

        assert result["outcomes"][0] == data["outcomes"][0]

    def test_string_item_not_in_original(self):
        """When a string item cannot be found in original, keep it as-is."""
        data = {
            "title": "Test Study",
            "outcomes": ["O1", "O3"],  # O3 not in original
        }
        original = {
            "title": "Test Study",
            "outcomes": [
                {"outcome_id": "O1", "name": "Primary", "type": "continuous"},
            ],
        }

        result = repair_schema_violations(data, SIMPLE_SCHEMA, original)

        assert result["outcomes"][0]["outcome_id"] == "O1"
        assert result["outcomes"][1] == "O3"  # kept as-is

    def test_no_original_provided(self):
        """Without original, string items cannot be restored."""
        data = {
            "title": "Test Study",
            "outcomes": ["O1"],
        }

        result = repair_schema_violations(data, SIMPLE_SCHEMA, None)

        assert result["outcomes"][0] == "O1"

    def test_mixed_string_and_object_items(self):
        """Mixed array with some objects and some strings."""
        data = {
            "title": "Test Study",
            "outcomes": [
                {"outcome_id": "O1", "name": "Primary", "type": "continuous"},
                "O2",
            ],
        }
        original = {
            "title": "Test Study",
            "outcomes": [
                {"outcome_id": "O1", "name": "Primary", "type": "continuous"},
                {"outcome_id": "O2", "name": "Secondary", "type": "binary"},
            ],
        }

        result = repair_schema_violations(data, SIMPLE_SCHEMA, original)

        assert isinstance(result["outcomes"][0], dict)
        assert isinstance(result["outcomes"][1], dict)
        assert result["outcomes"][1]["name"] == "Secondary"

    def test_empty_array_unchanged(self):
        """Empty arrays should pass through unchanged."""
        data = {"title": "Test", "outcomes": []}

        result = repair_schema_violations(data, SIMPLE_SCHEMA, None)

        assert result["outcomes"] == []


class TestRemoveDisallowedProperties:
    """Test removal of properties not in schema."""

    def test_top_level_disallowed_removed(self):
        """Properties not defined in schema should be removed."""
        data = {
            "title": "Test",
            "outcomes": [],
            "extra_field": "should be removed",
            "_metadata": {"model": "gpt-5"},
        }

        result = repair_schema_violations(data, SIMPLE_SCHEMA, None)

        assert "title" in result
        assert "extra_field" not in result
        assert "_metadata" not in result

    def test_nested_disallowed_removed(self):
        """Disallowed properties in nested objects should be removed."""
        data = {
            "title": "Test",
            "nested_obj": {
                "name": "test",
                "value": 42,
                "source": {"page": 1},  # not in schema
            },
        }

        result = repair_schema_violations(data, SIMPLE_SCHEMA, None)

        assert "name" in result["nested_obj"]
        assert "source" not in result["nested_obj"]

    def test_disallowed_in_array_items_removed(self):
        """Disallowed properties in array item objects should be removed."""
        data = {
            "title": "Test",
            "outcomes": [
                {
                    "outcome_id": "O1",
                    "name": "Primary",
                    "type": "continuous",
                    "source": {"page": 1},  # not in Outcome schema
                },
            ],
        }

        result = repair_schema_violations(data, SIMPLE_SCHEMA, None)

        assert "source" not in result["outcomes"][0]
        assert result["outcomes"][0]["name"] == "Primary"


class TestIdempotency:
    """Test that repairing already-valid data returns it unchanged."""

    def test_valid_data_unchanged(self):
        """Valid data should pass through repair without modification."""
        data = {
            "title": "Test Study",
            "outcomes": [
                {"outcome_id": "O1", "name": "Primary", "type": "continuous"},
            ],
            "arms": [
                {"arm_id": "A", "label": "Treatment", "size": 50},
                {"arm_id": "B", "label": "Control", "size": 50},
            ],
        }

        result = repair_schema_violations(data, SIMPLE_SCHEMA, data)

        assert result == data

    def test_repair_does_not_modify_original(self):
        """Repair should not modify the input data dict."""
        data = {
            "title": "Test",
            "outcomes": ["O1"],
            "extra": "removed",
        }
        original = {
            "outcomes": [
                {"outcome_id": "O1", "name": "Primary", "type": "continuous"},
            ],
        }
        data_copy = {
            "title": "Test",
            "outcomes": ["O1"],
            "extra": "removed",
        }

        repair_schema_violations(data, SIMPLE_SCHEMA, original)

        assert data == data_copy  # original should be unmodified
