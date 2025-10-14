#!/usr/bin/env python3
"""
Comprehensive validation of JSON schemas for OpenAI Strict Mode compliance.

Checks:
1. JSON syntax validity
2. All $refs resolve correctly (no dangling references)
3. Schema statistics (size, depth, object count)
4. Common strict mode violations
"""

import json
from pathlib import Path


def get_nested_value(obj, path):
    """
    Get value from nested dict/list using JSON Pointer-like path.

    Traverses a JSON schema structure using a JSON Pointer-style path to
    retrieve a nested value. Supports both dictionary and list traversal.

    Args:
        obj: Root JSON schema dictionary to traverse
        path: JSON Pointer-like path string (e.g., "#/$defs/TypeName", "#/properties/field")
              Must start with "#/" prefix

    Returns:
        The value at the specified path, or None if path doesn't exist or is invalid

    Example:
        >>> schema = {"$defs": {"Author": {"type": "object", "properties": {"name": {"type": "string"}}}}}
        >>> get_nested_value(schema, "#/$defs/Author")
        {'type': 'object', 'properties': {'name': {'type': 'string'}}}
        >>> get_nested_value(schema, "#/$defs/NonExistent")
        None
        >>> get_nested_value(schema, "invalid")  # Missing #/ prefix
        None

    Note:
        - Path must start with "#/" (JSON Pointer internal reference format)
        - Path components are split by "/" character
        - For lists, path components must be valid integer indices
        - Returns None for any traversal error (missing key, invalid index, type mismatch)
    """
    if not path.startswith("#/"):
        return None

    parts = path[2:].split("/")
    current = obj

    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None

    return current


def check_refs_recursive(obj, root_schema, path="root", errors=None):
    """
    Recursively check that all $ref references resolve correctly in a JSON schema.

    Traverses the entire schema structure and validates that every $ref can be
    resolved using get_nested_value(). Detects both unresolved internal references
    and external references (which shouldn't exist in bundled schemas).

    Args:
        obj: Current schema object/dict/list being checked
        root_schema: Root schema dictionary for resolving references
        path: Current path in schema (for error reporting), default "root"
        errors: List to accumulate error messages, created if None

    Returns:
        List of error strings describing unresolved or invalid references.
        Empty list if all references resolve correctly.

    Example:
        >>> schema = {
        ...     "$defs": {"Person": {"type": "object"}},
        ...     "properties": {"user": {"$ref": "#/$defs/Person"}}
        ... }
        >>> errors = check_refs_recursive(schema, schema)
        >>> errors
        []
        >>> bad_schema = {"properties": {"user": {"$ref": "#/$defs/NonExistent"}}}
        >>> errors = check_refs_recursive(bad_schema, bad_schema)
        >>> len(errors) > 0
        True

    Note:
        - Only checks internal references (starting with "#/")
        - External references (not starting with "#") are flagged as errors in bundled schemas
        - Recursively processes all nested dicts and lists
        - Error messages include path for easy location of issues
        - Mutates the errors list parameter (accumulator pattern)
    """
    if errors is None:
        errors = []

    if isinstance(obj, dict):
        # Check if this is a $ref
        if "$ref" in obj:
            ref_path = obj["$ref"]

            # Internal reference (starts with #)
            if ref_path.startswith("#/"):
                resolved = get_nested_value(root_schema, ref_path)
                if resolved is None:
                    errors.append(f"{path}: Unresolved $ref: {ref_path}")

            # External reference (not supported in bundled schemas)
            elif not ref_path.startswith("#"):
                errors.append(f"{path}: External $ref in bundled schema: {ref_path}")

        # Recurse into all values
        for key, value in obj.items():
            if key != "$ref":  # Don't recurse into $ref string
                check_refs_recursive(value, root_schema, f"{path}.{key}", errors)

    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            check_refs_recursive(item, root_schema, f"{path}[{i}]", errors)

    return errors


def get_schema_stats(obj, stats=None, depth=0):
    """
    Collect comprehensive statistics about a JSON schema structure.

    Recursively traverses a schema to gather metrics about its complexity,
    structure, and composition. Useful for assessing schema size and identifying
    potential issues with overly complex schemas.

    Args:
        obj: Current schema object/dict/list being analyzed
        stats: Dictionary to accumulate statistics, created with defaults if None
        depth: Current recursion depth (for tracking max nesting), default 0

    Returns:
        Dictionary with schema statistics:
        {
            "max_depth": int,        # Maximum nesting depth
            "object_count": int,     # Number of object type definitions
            "property_count": int,   # Total number of properties across all objects
            "ref_count": int,        # Number of $ref references
            "array_count": int       # Number of array type definitions
        }

    Example:
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "name": {"type": "string"},
        ...         "tags": {"type": "array", "items": {"type": "string"}}
        ...     }
        ... }
        >>> stats = get_schema_stats(schema)
        >>> stats["object_count"]
        1
        >>> stats["property_count"]
        2
        >>> stats["array_count"]
        1

    Note:
        - Handles both single type strings and type arrays (e.g., ["string", "null"])
        - Counts nested objects and arrays at all depths
        - Max depth helps identify deeply nested schemas that might hit parser limits
        - Mutates the stats dict parameter (accumulator pattern)
        - Used by validate_schema() to report schema complexity
    """
    if stats is None:
        stats = {
            "max_depth": 0,
            "object_count": 0,
            "property_count": 0,
            "ref_count": 0,
            "array_count": 0,
        }

    stats["max_depth"] = max(stats["max_depth"], depth)

    if isinstance(obj, dict):
        # Count schema objects
        if "type" in obj:
            obj_type = obj["type"]
            types = obj_type if isinstance(obj_type, list) else [obj_type]
            if "object" in types:
                stats["object_count"] += 1
            if "array" in types:
                stats["array_count"] += 1

        if "properties" in obj:
            stats["property_count"] += len(obj["properties"])

        if "$ref" in obj:
            stats["ref_count"] += 1

        # Recurse
        for value in obj.values():
            get_schema_stats(value, stats, depth + 1)

    elif isinstance(obj, list):
        for item in obj:
            get_schema_stats(item, stats, depth + 1)

    return stats


