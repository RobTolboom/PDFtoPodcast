"""
Integration tests for schema bundling workflow.

Tests the complete bundling process using test fixtures to ensure
the recursive $ref resolution works end-to-end.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# Import bundler functions by direct file import
schema_dir = Path(__file__).parent.parent.parent / "schemas"
json_bundler_path = schema_dir / "json-bundler.py"

spec = importlib.util.spec_from_file_location("json_bundler", json_bundler_path)
json_bundler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(json_bundler)

bundle_schema = json_bundler.bundle_schema


class TestSchemaBundling:
    """Integration tests for complete schema bundling workflow."""

    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures directory."""
        return Path(__file__).parent.parent / "fixtures" / "schemas"

    @pytest.fixture
    def test_common_schema(self, fixtures_dir):
        """Load test common schema fixture."""
        schema_path = fixtures_dir / "test_common.schema.json"
        return json.loads(schema_path.read_text())

    @pytest.fixture
    def test_study_schema(self, fixtures_dir):
        """Load test study schema fixture."""
        schema_path = fixtures_dir / "test_study.schema.json"
        return json.loads(schema_path.read_text())

    def test_bundle_with_fixtures_resolves_all_nested_refs(
        self, test_study_schema, test_common_schema
    ):
        """
        Integration test: Bundle test_study.schema.json with test_common.schema.json.

        This is the main regression test that verifies the complete workflow:
        1. test_study references Metadata
        2. Metadata references Author, Registration, SupplementFile
        3. Registration references Registry
        4. All definitions should be embedded in bundled output
        """
        pattern = re.compile(r"^test_common\.schema\.json#/\$defs/([^/]+)$")

        bundled = bundle_schema(test_study_schema, test_common_schema, pattern)

        # Verify all transitive dependencies are embedded
        assert "$defs" in bundled
        assert "Metadata" in bundled["$defs"], "Top-level Metadata missing"
        assert "Author" in bundled["$defs"], "Nested Author missing"
        assert "Registration" in bundled["$defs"], "Nested Registration missing"
        assert "Registry" in bundled["$defs"], "Deeply nested Registry missing"
        assert "SupplementFile" in bundled["$defs"], "Nested SupplementFile missing"

        # Total: 5 definitions should be embedded
        assert len(bundled["$defs"]) == 5

    def test_bundled_schema_has_no_external_refs(self, test_study_schema, test_common_schema):
        """Test that bundled schema contains no external references."""
        pattern = re.compile(r"^test_common\.schema\.json#/\$defs/([^/]+)$")

        bundled = bundle_schema(test_study_schema, test_common_schema, pattern)

        # Convert to JSON string and check for external refs
        bundled_str = json.dumps(bundled)

        assert (
            "test_common.schema.json" not in bundled_str
        ), "Bundled schema still contains external references"

        # All refs should be local
        assert bundled["properties"]["metadata"]["$ref"] == "#/$defs/Metadata"

    def test_bundled_definitions_are_complete(self, test_study_schema, test_common_schema):
        """Test that embedded definitions are complete and unchanged."""
        pattern = re.compile(r"^test_common\.schema\.json#/\$defs/([^/]+)$")

        bundled = bundle_schema(test_study_schema, test_common_schema, pattern)

        # Check Metadata definition
        metadata = bundled["$defs"]["Metadata"]
        assert "title" in metadata["properties"]
        assert "authors" in metadata["properties"]
        assert "registration" in metadata["properties"]
        assert "supplements" in metadata["properties"]

        # Check Author definition
        author = bundled["$defs"]["Author"]
        assert "name" in author["properties"]
        assert "email" in author["properties"]

        # Check Registration definition
        registration = bundled["$defs"]["Registration"]
        assert "id" in registration["properties"]
        assert "registry" in registration["properties"]

        # Check that nested refs are rewritten to local
        assert registration["properties"]["registry"]["$ref"] == "#/$defs/Registry"

    def test_bundled_schema_validates_against_jsonschema(
        self, test_study_schema, test_common_schema
    ):
        """Test that bundled schema is valid JSON Schema."""
        from jsonschema import Draft7Validator

        pattern = re.compile(r"^test_common\.schema\.json#/\$defs/([^/]+)$")

        bundled = bundle_schema(test_study_schema, test_common_schema, pattern)

        # This will raise if the schema is invalid
        validator = Draft7Validator(bundled)
        validator.check_schema(bundled)  # Validates schema structure

    def test_bundled_schema_can_validate_data(self, test_study_schema, test_common_schema):
        """Test that bundled schema can validate actual data."""
        from jsonschema import ValidationError, validate

        pattern = re.compile(r"^test_common\.schema\.json#/\$defs/([^/]+)$")

        bundled = bundle_schema(test_study_schema, test_common_schema, pattern)

        # Valid data
        valid_data = {
            "schema_version": "v1.0-test",
            "metadata": {
                "title": "Test Study",
                "authors": [{"name": "John Doe", "email": "john@example.com"}],
                "registration": {
                    "id": "NCT12345678",
                    "registry": {"name": "ClinicalTrials.gov"},
                },
            },
        }

        # Should not raise
        validate(valid_data, bundled)

        # Invalid data (missing required field)
        invalid_data = {
            "schema_version": "v1.0-test",
            # Missing required "metadata" field
        }

        # Should raise ValidationError
        with pytest.raises(ValidationError):
            validate(invalid_data, bundled)
