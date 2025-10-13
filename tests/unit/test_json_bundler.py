"""
Unit tests for schemas/json-bundler.py

Tests the recursive $ref resolution fix that ensures nested dependencies
are properly embedded when bundling schemas.
"""

import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# Import functions from json-bundler by direct file import
schema_dir = Path(__file__).parent.parent.parent / "schemas"
json_bundler_path = schema_dir / "json-bundler.py"

# Load json-bundler.py as a module

spec = importlib.util.spec_from_file_location("json_bundler", json_bundler_path)
json_bundler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(json_bundler)

find_common_refs = json_bundler.find_common_refs
bundle_schema = json_bundler.bundle_schema
rewrite_refs_to_local = json_bundler.rewrite_refs_to_local


class TestFindCommonRefs:
    """Test the find_common_refs() function."""

    def test_find_external_refs(self):
        """Test that external common schema references are found."""
        schema = {
            "properties": {
                "metadata": {"$ref": "common.schema.json#/$defs/Metadata"},
                "author": {"$ref": "common.schema.json#/$defs/Author"},
            }
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        refs = set(find_common_refs(schema, pattern, include_local=False))

        assert refs == {"Metadata", "Author"}

    def test_find_local_refs_with_include_local(self):
        """Test that local #/$defs/ references are found when include_local=True."""
        schema = {
            "properties": {
                "authors": {"type": "array", "items": {"$ref": "#/$defs/Author"}},
                "registration": {"$ref": "#/$defs/Registration"},
            }
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        refs = set(find_common_refs(schema, pattern, include_local=True))

        assert refs == {"Author", "Registration"}

    def test_ignores_local_refs_without_include_local(self):
        """Test that local references are ignored when include_local=False."""
        schema = {
            "properties": {
                "metadata": {"$ref": "common.schema.json#/$defs/Metadata"},
                "authors": {"type": "array", "items": {"$ref": "#/$defs/Author"}},
            }
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        refs = set(find_common_refs(schema, pattern, include_local=False))

        # Should only find external ref, not local ref
        assert refs == {"Metadata"}
        assert "Author" not in refs

    def test_find_refs_in_nested_structures(self):
        """Test that references are found in deeply nested structures."""
        schema = {
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {"$ref": "common.schema.json#/$defs/Item"},
                        }
                    },
                }
            }
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        refs = set(find_common_refs(schema, pattern))

        assert refs == {"Item"}

    def test_handles_empty_schema(self):
        """Test that empty schema returns no refs."""
        schema = {}
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        refs = set(find_common_refs(schema, pattern))

        assert refs == set()


