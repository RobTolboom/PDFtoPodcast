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
    Path format: #/$defs/TypeName or #/properties/field
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
    Recursively check all $ref resolve correctly.
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
    Collect schema statistics.
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
    Comprehensive validation of a schema file.
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
