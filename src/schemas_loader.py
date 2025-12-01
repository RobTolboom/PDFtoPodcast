# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

# schemas_loader.py
"""
JSON Schema loading utilities for the PDFtoPodcast extraction pipeline.

This module provides functions to load and manage bundled JSON schemas for structured
data extraction. Each publication type has a corresponding bundled schema that
enforces the expected output structure.

Bundled schemas are self-contained (all $refs resolved) and ready for use with
LLM structured outputs like OpenAI's response_format with json_schema.

Example:
    >>> from src.schemas_loader import load_schema
    >>> schema = load_schema("interventional_trial")
    >>> # Use schema with OpenAI structured outputs
    >>> llm.generate_json_with_schema(prompt, schema)
"""

import json
import logging
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)

# Base directory for schemas
SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"

# Map publication types to bundled schema files (single source of truth)
SCHEMA_MAPPING = {
    "interventional_trial": "interventional_trial_bundled.json",
    "observational_analytic": "observational_analytic_bundled.json",
    "evidence_synthesis": "evidence_synthesis_bundled.json",
    "prediction_prognosis": "prediction_prognosis_bundled.json",
    "editorials_opinion": "editorials_opinion_bundled.json",
    # Pipeline schemas (classification, validation, and appraisal outputs)
    "classification": "classification.schema.json",
    "validation": "validation.schema.json",
    "appraisal": "appraisal.schema.json",
    "appraisal_validation": "appraisal_validation.schema.json",
    # Report schemas (report generation outputs)
    "report": "report.schema.json",
    "report_validation": "report_validation.schema.json",
    # Podcast schemas
    "podcast": "podcast.schema.json",
}


class SchemaLoadError(Exception):
    """Error loading schema files"""

    pass


# Cache for loaded schemas to avoid repeated file I/O
_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}


def load_schema(publication_type: str) -> dict[str, Any]:
    """
    Load the bundled JSON schema for a specific publication type.

    The schema is cached after first load for performance. Bundled schemas
    contain all definitions inline (no external $refs) and are ready for
    use with LLM structured outputs.

    Args:
        publication_type: One of: interventional_trial, observational_analytic,
                         evidence_synthesis, prediction_prognosis, editorials_opinion,
                         classification, validation, appraisal, appraisal_validation,
                         report, report_validation, podcast

    Returns:
        Dictionary containing the JSON schema (Draft 2020-12 format)

    Raises:
        SchemaLoadError: If schema file not found or invalid JSON

    Example:
        >>> schema = load_schema("interventional_trial")
        >>> schema['title']
        'Clinical Trial Extraction (Interventional Studies)'
    """
    if publication_type not in SCHEMA_MAPPING:
        raise SchemaLoadError(
            f"Unknown publication type: {publication_type}. "
            f"Supported: {list(SCHEMA_MAPPING.keys())}"
        )

    # Check cache first
    if publication_type in _SCHEMA_CACHE:
        logger.debug(f"Using cached schema for {publication_type}")
        return _SCHEMA_CACHE[publication_type]

    schema_file = SCHEMAS_DIR / SCHEMA_MAPPING[publication_type]

    if not schema_file.exists():
        raise SchemaLoadError(f"Schema file not found: {schema_file}")

    try:
        with open(schema_file, encoding="utf-8") as f:
            schema = cast(dict[str, Any], json.load(f))

        # Cache the schema
        _SCHEMA_CACHE[publication_type] = schema
        logger.info(f"Loaded schema for {publication_type} from {schema_file.name}")

        return schema

    except json.JSONDecodeError as e:
        raise SchemaLoadError(f"Invalid JSON in schema file {schema_file}: {e}") from e
    except Exception as e:
        raise SchemaLoadError(f"Error reading schema file {schema_file}: {e}") from e


def get_schema_info(publication_type: str) -> dict[str, Any]:
    """
    Get metadata about a schema without loading the full schema.

    Args:
        publication_type: The publication type identifier

    Returns:
        Dictionary with schema metadata (title, version, required fields, etc.)
    """
    schema = load_schema(publication_type)

    return {
        "title": schema.get("title", "Unknown"),
        "schema_id": schema.get("$id", "Unknown"),
        "required_fields": schema.get("required", []),
        "description": schema.get("description", ""),
    }


