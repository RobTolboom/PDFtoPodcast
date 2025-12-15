# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Tests for _remove_null_values() utility function.

This function removes explicit null values from LLM output before schema validation,
preventing spurious validation failures when LLMs emit "field": null for absent
optional fields.
"""

from src.pipeline.utils import _remove_null_values


class TestRemoveNullValues:
    """Tests for _remove_null_values recursive null removal."""

    def test_removes_top_level_nulls(self):
        """Should remove null values from top-level dict."""
        data = {"a": 1, "b": None, "c": "test"}
        result = _remove_null_values(data)
        assert result == {"a": 1, "c": "test"}

    def test_removes_nested_nulls(self):
        """Should recursively remove nulls from nested dicts."""
        data = {"outer": {"inner": None, "value": 1}}
        result = _remove_null_values(data)
        assert result == {"outer": {"value": 1}}

    def test_removes_nulls_in_list_of_dicts(self):
        """Should remove nulls from dicts inside lists."""
        data = {"items": [{"a": 1}, {"b": None, "c": 2}]}
        result = _remove_null_values(data)
        assert result == {"items": [{"a": 1}, {"c": 2}]}

    def test_removes_null_items_from_list(self):
        """Should remove None items from lists."""
        data = {"items": [1, None, 2, None, 3]}
        result = _remove_null_values(data)
        assert result == {"items": [1, 2, 3]}

    def test_empty_dict_returns_empty(self):
        """Should handle empty dicts."""
        assert _remove_null_values({}) == {}

    def test_empty_list_returns_empty(self):
        """Should handle empty lists."""
        assert _remove_null_values([]) == []

    def test_preserves_false_value(self):
        """Should preserve False values (not remove as null)."""
        data = {"a": False, "b": None}
        result = _remove_null_values(data)
        assert result == {"a": False}

    def test_preserves_zero_value(self):
        """Should preserve 0 values (not remove as null)."""
        data = {"a": 0, "b": None}
        result = _remove_null_values(data)
        assert result == {"a": 0}

    def test_preserves_empty_string(self):
        """Should preserve empty strings (not remove as null)."""
        data = {"a": "", "b": None}
        result = _remove_null_values(data)
        assert result == {"a": ""}

    def test_deeply_nested_structure(self):
        """Should handle deeply nested structures."""
        data = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": "deep",
                        "null_field": None,
                    }
                }
            }
        }
        result = _remove_null_values(data)
        assert result == {"level1": {"level2": {"level3": {"value": "deep"}}}}

    def test_mixed_nested_lists_and_dicts(self):
        """Should handle mixed nested lists and dicts."""
        data = {
            "sections": [
                {"name": "section1", "content": None},
                {"name": "section2", "items": [1, None, 3]},
            ]
        }
        result = _remove_null_values(data)
        expected = {
            "sections": [
                {"name": "section1"},
                {"name": "section2", "items": [1, 3]},
            ]
        }
        assert result == expected

    def test_returns_primitive_unchanged(self):
        """Should return primitive values unchanged."""
        assert _remove_null_values("string") == "string"
        assert _remove_null_values(42) == 42
        assert _remove_null_values(3.14) == 3.14
        assert _remove_null_values(True) is True

    def test_returns_none_unchanged(self):
        """Should return None unchanged when passed directly."""
        assert _remove_null_values(None) is None

    def test_dict_becomes_empty_after_removal(self):
        """Should return empty dict when all values are null."""
        data = {"a": None, "b": None}
        result = _remove_null_values(data)
        assert result == {}

    def test_list_becomes_empty_after_removal(self):
        """Should return empty list when all items are null."""
        data = [None, None, None]
        result = _remove_null_values(data)
        assert result == []
