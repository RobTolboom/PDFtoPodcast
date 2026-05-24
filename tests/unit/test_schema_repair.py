"""
Unit tests for src/pipeline/schema_repair.py

Tests deterministic post-correction schema repair logic.
"""

import pytest

from src.pipeline.schema_repair import (
    _is_json_fragment_string,
    _repair_figures_key_values,
    repair_schema_violations,
)

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


class TestRemoveIncompleteOptionalObjectFields:
    """Test removal of optional object fields whose value is missing required sub-schema fields.

    When an LLM produces an incomplete object (e.g., an effect object without the required
    'type' and 'point' fields because no numeric estimate exists in the paper), the entire
    optional field should be removed rather than leaving an invalid object in place.
    """

    EFFECT_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "label": {"type": "string"},
            "effect": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "point"],
                "properties": {
                    "type": {"type": "string", "enum": ["RR", "OR", "HR", "MD", "Other"]},
                    "point": {"type": "number"},
                    "favors": {"type": "string"},
                },
            },
        },
    }

    def test_optional_object_missing_all_required_subfields_removed(self):
        """Optional object with none of its required sub-fields should be removed."""
        data = {
            "label": "Sensitivity by age",
            "effect": {"favors": "control"},  # Missing required "type" and "point"
        }

        result = repair_schema_violations(data, self.EFFECT_SCHEMA, None)

        assert "label" in result
        assert "effect" not in result

    def test_optional_object_missing_one_required_subfield_removed(self):
        """Optional object missing even one required sub-field should be removed."""
        data = {
            "label": "Sensitivity by age",
            "effect": {"type": "OR"},  # Has "type" but missing required "point"
        }

        result = repair_schema_violations(data, self.EFFECT_SCHEMA, None)

        assert "effect" not in result

    def test_optional_object_with_all_required_subfields_preserved(self):
        """Optional object with all required sub-fields intact should not be removed."""
        data = {
            "label": "Sensitivity by age",
            "effect": {"type": "OR", "point": 0.75, "favors": "intervention"},
        }

        result = repair_schema_violations(data, self.EFFECT_SCHEMA, None)

        assert "effect" in result
        assert result["effect"]["type"] == "OR"
        assert result["effect"]["point"] == 0.75

    def test_sensitivity_analysis_array_items_effect_removed(self):
        """Reproduce the sensitivity_analyses/0/effect error from the pipeline run.

        When qualitative sensitivity analyses produce an effect object with only
        optional fields (e.g. 'favors'), the effect field should be removed entirely
        because 'type' and 'point' are required by ContrastEffect schema.
        """
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "sensitivity_analyses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string"},
                            "effect": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["type", "point"],
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["RR", "OR", "HR", "MD", "Other"],
                                    },
                                    "point": {"type": "number"},
                                    "favors": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        }
        data = {
            "sensitivity_analyses": [
                {
                    "label": "Sensitivity analysis by age",
                    "effect": {"favors": "control_or_reference"},  # Missing "type" and "point"
                },
                {
                    "label": "Sensitivity analysis per-protocol",
                    "effect": {"type": "RR", "point": 0.82},  # Complete — should be kept
                },
            ],
        }

        result = repair_schema_violations(data, schema, None)

        assert len(result["sensitivity_analyses"]) == 2
        assert "effect" not in result["sensitivity_analyses"][0]
        assert "label" in result["sensitivity_analyses"][0]
        assert "effect" in result["sensitivity_analyses"][1]
        assert result["sensitivity_analyses"][1]["effect"]["point"] == 0.82

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

    def test_required_field_kept_even_when_empty(self):
        """Required field should NOT be removed even if empty string."""
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


# ---------------------------------------------------------------------------
# Task 3: schema_version normalisation
# ---------------------------------------------------------------------------

SCHEMA_VERSION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version"],
    "properties": {
        "schema_version": {
            "type": "string",
            "pattern": "^v\\d+\\.\\d+(\\.\\d+)?$",
        },
        "title": {"type": "string"},
    },
    "$defs": {},
}


