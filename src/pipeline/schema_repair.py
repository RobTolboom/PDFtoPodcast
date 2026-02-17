# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Deterministic post-correction schema repair.

Runs between the LLM correction call and schema validation to fix common,
predictable structural issues that the LLM introduces during correction:

1. Array items that are strings/IDs instead of objects (restore from original)
2. Properties not allowed by the schema (strip when additionalProperties=false)

This avoids wasting a correction retry on issues that can be fixed deterministically.
"""

import logging
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)


def repair_schema_violations(
    data: dict[str, Any],
    schema: dict[str, Any],
    original: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Apply deterministic fixes for common LLM output structural issues.

    Runs AFTER the LLM correction but BEFORE schema validation.
    Only fixes predictable structural problems; does not alter data content.

    Args:
        data: The corrected extraction JSON from the LLM
        schema: The JSON schema (bundled, with all $ref resolved)
        original: The original extraction (pre-correction) for restoring array items

    Returns:
        Repaired copy of data (original is not modified)
    """
    result = deepcopy(data)

    # Resolve top-level schema properties (handle $defs inlining in bundled schemas)
    schema_props = schema.get("properties", {})
    schema_defs = schema.get("$defs", {})

    result = _repair_object(result, schema_props, schema_defs, schema, original)

    # Remove disallowed top-level properties
    if schema.get("additionalProperties") is False:
        allowed_keys = set(schema_props.keys())
        disallowed = [k for k in result if k not in allowed_keys]
        for key in disallowed:
            logger.info("Removing disallowed top-level property: %s", key)
            del result[key]

    return result


def _resolve_ref(ref: str, schema_defs: dict[str, Any]) -> dict[str, Any]:
    """Resolve a $ref to its definition within the schema."""
    # Handle "#/$defs/Name" format
    if ref.startswith("#/$defs/"):
        def_name = ref[len("#/$defs/") :]
        return schema_defs.get(def_name, {})
    return {}


def _get_item_schema(prop_schema: dict[str, Any], schema_defs: dict[str, Any]) -> dict[str, Any]:
    """Get the resolved schema for array items."""
    items_schema = prop_schema.get("items", {})
    if "$ref" in items_schema:
        return _resolve_ref(items_schema["$ref"], schema_defs)
    return items_schema


def _get_id_field_for_array(item_schema: dict[str, Any]) -> str | None:
    """Determine the ID field for an array item schema (e.g., outcome_id, arm_id)."""
    props = item_schema.get("properties", {})
    # Common ID field patterns in medical extraction schemas
    id_candidates = [k for k in props if k.endswith("_id") and k != "study_id"]
    if len(id_candidates) == 1:
        return id_candidates[0]
    # Prefer the most specific one (e.g., outcome_id over study_id)
    for candidate in [
        "outcome_id",
        "arm_id",
        "comparison_id",
        "exposure_id",
        "group_id",
        "predictor_id",
        "dataset_id",
        "model_id",
        "figure_id",
        "table_id",
        "claim_id",
        "intervention_id",
    ]:
        if candidate in props:
            return candidate
    return id_candidates[0] if id_candidates else None


def _repair_object(
    obj: dict[str, Any],
    schema_props: dict[str, Any],
    schema_defs: dict[str, Any],
    root_schema: dict[str, Any],
    original: dict[str, Any] | None,
) -> dict[str, Any]:
    """Recursively repair an object according to its schema properties."""
    for key, prop_schema in schema_props.items():
        if key not in obj:
            continue

        # Resolve $ref if present
        resolved = prop_schema
        if "$ref" in prop_schema:
            resolved = _resolve_ref(prop_schema["$ref"], schema_defs)
            if not resolved:
                continue

        prop_type = resolved.get("type")

        if prop_type == "array":
            obj[key] = _repair_array(
                obj[key], resolved, schema_defs, original.get(key) if original else None
            )
        elif prop_type == "object":
            if isinstance(obj[key], dict):
                nested_props = resolved.get("properties", {})
                original_nested = original.get(key) if original else None
                obj[key] = _repair_object(
                    obj[key], nested_props, schema_defs, root_schema, original_nested
                )
                # Remove disallowed nested properties
                if resolved.get("additionalProperties") is False and nested_props:
                    allowed = set(nested_props.keys())
                    disallowed = [k for k in obj[key] if k not in allowed]
                    for dk in disallowed:
                        logger.info("Removing disallowed property: %s.%s", key, dk)
                        del obj[key][dk]

    return obj


def _repair_array(
    arr: Any,
    array_schema: dict[str, Any],
    schema_defs: dict[str, Any],
    original_arr: Any | None,
) -> list[Any]:
    """Repair an array: restore string items to objects if schema expects objects."""
    if not isinstance(arr, list):
        return arr

    item_schema = _get_item_schema(array_schema, schema_defs)
    if not item_schema:
        return arr

    item_type = item_schema.get("type")

    # Only repair if schema expects objects but we got non-objects
    if item_type != "object":
        return arr

    id_field = _get_id_field_for_array(item_schema)
    if not id_field:
        return arr

    # Build lookup from original extraction
    original_lookup: dict[str, dict] = {}
    if original_arr and isinstance(original_arr, list):
        for item in original_arr:
            if isinstance(item, dict) and id_field in item:
                original_lookup[str(item[id_field])] = item

    repaired = []
    for item in arr:
        if isinstance(item, dict):
            # Item is already an object - recurse into it for nested repairs
            nested_props = item_schema.get("properties", {})
            item = _repair_object(item, nested_props, schema_defs, {}, None)
            # Remove disallowed properties within array items
            if item_schema.get("additionalProperties") is False and nested_props:
                allowed = set(nested_props.keys())
                disallowed = [k for k in item if k not in allowed]
                for dk in disallowed:
                    logger.info("Removing disallowed property in array item: %s", dk)
                    del item[dk]
            repaired.append(item)
        elif isinstance(item, str):
            # Item is a string but should be an object - try to restore
            if item in original_lookup:
                logger.info("Restored array item from original: %s=%s", id_field, item)
                repaired.append(deepcopy(original_lookup[item]))
            else:
                # Cannot restore - keep the string (will fail validation,
                # but that's better than silently dropping data)
                logger.warning("Cannot restore array item %s=%s from original", id_field, item)
                repaired.append(item)
        else:
            repaired.append(item)

    return repaired