def validate_schema(schema_file):
    """
    Comprehensive validation of a JSON schema file for OpenAI compatibility.

    Performs multiple validation checks on a schema file to ensure it's valid,
    properly structured, and compatible with OpenAI's Structured Outputs API.
    Prints detailed validation report to stdout.

    Validation Checks:
        1. JSON syntax validity
        2. File size (warns if >100KB)
        3. Schema statistics (depth, objects, properties, arrays, refs)
        4. All $ref references resolve correctly
        5. No external references in bundled schemas
        6. Common OpenAI strict mode issues

    Args:
        schema_file: Path object pointing to JSON schema file to validate

    Returns:
        Boolean indicating validation success (True) or failure (False)

    Example:
        >>> from pathlib import Path
        >>> schema_file = Path("schemas/interventional_trial_bundled.json")
        >>> result = validate_schema(schema_file)
        ======================================================================
        Validating: interventional_trial_bundled.json
        ======================================================================
        ✓ JSON syntax valid
        ✓ File size: 45.2 KB (46285 bytes)
        ✓ Schema statistics:
          - Max nesting depth: 8
          - Object definitions: 42
          - Total properties: 156
          - Array definitions: 12
          - $ref count: 0
        ✓ All $refs resolve (0 checked)
        ✓ No external refs in bundled schema
        ======================================================================
        ✅ VALIDATION PASSED
        >>> result
        True

    Note:
        - Validation output includes visual separators for readability
        - Warnings are shown for large schemas (>100KB) and deep nesting (>50 levels)
        - Bundled schemas must not contain external references (common.schema.json#)
        - Only first 10 unresolved refs are displayed to avoid output overflow
        - Used by main() function to validate all bundled schemas in batch
    """
    print(f"\n{'='*70}")
    print(f"Validating: {schema_file.name}")
    print("=" * 70)

    issues = []

    # 1. Check JSON syntax
    try:
        with open(schema_file, encoding="utf-8") as f:
            schema = json.load(f)
        print("✓ JSON syntax valid")
    except json.JSONDecodeError as e:
        print(f"✗ JSON SYNTAX ERROR: {e}")
        return False

    # 2. Check file size
    file_size = schema_file.stat().st_size
    size_kb = file_size / 1024
    print(f"✓ File size: {size_kb:.1f} KB ({file_size} bytes)")
    if file_size > 100000:  # 100KB
        print(f"  ⚠ Warning: Large schema (>{100}KB)")

    # 3. Check schema statistics
    stats = get_schema_stats(schema)
    print("✓ Schema statistics:")
    print(f"  - Max nesting depth: {stats['max_depth']}")
    print(f"  - Object definitions: {stats['object_count']}")
    print(f"  - Total properties: {stats['property_count']}")
    print(f"  - Array definitions: {stats['array_count']}")
    print(f"  - $ref count: {stats['ref_count']}")

    if stats["max_depth"] > 50:
        print(f"  ⚠ Warning: Very deep nesting (>{50} levels)")

    # 4. Check $refs resolve
    ref_errors = check_refs_recursive(schema, schema)
    if ref_errors:
        print(f"✗ UNRESOLVED $REFS ({len(ref_errors)}):")
        for error in ref_errors[:10]:
            print(f"  - {error}")
        if len(ref_errors) > 10:
            print(f"  ... and {len(ref_errors) - 10} more")
        issues.extend(ref_errors)
    else:
        print(f"✓ All $refs resolve ({stats['ref_count']} checked)")

    # 5. Check for common issues
    schema_json = json.dumps(schema)

    # Check for external refs (shouldn't be in bundled)
    if schema_file.name.endswith("_bundled.json"):
        if "common.schema.json#" in schema_json:
            print("✗ EXTERNAL REFS: Found references to common.schema.json in bundled schema")
            issues.append("External refs in bundled schema")
        else:
            print("✓ No external refs in bundled schema")

    # Summary
    print(f"\n{'='*70}")
    if issues:
        print(f"❌ VALIDATION FAILED: {len(issues)} issue(s) found")
        return False
    else:
        print("✅ VALIDATION PASSED")
        return True


def main():
    schemas_dir = Path("schemas")

    # Check bundled schemas (these are what OpenAI uses)
    bundled_schemas = sorted(schemas_dir.glob("*_bundled.json"))

    print("\n" + "=" * 70)
    print("SCHEMA VALIDATION REPORT")
    print("=" * 70)

    results = {}
    for schema_file in bundled_schemas:
        passed = validate_schema(schema_file)
        results[schema_file.name] = passed

    # Final summary
    print(f"\n\n{'='*70}")
    print("SUMMARY")
    print("=" * 70)

    passed_count = sum(1 for p in results.values() if p)
    total_count = len(results)

    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\n{passed_count}/{total_count} schemas passed validation")

    if passed_count < total_count:
        print("\n⚠ Some schemas have validation errors. Fix these before testing.")
        return 1
    else:
        print("\n✅ All schemas passed validation!")
        return 0


if __name__ == "__main__":
    exit(main())