class TestNormalizeSchemaVersion:
    """schema_repair normalises bare major-only schema_version strings."""

    VERSIONED_SCHEMA = {
        "type": "object",
        "required": ["schema_version"],
        "properties": {
            "schema_version": {
                "type": "string",
                "pattern": r"^v\d+\.\d+(\.\d+)?$",
            }
        },
    }

    def test_bare_major_version_normalised(self):
        """'v2' is normalised to 'v2.0' before validation."""
        data = {"schema_version": "v2"}
        result = repair_schema_violations(data, self.VERSIONED_SCHEMA)
        assert result["schema_version"] == "v2.0"

    def test_already_valid_version_unchanged(self):
        """'v2.0' is not modified."""
        data = {"schema_version": "v2.0"}
        result = repair_schema_violations(data, self.VERSIONED_SCHEMA)
        assert result["schema_version"] == "v2.0"

    def test_three_part_version_unchanged(self):
        """'v2.1.3' is not modified."""
        data = {"schema_version": "v2.1.3"}
        result = repair_schema_violations(data, self.VERSIONED_SCHEMA)
        assert result["schema_version"] == "v2.1.3"

    def test_no_schema_version_field_no_error(self):
        """When schema_version is absent, no error is raised."""
        data = {"title": "Study X"}
        result = repair_schema_violations(
            data, {"type": "object", "properties": {"title": {"type": "string"}}}
        )
        assert "schema_version" not in result


# ---------------------------------------------------------------------------
# Task 4: dropping malformed JSON-fragment strings from arrays
# ---------------------------------------------------------------------------


class TestIsJsonFragmentString:
    """Unit tests for the _is_json_fragment_string helper."""

    def test_json_object_string_detected(self):
        assert _is_json_fragment_string('{"key": "val"}') is True

    def test_json_array_string_detected(self):
        assert _is_json_fragment_string('["a", "b"]') is True

    def test_colon_detected(self):
        assert _is_json_fragment_string("key: value") is True

    def test_plain_id_string_not_detected(self):
        assert _is_json_fragment_string("O1") is False

    def test_alphanumeric_id_not_detected(self):
        assert _is_json_fragment_string("arm_A") is False

    def test_empty_string_not_detected(self):
        assert _is_json_fragment_string("") is False


class TestDropMalformedJsonFragments:
    """Test that JSON-fragment strings in object-typed arrays are dropped."""

    FRAGMENT_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "outcomes": {
                "type": "array",
                "items": {"$ref": "#/$defs/Outcome"},
            },
        },
        "$defs": {
            "Outcome": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "outcome_id": {"type": "string"},
                    "name": {"type": "string"},
                },
            },
        },
    }

    def test_json_fragment_string_dropped(self):
        """A string with JSON chars (\"  { [ ) in an array should be dropped."""
        data = {
            "outcomes": [
                {"outcome_id": "O1", "name": "Primary"},
                '{"outcome_id": "O2", "name": "Secondary"}',  # JSON fragment
            ],
        }
        result = repair_schema_violations(data, self.FRAGMENT_SCHEMA, None)
        assert len(result["outcomes"]) == 1
        assert result["outcomes"][0]["outcome_id"] == "O1"

    def test_plain_id_string_kept_for_restore(self):
        """A plain ID string (no special chars) goes through restore from original."""
        data = {"outcomes": ["O1"]}
        original = {
            "outcomes": [{"outcome_id": "O1", "name": "Primary"}],
        }
        result = repair_schema_violations(data, self.FRAGMENT_SCHEMA, original)
        assert result["outcomes"][0]["outcome_id"] == "O1"

    def test_fragment_with_colon_dropped(self):
        """A string with ':' is dropped from the array."""
        data = {
            "outcomes": [
                '["O1", "O2"]',  # JSON fragment with [ and "
                {"outcome_id": "O1", "name": "Primary"},
            ],
        }
        result = repair_schema_violations(data, self.FRAGMENT_SCHEMA, None)
        assert len(result["outcomes"]) == 1
        assert result["outcomes"][0]["outcome_id"] == "O1"

    def test_fragment_drop_logged_at_warning(self, caplog):
        """Dropping a JSON-fragment string must be logged at WARNING level.

        Dropping array items is a data-loss event and must be visible even
        in default logging configurations (WARNING threshold).
        """
        import logging

        data = {
            "outcomes": [
                '{"outcome_id": "O2", "name": "Secondary"}',  # JSON fragment
                {"outcome_id": "O1", "name": "Primary"},
            ],
        }
        with caplog.at_level(logging.WARNING, logger="src.pipeline.schema_repair"):
            repair_schema_violations(data, self.FRAGMENT_SCHEMA, None)

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any(
            "Dropping" in msg for msg in warning_messages
        ), f"Expected a WARNING log containing 'Dropping', got: {warning_messages}"


