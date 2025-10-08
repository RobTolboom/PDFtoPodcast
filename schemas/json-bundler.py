#!/usr/bin/env python3
"""
JSON Schema Bundler for Medical Literature Extraction Schemas

This script creates standalone, self-contained versions of extraction schemas that
reference external common definitions. It transforms modular schema architectures
into monolithic ones while preserving all functionality.

Purpose:
    Converts extraction schemas with external $ref dependencies into bundled schemas
    where all referenced definitions are embedded locally. This is useful for:
    - Production deployments where external file dependencies aren't desired
    - Schema distribution requiring self-contained files
    - OpenAI API structured outputs requiring standalone schemas
    - Validation libraries that don't support external $ref resolution

Example Usage:
    # Bundle all extraction schemas in current directory
    python json-bundler.py

    # Bundle schemas in specific directory
    python json-bundler.py --directory /path/to/schemas

Input Requirements:
    - common.schema.json: Contains shared $defs referenced by extraction schemas
    - *_trial.schema.json, *_analytic.schema.json, etc.: Extraction schemas with
      external references to common.schema.json

Excluded from bundling:
    - classification.schema.json: Self-contained pipeline schema (no external refs)
    - validation.schema.json: Self-contained pipeline schema (no external refs)

Output:
    - *_bundled.json: Self-contained extraction schemas with embedded common definitions

Algorithm Overview:
    1. Discover all *.schema.json files (excluding common.schema.json)
    2. For each schema:
       a. Parse and find all external references to common schema
       b. Extract referenced definitions from common.schema.json
       c. Embed definitions into the schema's local $defs section
       d. Rewrite external references to local #/$defs/ references
       e. Output bundled schema as *_bundled.json

Author: Rob Tolboom
Version: 2.0 - Enhanced for batch processing
"""

import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterator, List


def get_common_id(common_schema: Dict[str, Any]) -> str:
    """
    Extract the $id from the common schema file.

    Args:
        common_schema: Parsed JSON schema dictionary containing the common definitions

    Returns:
        str: The schema ID used for external references, defaults to "common.schema.json"

    Example:
        >>> schema = {"$id": "https://example.org/common.schema.json"}
        >>> get_common_id(schema)
        'https://example.org/common.schema.json'
    """
    return common_schema.get("$id", "common.schema.json")