def validate_schema_compatibility(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Check if a schema is compatible with OpenAI structured outputs.

    OpenAI has specific requirements and limitations for structured outputs:
    - Maximum schema size limits (~20k tokens)
    - External file references not supported
    - additionalProperties should be explicitly set

    Note: Internal $refs (like #/$defs/...) are supported and commonly used
    in bundled schemas.

    Args:
        schema: The JSON schema to validate

    Returns:
        Dictionary with compatibility info:
        {
            "compatible": bool,
            "warnings": list of warning messages,
            "estimated_tokens": int (rough estimate)
        }

    Example:
        >>> compatibility = validate_schema_compatibility(schema)
        >>> if not compatibility['compatible']:
        ...     print("Schema may be too large for OpenAI")
    """
    warnings = []
    schema_str = json.dumps(schema)
    estimated_tokens = len(schema_str) // 4  # Rough estimate: 4 chars per token

    # Check schema size (OpenAI has limits, typically ~20k tokens)
    if estimated_tokens > 15000:
        warnings.append(
            f"Schema is large ({estimated_tokens} estimated tokens). "
            "May hit OpenAI limits or reduce available context."
        )

    # Check for additionalProperties
    if schema.get("additionalProperties") is None:
        warnings.append(
            "Schema doesn't specify 'additionalProperties'. "
            "OpenAI structured outputs work best with 'additionalProperties: false'"
        )

    # Check for external file references (internal refs like #/$defs/ are OK)
    schema_str_lower = schema_str.lower()
    # Look for refs to external files (e.g., "common.schema.json#/$defs/...")
    if '".json' in schema_str_lower or "'.json" in schema_str_lower:
        warnings.append(
            "Schema contains external file references. "
            "Use bundled schemas instead (all $refs should be internal like #/$defs/...)"
        )

    # Check for potentially unsupported advanced features
    # Note: allOf, anyOf, oneOf are supported but can be complex
    if any(keyword in schema_str_lower for keyword in ["patternproperties", "dependencies"]):
        warnings.append(
            "Schema contains advanced features (patternProperties, dependencies). "
            "These may work but could cause issues with strict mode."
        )

    compatible = estimated_tokens < 20000  # Conservative limit

    return {
        "compatible": compatible,
        "warnings": warnings,
        "estimated_tokens": estimated_tokens,
    }


def get_all_available_schemas() -> dict[str, dict[str, Any]]:
    """
    Get information about all available schemas.

    Returns:
        Dictionary mapping publication types to their schema info
    """
    schemas_info = {}
    for pub_type in SCHEMA_MAPPING.keys():
        try:
            schemas_info[pub_type] = get_schema_info(pub_type)
        except SchemaLoadError as e:
            logger.warning(f"Could not load schema for {pub_type}: {e}")
            schemas_info[pub_type] = {"error": str(e)}

    return schemas_info


def clear_schema_cache():
    """Clear the schema cache. Useful for development/testing."""
    global _SCHEMA_CACHE
    _SCHEMA_CACHE.clear()
    logger.info("Schema cache cleared")


def get_supported_publication_types() -> list[str]:
    """
    Get list of all supported publication types.

    Returns:
        List of publication type identifiers

    Example:
        >>> types = get_supported_publication_types()
        >>> 'interventional_trial' in types
        True
    """
    return list(SCHEMA_MAPPING.keys())


def schema_exists(publication_type: str) -> bool:
    """
    Check if a schema file exists for the given publication type.

    This is a lightweight check that doesn't load the schema.

    Args:
        publication_type: The publication type to check

    Returns:
        True if schema file exists, False otherwise

    Example:
        >>> schema_exists("interventional_trial")
        True
        >>> schema_exists("invalid_type")
        False
    """
    if publication_type not in SCHEMA_MAPPING:
        return False

    schema_file = SCHEMAS_DIR / SCHEMA_MAPPING[publication_type]
    return schema_file.exists()
