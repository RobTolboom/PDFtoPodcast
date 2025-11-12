"""
Schema compatibility tests for OpenAI structured outputs.

The appraisal pipeline relies on strict schemas that must comply with the
limits documented for OpenAI structured outputs (response_format=json_schema).
These tests guard against regressions in the bundled appraisal schemas.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from src.schemas_loader import load_schema, validate_schema_compatibility

pytestmark = pytest.mark.unit

APPRAISAL_SCHEMA_TYPES = ("appraisal", "appraisal_validation")


def _iter_schema_nodes(node: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    """Depth-first traversal yielding (path, node) pairs for dicts and lists."""
    yield path, node

    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}"
            yield from _iter_schema_nodes(value, child_path)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            child_path = f"{path}[{index}]"
            yield from _iter_schema_nodes(item, child_path)


def _iter_object_nodes(schema: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield schema nodes that represent JSON objects."""
    for path, node in _iter_schema_nodes(schema):
        if isinstance(node, dict):
            node_type = node.get("type")
            has_object_markers = (
                node_type == "object"
                or "properties" in node
                or "required" in node
                or "additionalProperties" in node
            )
            if has_object_markers:
                yield path, node


@pytest.mark.parametrize("schema_type", APPRAISAL_SCHEMA_TYPES)
def test_appraisal_schemas_marked_compatible(schema_type: str):
    """validate_schema_compatibility should deem appraisal schemas safe to send to OpenAI."""
    schema = load_schema(schema_type)
    compatibility = validate_schema_compatibility(schema)
    assert compatibility["compatible"] is True, f"{schema_type} schema exceeds size limits"


@pytest.mark.parametrize(
    ("schema_name", "schema_fixture_name"),
    [("appraisal", "appraisal_schema"), ("appraisal_validation", "appraisal_validation_schema")],
)
def test_all_objects_disallow_additional_properties(
    request: pytest.FixtureRequest, schema_name: str, schema_fixture_name: str
):
    """Every object definition must explicitly set additionalProperties: false."""
    schema = request.getfixturevalue(schema_fixture_name)
    violations: list[str] = []

    for path, node in _iter_object_nodes(schema):
        additional = node.get("additionalProperties")
        # OpenAI strict mode requires additionalProperties to be False
        if additional is not False:
            violations.append(f"{schema_name}:{path} missing additionalProperties:false")

    assert not violations, "Objects missing additionalProperties=false:\n" + "\n".join(
        violations[:10]
    )


@pytest.mark.parametrize(
    ("schema_name", "schema_fixture_name"),
    [("appraisal", "appraisal_schema"), ("appraisal_validation", "appraisal_validation_schema")],
)
def test_required_fields_have_definitions(
    request: pytest.FixtureRequest, schema_name: str, schema_fixture_name: str
):
    """All required fields should have a corresponding entry in properties."""
    schema = request.getfixturevalue(schema_fixture_name)
    missing: list[str] = []

    for path, node in _iter_object_nodes(schema):
        required_fields = node.get("required", [])
        if not required_fields:
            continue

        properties = node.get("properties", {})
        for field in required_fields:
            if field not in properties:
                missing.append(f"{schema_name}:{path} -> missing property definition for '{field}'")

    assert not missing, "Required fields missing property definitions:\n" + "\n".join(missing[:10])


@pytest.mark.parametrize(
    ("schema_name", "schema_fixture_name"),
    [("appraisal", "appraisal_schema"), ("appraisal_validation", "appraisal_validation_schema")],
)
def test_required_fields_are_not_nullable(
    request: pytest.FixtureRequest, schema_name: str, schema_fixture_name: str
):
    """
    OpenAI structured outputs do not allow nullable required fields.

    Ensure any required field does not include 'null' in its type definition.
    """
    schema = request.getfixturevalue(schema_fixture_name)
    nullable_required: list[str] = []

    for path, node in _iter_object_nodes(schema):
        required_fields = node.get("required", [])
        if not required_fields:
            continue

        properties = node.get("properties", {})
        for field in required_fields:
            prop = properties.get(field)
            if not isinstance(prop, dict):
                continue
            prop_type = prop.get("type")

            if isinstance(prop_type, list) and "null" in prop_type:
                nullable_required.append(f"{schema_name}:{path}.{field}")
            elif prop_type == "null":
                nullable_required.append(f"{schema_name}:{path}.{field}")

    assert not nullable_required, "Required fields cannot be nullable:\n" + "\n".join(
        nullable_required[:10]
    )