# ---------------------------------------------------------------------------
# Task 5: flattening depth-2+ key_values objects in figures_summary
# ---------------------------------------------------------------------------

FIGURES_SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "figures_summary": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "figure_id": {"type": "string"},
                    "key_values": {
                        "type": "object",
                        "additionalProperties": {
                            "oneOf": [
                                {"type": "number"},
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "additionalProperties": {
                                        "oneOf": [{"type": "number"}, {"type": "string"}]
                                    },
                                },
                            ]
                        },
                    },
                },
            },
        },
    },
    "$defs": {},
}


class TestFlattenKeyValuesDepth2:
    """Test that depth-2+ key_values objects are flattened to depth-1."""

    def test_depth2_object_flattened(self):
        """A depth-2 nested object should be flattened with underscore-separated keys.

        Depth-2 means the key_values value is an object whose values are themselves
        objects (not scalars).  The allowed schema allows depth-0 scalars and
        depth-1 objects (values are scalars).  Depth-2+ must be flattened.
        """
        figures = [
            {
                "figure_id": "F1",
                "key_values": {
                    # depth-2: exclusions -> category -> {subtype: count}
                    "exclusions": {
                        "pre_screening": {"medical": 5, "logistic": 3},
                    },
                    "enrolled": 120,
                },
            }
        ]
        result = _repair_figures_key_values(figures)
        kv = result[0]["key_values"]
        assert "exclusions" not in kv
        assert kv["exclusions_pre_screening_medical"] == 5
        assert kv["exclusions_pre_screening_logistic"] == 3
        assert kv["enrolled"] == 120

    def test_depth1_object_unchanged(self):
        """A depth-1 object value (all scalar values) should be left unchanged.

        Depth-1 objects are explicitly allowed by the schema: the value is an
        object whose own values are all scalars (numbers or strings).
        """
        figures = [
            {
                "figure_id": "F1",
                "key_values": {
                    "breakdown": {"a": 1, "b": 2},  # depth-1: scalar values — allowed
                    "total": 100,
                },
            }
        ]
        result = _repair_figures_key_values(figures)
        kv = result[0]["key_values"]
        assert kv["breakdown"] == {"a": 1, "b": 2}  # unchanged
        assert kv["total"] == 100

    def test_scalar_values_unchanged(self):
        """Scalar key_values should pass through unchanged."""
        figures = [
            {
                "figure_id": "F1",
                "key_values": {"n": 42, "label": "CONSORT"},
            }
        ]
        result = _repair_figures_key_values(figures)
        assert result[0]["key_values"] == {"n": 42, "label": "CONSORT"}

    def test_no_figures_summary_no_error(self):
        """Data without figures_summary should not cause errors."""
        data = {"title": "Test"}
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"title": {"type": "string"}},
            "$defs": {},
        }
        result = repair_schema_violations(data, schema, None)
        assert result == {"title": "Test"}

    def test_depth2_via_repair_schema_violations(self):
        """End-to-end: depth-2 key_values flattened via repair_schema_violations.

        'exclusions' maps to an object whose values are themselves objects (depth-2).
        The repair must flatten to depth-1.
        """
        data = {
            "figures_summary": [
                {
                    "figure_id": "F1",
                    "key_values": {
                        "exclusions": {
                            # depth-2: value is an object with object values
                            "criteria": {"age": 3, "comorbidity": 7},
                        },
                    },
                }
            ]
        }
        result = repair_schema_violations(data, FIGURES_SUMMARY_SCHEMA, None)
        kv = result["figures_summary"][0]["key_values"]
        assert "exclusions" not in kv
        assert kv["exclusions_criteria_age"] == 3
        assert kv["exclusions_criteria_comorbidity"] == 7