def find_common_refs(node: Any, common_ref_rx: re.Pattern) -> Iterator[str]:
    """
    Recursively find all definition names from common schema that are referenced.

    This function traverses a JSON schema structure recursively and identifies all
    external references to the common schema. It uses a regex pattern to match
    references like "common.schema.json#/$defs/DefinitionName" and extracts
    the definition name.

    Args:
        node: JSON schema node (dict, list, or primitive) to search for references
        common_ref_rx: Compiled regex pattern to match external common schema references

    Yields:
        str: Definition names from common schema that are referenced (e.g., "SourceRef", "Metadata")

    Example:
        >>> import re
        >>> schema = {"properties": {"source": {"$ref": "common.schema.json#/$defs/SourceRef"}}}
        >>> pattern = re.compile(r"^common\\.schema\\.json#/\\$defs/([^/]+)$")
        >>> list(find_common_refs(schema, pattern))
        ['SourceRef']
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                m = common_ref_rx.match(v)
                if m:
                    yield m.group(1)  # Extract definition name from regex group
            else:
                yield from find_common_refs(v, common_ref_rx)
    elif isinstance(node, list):
        for item in node:
            yield from find_common_refs(item, common_ref_rx)


def rewrite_refs_to_local(node: Any, common_ref_rx: re.Pattern) -> Any:
    """
    Replace external common schema references with local #/$defs/<name> references.

    This function recursively traverses a JSON schema and converts all external
    references to the common schema into local references within the same schema.
    For example: "common.schema.json#/$defs/SourceRef" becomes "#/$defs/SourceRef"

    Args:
        node: JSON schema node (dict, list, or primitive) to process
        common_ref_rx: Compiled regex pattern to match external common schema references

    Returns:
        Any: Processed schema with rewritten references, maintaining original structure

    Example:
        >>> import re
        >>> schema = {"$ref": "common.schema.json#/$defs/SourceRef"}
        >>> pattern = re.compile(r"^common\\.schema\\.json#/\\$defs/([^/]+)$")
        >>> rewrite_refs_to_local(schema, pattern)
        {'$ref': '#/$defs/SourceRef'}
    """
    if isinstance(node, dict):
        new = {}
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                m = common_ref_rx.match(v)
                if m:
                    # Convert external reference to local reference
                    new[k] = f"#/$defs/{m.group(1)}"
                else:
                    new[k] = rewrite_refs_to_local(v, common_ref_rx)
            else:
                new[k] = rewrite_refs_to_local(v, common_ref_rx)
        return new
    elif isinstance(node, list):
        return [rewrite_refs_to_local(x, common_ref_rx) for x in node]
    return node  # Return primitives unchanged


def bundle_schema(
    schema: Dict[str, Any], common_schema: Dict[str, Any], common_ref_rx: re.Pattern
) -> Dict[str, Any]:
    """
    Bundle a schema with its common dependencies into a self-contained schema.

    This is the main bundling function that combines a schema with its external
    dependencies from the common schema. It performs the complete bundling process:
    finding dependencies, embedding definitions, and rewriting references.

    Args:
        schema: The source schema dictionary to bundle
        common_schema: The common schema containing shared definitions
        common_ref_rx: Compiled regex pattern to match external common schema references

    Returns:
        Dict[str, Any]: A self-contained schema with all dependencies embedded

    Raises:
        KeyError: If a referenced definition is not found in the common schema

    Example:
        >>> # Schema with external reference
        >>> schema = {"properties": {"source": {"$ref": "common.schema.json#/$defs/SourceRef"}}}
        >>> common = {"$defs": {"SourceRef": {"type": "object"}}}
        >>> pattern = re.compile(r"^common\\.schema\\.json#/\\$defs/([^/]+)$")
        >>> bundled = bundle_schema(schema, common, pattern)
        >>> # Result: schema with SourceRef embedded and reference rewritten to local
    """
    # Create a deep copy to avoid modifying the original
    bundled = deepcopy(schema)

    # Collect all needed definitions from common schema
    needed = set(find_common_refs(bundled, common_ref_rx))

    # Create or merge with existing local $defs section
    bundled.setdefault("$defs", {})
    defs = bundled["$defs"]

    # Embed each needed definition from common schema
    for name in sorted(needed):
        if name in defs:
            continue  # Skip if definition already exists locally
        if name not in common_schema.get("$defs", {}):
            raise KeyError(f"Definition '{name}' not found in common schema")
        # Deep copy the definition to avoid reference issues
        defs[name] = deepcopy(common_schema["$defs"][name])

    # Rewrite all external references to local references
    bundled = rewrite_refs_to_local(bundled, common_ref_rx)

    return bundled


def discover_schema_files(directory: str = ".") -> List[Path]:
    """
    Discover extraction schema files that need bundling.

    Scans the specified directory for JSON schema files following the naming
    convention *.schema.json and excludes schemas that don't need bundling:
    - common.schema.json: Contains shared definitions (source, not target)
    - classification.schema.json: Self-contained pipeline schema
    - validation.schema.json: Self-contained pipeline schema

    Only extraction schemas with external references to common.schema.json
    are included for bundling.

    Args:
        directory: Path to directory containing schema files (default: current directory)

    Returns:
        List[Path]: Sorted list of schema file paths ready for bundling

    Example:
        >>> files = discover_schema_files("/path/to/schemas")
        >>> [f.name for f in files]
        ['interventional_trial.schema.json', 'observational_analytic.schema.json', ...]
    """
    schema_dir = Path(directory)
    schema_files = []

    # Schemas to skip: common definitions + self-contained pipeline schemas
    skip_schemas = {
        "common.schema.json",  # Shared definitions (not a bundling target)
        "classification.schema.json",  # Self-contained, no external refs
        "validation.schema.json",  # Self-contained, no external refs
    }

    # Find all schema files using glob pattern
    for file_path in schema_dir.glob("*.schema.json"):
        if file_path.name not in skip_schemas:
            schema_files.append(file_path)

    return sorted(schema_files)  # Sort for consistent processing order


def bundle_all_schemas(directory: str = ".") -> bool:
    """
    Bundle all schemas in the given directory with comprehensive error handling.

    This is the main orchestration function that handles the complete bundling
    workflow for all schemas in a directory. It loads the common schema, discovers
    target schemas, and processes each one with detailed progress reporting.

    Args:
        directory: Path to directory containing schema files (default: current directory)

    Returns:
        bool: True if all schemas were successfully bundled, False if any failed

    Example:
        >>> success = bundle_all_schemas("/path/to/schemas")
        Using common schema ID: common.schema.json
        Found 5 schema(s) to bundle:
          - interventional_trial.schema.json
          - ...
        🎉 Successfully bundled 5/5 schemas
        >>> success
        True
    """
    schema_dir = Path(directory)
    common_path = schema_dir / "common.schema.json"

    # Load and validate common schema
    if not common_path.exists():
        print(f"Error: common.schema.json not found in {schema_dir}")
        return False

    try:
        # Load common schema with explicit UTF-8 encoding
        common = json.loads(common_path.read_text(encoding="utf-8"))
        common_id = get_common_id(common)

        # Build regex pattern to match external references to common schema
        # Pattern matches: "<common_id>#/$defs/<definition_name>"
        common_ref_rx = re.compile(rf"^{re.escape(common_id)}#/\$defs/([^/]+)$")

        print(f"Using common schema ID: {common_id}")

    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading common schema: {e}")
        return False

    # Discover all bundleable schema files
    schema_files = discover_schema_files(directory)

    if not schema_files:
        print(f"No schema files found in {schema_dir}")
        return False

    print(f"Found {len(schema_files)} schema(s) to bundle:")
    for file_path in schema_files:
        print(f"  - {file_path.name}")

    # Process each schema with individual error handling
    success_count = 0
    for schema_path in schema_files:
        try:
            print(f"\nProcessing {schema_path.name}...")

            # Load and parse the target schema
            schema = json.loads(schema_path.read_text(encoding="utf-8"))

            # Perform the bundling process
            bundled = bundle_schema(schema, common, common_ref_rx)

            # Generate output filename by replacing .schema with _bundled
            base_name = schema_path.stem.replace(".schema", "")
            output_path = schema_dir / f"{base_name}_bundled.json"

            # Write the bundled schema with proper formatting
            output_path.write_text(
                json.dumps(bundled, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            print(f"  ✅ Created: {output_path.name}")
            success_count += 1

        except (json.JSONDecodeError, IOError, KeyError) as e:
            print(f"  ❌ Error processing {schema_path.name}: {e}")
            continue  # Continue with next schema despite this failure

    # Report final results
    print(f"\n🎉 Successfully bundled {success_count}/{len(schema_files)} schemas")
    return success_count == len(schema_files)


if __name__ == "__main__":
    """
    Command-line interface for the JSON Schema Bundler.

    Provides a simple CLI for bundling schemas with optional directory specification.
    Returns appropriate exit codes for use in scripts and CI/CD pipelines.

    Exit codes:
        0: All schemas bundled successfully
        1: One or more schemas failed to bundle or other error occurred
    """
    import argparse

    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(
        description="Bundle JSON schemas with common definitions",
        epilog="""
Examples:
  python json-bundler.py                    # Bundle schemas in current directory
  python json-bundler.py -d /path/schemas   # Bundle schemas in specific directory

Output:
  Creates *_bundled.json files for each input *.schema.json file (except common.schema.json)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--directory",
        "-d",
        default=".",
        help="Directory containing schema files (default: current directory)",
    )

    # Parse arguments and execute bundling
    args = parser.parse_args()

    # Run the bundling process and exit with appropriate code
    success = bundle_all_schemas(args.directory)
    sys.exit(0 if success else 1)
