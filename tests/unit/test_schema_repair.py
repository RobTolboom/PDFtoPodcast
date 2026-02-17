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


# Extended schema with pattern-constrained and minimum-constrained fields
PATTERN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title"],
    "properties": {
        "title": {"type": "string"},
        "study_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9._/:;()\\[\\]-]+$",
        },
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title"],
            "properties": {
                "title": {"type": "string"},
                "pmid": {
                    "type": "string",
                    "pattern": "^\\d{1,8}$",
                },
                "issn": {
                    "type": "string",
                    "pattern": "^\\d{4}-\\d{3}[\\dxX]$",
                },
                "page_count": {
                    "type": "integer",
                    "minimum": 1,
                },
                "authors": {
                    "type": "array",
                    "items": {
                        "$ref": "#/$defs/Author",
                    },
                },
            },
        },
        "outcomes": {
            "type": "array",
            "items": {"$ref": "#/$defs/OutcomeWithISO"},
        },
        "truncated": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "is_truncated": {"type": "boolean"},
                "reason": {
                    "type": "string",
                    "enum": ["token_limit", "page_limit", "timeout", "other"],
                },
            },
        },
    },
    "$defs": {
        "Author": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "orcid": {
                    "type": "string",
                    "pattern": "^(https://orcid\\.org/)?0000-00(0[2-9]|[1-9]\\d)-\\d{4}-\\d{3}[\\dX]$",
                },
            },
        },
        "OutcomeWithISO": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "outcome_id": {"type": "string"},
                "name": {"type": "string"},
                "timepoint_iso8601": {
                    "type": "string",
                    "pattern": "^P(?:(?:\\d+Y)?(?:\\d+M)?(?:\\d+W)?(?:\\d+D)?)?(?:T(?:\\d+H)?(?:\\d+M)?(?:\\d+(?:\\.\\d+)?S)?)?$",
                },
            },
        },
    },
}


class TestRepairPatternViolations:
    """Test repair of empty strings violating pattern constraints."""

    def test_empty_string_pattern_field_removed_when_optional(self):
        """Empty string violating pattern on optional field should be removed."""
        data = {
            "title": "Test",
            "study_id": "",  # violates pattern, optional field
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "study_id" not in result

    def test_valid_pattern_field_preserved(self):
        """Valid pattern-matching string should be preserved."""
        data = {
            "title": "Test",
            "study_id": "NCT12345678",
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert result["study_id"] == "NCT12345678"

    def test_nested_pattern_field_removed(self):
        """Empty string violating pattern in nested object removed."""
        data = {
            "title": "Test",
            "metadata": {
                "title": "Study Title",
                "pmid": "",  # violates pattern, optional
                "issn": "",  # violates pattern, optional
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "pmid" not in result["metadata"]
        assert "issn" not in result["metadata"]
        assert result["metadata"]["title"] == "Study Title"

    def test_pattern_in_array_item_refs(self):
        """Empty pattern fields in array items via $ref should be removed."""
        data = {
            "title": "Test",
            "metadata": {
                "title": "Study",
                "authors": [
                    {"name": "Smith", "orcid": ""},
                    {"name": "Jones", "orcid": "0000-0002-1234-5678"},
                ],
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "orcid" not in result["metadata"]["authors"][0]
        assert result["metadata"]["authors"][1]["orcid"] == "0000-0002-1234-5678"

    def test_iso8601_empty_string_in_outcomes(self):
        """Empty ISO8601 duration fields in outcomes should be removed."""
        data = {
            "title": "Test",
            "outcomes": [
                {"outcome_id": "O1", "name": "Primary", "timepoint_iso8601": ""},
                {"outcome_id": "O2", "name": "Secondary", "timepoint_iso8601": "P6M"},
            ],
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "timepoint_iso8601" not in result["outcomes"][0]
        assert result["outcomes"][1]["timepoint_iso8601"] == "P6M"

    def test_required_pattern_field_not_removed(self):
        """Required field with pattern violation should NOT be removed."""
        data = {
            "title": "Test",
            "metadata": {
                "title": "",  # required field, should NOT be removed even if empty
                "pmid": "",  # optional, should be removed
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "title" in result["metadata"]  # required, kept
        assert "pmid" not in result["metadata"]  # optional pattern, removed


class TestRepairMinimumViolations:
    """Test repair of values violating minimum constraints."""

    def test_zero_below_minimum_removed_when_optional(self):
        """Value below minimum on optional field should be removed."""
        data = {
            "title": "Test",
            "metadata": {
                "title": "Study",
                "page_count": 0,  # minimum is 1, optional field
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "page_count" not in result["metadata"]

    def test_valid_minimum_preserved(self):
        """Value meeting minimum should be preserved."""
        data = {
            "title": "Test",
            "metadata": {
                "title": "Study",
                "page_count": 5,
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert result["metadata"]["page_count"] == 5


class TestRepairEnumViolations:
    """Test repair of values violating enum constraints."""

    def test_empty_string_not_in_enum_removed(self):
        """Empty string not in enum on optional field should be removed."""
        data = {
            "title": "Test",
            "truncated": {
                "is_truncated": False,
                "reason": "",  # not in enum, optional
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "reason" not in result["truncated"]

    def test_valid_enum_preserved(self):
        """Valid enum value should be preserved."""
        data = {
            "title": "Test",
            "truncated": {
                "is_truncated": True,
                "reason": "token_limit",
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert result["truncated"]["reason"] == "token_limit"