class TestBundleSchema:
    """Test the bundle_schema() function."""

    @pytest.fixture
    def common_schema(self):
        """Common schema with nested dependencies (mimics real common.schema.json)."""
        return {
            "$id": "common.schema.json",
            "$defs": {
                "Author": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
                "Registry": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
                "Registration": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "registry": {"$ref": "#/$defs/Registry"},  # Nested ref!
                    },
                },
                "SupplementFile": {
                    "type": "object",
                    "properties": {"filename": {"type": "string"}},
                },
                "Metadata": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "authors": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/Author"},  # Nested ref!
                        },
                        "registration": {"$ref": "#/$defs/Registration"},  # Nested ref!
                        "supplements": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/SupplementFile"},  # Nested ref!
                        },
                    },
                },
            },
        }

    def test_bundle_with_nested_refs(self, common_schema):
        """
        Test that bundling recursively resolves nested dependencies.

        This is the main regression test for the bug fix. When bundling a schema
        that references Metadata, the bundler must also include Author, Registration,
        Registry, and SupplementFile (the nested dependencies).
        """
        target_schema = {
            "type": "object",
            "properties": {
                "metadata": {"$ref": "common.schema.json#/$defs/Metadata"},
            },
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        bundled = bundle_schema(target_schema, common_schema, pattern)

        # Verify all definitions are embedded
        assert "Metadata" in bundled["$defs"]
        assert "Author" in bundled["$defs"]
        assert "Registration" in bundled["$defs"]
        assert "Registry" in bundled["$defs"]  # Deeply nested!
        assert "SupplementFile" in bundled["$defs"]

        # Verify references are rewritten to local
        metadata_def = bundled["$defs"]["Metadata"]
        assert metadata_def["properties"]["authors"]["items"]["$ref"] == "#/$defs/Author"
        assert metadata_def["properties"]["registration"]["$ref"] == "#/$defs/Registration"

    def test_bundle_avoids_duplicates(self, common_schema):
        """Test that definitions already in local $defs are not duplicated."""
        target_schema = {
            "type": "object",
            "properties": {
                "metadata": {"$ref": "common.schema.json#/$defs/Metadata"},
            },
            "$defs": {"Author": {"type": "object", "properties": {"custom": {"type": "string"}}}},
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        bundled = bundle_schema(target_schema, common_schema, pattern)

        # Should keep local Author definition (not overwrite)
        assert bundled["$defs"]["Author"]["properties"]["custom"]["type"] == "string"
        # But should still add other deps
        assert "Metadata" in bundled["$defs"]
        assert "Registration" in bundled["$defs"]

    def test_bundle_handles_multiple_top_level_refs(self, common_schema):
        """Test bundling schema with multiple top-level common refs."""
        target_schema = {
            "type": "object",
            "properties": {
                "metadata": {"$ref": "common.schema.json#/$defs/Metadata"},
                "author_info": {"$ref": "common.schema.json#/$defs/Author"},
            },
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        bundled = bundle_schema(target_schema, common_schema, pattern)

        # All refs should be resolved
        assert "Metadata" in bundled["$defs"]
        assert "Author" in bundled["$defs"]
        # Plus Metadata's nested deps
        assert "Registration" in bundled["$defs"]
        assert "Registry" in bundled["$defs"]
        assert "SupplementFile" in bundled["$defs"]

    def test_bundle_raises_on_missing_definition(self, common_schema):
        """Test that bundling raises error if referenced definition doesn't exist."""
        target_schema = {
            "type": "object",
            "properties": {
                "data": {"$ref": "common.schema.json#/$defs/NonExistent"},
            },
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        with pytest.raises(KeyError, match="NonExistent"):
            bundle_schema(target_schema, common_schema, pattern)


class TestRewriteRefsToLocal:
    """Test the rewrite_refs_to_local() function."""

    def test_rewrites_external_refs(self):
        """Test that external common schema refs are rewritten to local."""
        schema = {
            "properties": {
                "metadata": {"$ref": "common.schema.json#/$defs/Metadata"},
                "author": {"$ref": "common.schema.json#/$defs/Author"},
            }
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        rewritten = rewrite_refs_to_local(schema, pattern)

        assert rewritten["properties"]["metadata"]["$ref"] == "#/$defs/Metadata"
        assert rewritten["properties"]["author"]["$ref"] == "#/$defs/Author"

    def test_preserves_other_refs(self):
        """Test that non-common refs are preserved unchanged."""
        schema = {
            "properties": {
                "metadata": {"$ref": "common.schema.json#/$defs/Metadata"},
                "other": {"$ref": "#/$defs/LocalDef"},
                "external": {"$ref": "other.schema.json#/$defs/ExternalDef"},
            }
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        rewritten = rewrite_refs_to_local(schema, pattern)

        # Common ref rewritten
        assert rewritten["properties"]["metadata"]["$ref"] == "#/$defs/Metadata"
        # Local ref unchanged
        assert rewritten["properties"]["other"]["$ref"] == "#/$defs/LocalDef"
        # Other external ref unchanged
        assert rewritten["properties"]["external"]["$ref"] == "other.schema.json#/$defs/ExternalDef"

    def test_handles_nested_structures(self):
        """Test that rewriting works in nested structures."""
        schema = {
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"$ref": "common.schema.json#/$defs/Item"},
                }
            }
        }
        pattern = re.compile(r"^common\.schema\.json#/\$defs/([^/]+)$")

        rewritten = rewrite_refs_to_local(schema, pattern)

        assert rewritten["properties"]["items"]["items"]["$ref"] == "#/$defs/Item"
