# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

# validation.py
"""
Validation utilities for extracted data quality assurance.

This module provides functions to validate extracted JSON data against schemas
and perform quality checks on the extraction results. Works in conjunction with
schemas_loader to validate LLM-extracted data.

Validation Workflow:
    1. Schema validation - Check JSON structure and types against JSON schema
    2. Completeness analysis - Measure required vs optional field coverage
    3. Quality scoring - Combine schema compliance + completeness (50/50 weight)

Main Functions:
    - validate_with_schema(): Validate data against JSON schema (requires jsonschema library)
    - validate_extraction_quality(): Comprehensive validation with quality scoring
    - create_validation_report(): Human-readable validation report

Example Usage:
    >>> from src.schemas_loader import load_schema
    >>> from src.validation import validate_extraction_quality
    >>>
    >>> schema = load_schema("interventional_trial")
    >>> results = validate_extraction_quality(extracted_data, schema)
    >>> print(f"Quality: {results['quality_score']:.1%}")
    >>> print(f"Schema compliant: {results['schema_compliant']}")

Note:
    Requires jsonschema>=4.20 library for schema validation.
    Install with: pip install jsonschema
"""

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Error during data validation"""

    pass


def validate_with_schema(
    data: Dict[str, Any], schema: Dict[str, Any], strict: bool = True
) -> Tuple[bool, List[str]]:
    """
    Validate extracted data against a JSON schema.

    Uses jsonschema library with Draft 2020-12 validator to check data
    structure, types, required fields, and constraints.

    Args:
        data: The extracted data dictionary to validate
        schema: The JSON schema to validate against (Draft 2020-12 format)
        strict: If True, raise exception on validation failure. If False, return errors.

    Returns:
        Tuple of (is_valid: bool, errors: List[str])
            - is_valid: True if data passes all schema checks
            - errors: List of validation error messages (empty if valid)

    Raises:
        ValidationError: If strict=True and validation fails

    Example:
        >>> # Strict mode - raises exception on error
        >>> is_valid, errors = validate_with_schema(data, schema, strict=True)
        >>>
        >>> # Non-strict mode - returns errors for inspection
        >>> is_valid, errors = validate_with_schema(data, schema, strict=False)
        >>> if not is_valid:
        ...     print(f"Found {len(errors)} validation errors")
        ...     for error in errors[:5]:
        ...         print(f"  - {error}")
    """
    try:
        import jsonschema
        from jsonschema import Draft202012Validator
    except ImportError:
        logger.error("jsonschema library not installed. Install with: pip install jsonschema")
        if strict:
            raise ValidationError("jsonschema library required for validation")
        return False, ["jsonschema library not available"]

    errors = []

    try:
        # Create validator
        validator = Draft202012Validator(schema)

        # Validate and collect all errors
        validation_errors = sorted(validator.iter_errors(data), key=lambda e: e.path)

        for error in validation_errors:
            # Format error path
            path = "/".join(str(p) for p in error.path) if error.path else "root"
            error_msg = f"{path}: {error.message}"
            errors.append(error_msg)
            logger.warning(f"Schema validation error: {error_msg}")

        if errors:
            if strict:
                raise ValidationError(
                    f"Schema validation failed with {len(errors)} error(s):\n"
                    + "\n".join(errors[:5])
                )
            return False, errors

        logger.info("Schema validation successful")
        return True, []

    except jsonschema.SchemaError as e:
        error_msg = f"Invalid schema: {e.message}"
        logger.error(error_msg)
        if strict:
            raise ValidationError(error_msg)
        return False, [error_msg]


def check_required_fields(
    data: Dict[str, Any], required_fields: List[str]
) -> Tuple[bool, List[str]]:
    """
    Check if all required fields are present in the data.

    Note: This function is largely redundant with schema validation,
    which already checks required fields. Use validate_with_schema() instead
    for comprehensive validation.

    Args:
        data: The data dictionary to check
        required_fields: List of required field names (top-level only)

    Returns:
        Tuple of (all_present: bool, missing_fields: List[str])
            - all_present: True if all required fields exist and are non-None
            - missing_fields: List of missing or None field names
    """
    missing = []
    for field in required_fields:
        if field not in data or data[field] is None:
            missing.append(field)
            logger.warning(f"Missing required field: {field}")

    return len(missing) == 0, missing


def check_data_completeness(data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze data completeness based on schema.

    Calculates how many required and optional fields are filled.
    Completeness score uses weighted formula: required fields count 2x more
    than optional fields (because they're more important).

    Note: Only analyzes top-level properties. Nested objects are not
    recursively analyzed.

    Args:
        data: The extracted data dictionary
        schema: The JSON schema with "required" and "properties" fields

    Returns:
        Dictionary with completeness statistics:
        {
            "required_fields_present": int,  # How many required fields have values
            "required_fields_total": int,    # Total required fields in schema
            "optional_fields_present": int,  # How many optional fields have values
            "optional_fields_total": int,    # Total optional fields in schema
            "completeness_score": float      # Weighted score 0.0-1.0 (required=2x weight)
        }

    Example:
        >>> completeness = check_data_completeness(data, schema)
        >>> print(f"Required: {completeness['required_fields_present']}/{completeness['required_fields_total']}")
        >>> print(f"Completeness: {completeness['completeness_score']:.1%}")
    """
    required_fields = schema.get("required", [])
    all_properties = schema.get("properties", {})

    # Count required fields
    required_present = sum(
        1 for field in required_fields if field in data and data[field] is not None
    )
    required_total = len(required_fields)

    # Count optional fields
    optional_fields = [f for f in all_properties.keys() if f not in required_fields]
    optional_present = sum(
        1 for field in optional_fields if field in data and data[field] is not None
    )
    optional_total = len(optional_fields)

    # Calculate completeness score (weighted: required fields count 2x more than optional)
    total_possible = required_total + optional_total
    if total_possible > 0:
        # Weight required fields 2x more than optional fields
        # Example: 5/5 required + 3/10 optional = (10+3)/(10+10) = 13/20 = 65%
        weighted_present = (required_present * 2) + optional_present
        weighted_total = (required_total * 2) + optional_total
        completeness_score = weighted_present / weighted_total
    else:
        completeness_score = 1.0  # No fields to check = 100% complete

    return {
        "required_fields_present": required_present,
        "required_fields_total": required_total,
        "optional_fields_present": optional_present,
        "optional_fields_total": optional_total,
        "completeness_score": round(completeness_score, 3),
    }


def validate_extraction_quality(
    data: Dict[str, Any], schema: Dict[str, Any], strict: bool = False
) -> Dict[str, Any]:
    """
    Comprehensive quality validation of extracted data.

    Performs two-tier validation:
    1. Schema validation (structure, types, constraints)
    2. Completeness analysis (required vs optional field coverage)

    Quality score is calculated as:
    - 50% schema compliance (pass/fail)
    - 50% completeness (weighted: required=2x, optional=1x)

    Args:
        data: The extracted data to validate
        schema: The JSON schema for validation (Draft 2020-12)
        strict: If True, raise exception on validation failure

    Returns:
        Dictionary with validation results:
        {
            "valid": bool,                    # Overall pass/fail
            "schema_compliant": bool,         # True if passes schema validation
            "validation_errors": List[str],   # List of schema errors (empty if valid)
            "completeness": Dict[str, Any],   # Completeness statistics
            "quality_score": float            # Overall quality 0.0-1.0
        }

    Raises:
        ValidationError: If strict=True and validation fails

    Example:
        >>> from src.schemas_loader import load_schema
        >>> schema = load_schema("interventional_trial")
        >>> results = validate_extraction_quality(extracted_data, schema)
        >>>
        >>> if results['schema_compliant']:
        ...     print(f"✅ Valid! Quality: {results['quality_score']:.1%}")
        ... else:
        ...     print(f"❌ Invalid. Errors: {len(results['validation_errors'])}")
        ...     for error in results['validation_errors'][:3]:
        ...         print(f"  - {error}")
    """
    results = {
        "valid": True,
        "schema_compliant": False,
        "validation_errors": [],
        "completeness": {},
        "quality_score": 0.0,
    }

    # 1. Schema validation
    is_valid, errors = validate_with_schema(data, schema, strict=False)
    results["schema_compliant"] = is_valid
    results["validation_errors"] = errors

    if not is_valid:
        results["valid"] = False
        if strict:
            raise ValidationError(f"Schema validation failed: {errors}")

    # 2. Completeness check
    completeness = check_data_completeness(data, schema)
    results["completeness"] = completeness

    # 3. Calculate overall quality score
    # Schema compliance: 50% weight
    # Completeness: 50% weight
    schema_score = 1.0 if is_valid else 0.0
    completeness_score = completeness["completeness_score"]

    quality_score = (schema_score * 0.5) + (completeness_score * 0.5)
    results["quality_score"] = round(quality_score, 3)

    logger.info(f"Extraction quality score: {quality_score:.2%}")
    logger.info(f"Schema compliant: {is_valid}, Completeness: {completeness_score:.2%}")

    return results


def create_validation_report(validation_results: Dict[str, Any]) -> str:
    """
    Create a human-readable validation report.

    Formats validation results into a readable text report with:
    - Overall quality score
    - Schema compliance status
    - Completeness breakdown (required/optional fields)
    - First 10 validation errors (if any)

    Args:
        validation_results: Results from validate_extraction_quality()

    Returns:
        Formatted validation report string (multi-line)

    Example:
        >>> results = validate_extraction_quality(data, schema)
        >>> report = create_validation_report(results)
        >>> print(report)
        ============================================================
        EXTRACTION VALIDATION REPORT
        ============================================================
        Overall Quality Score: 85.0%
        Schema Compliant: ✅ Yes

        Data Completeness:
          Required Fields: 5/5
          Optional Fields: 8/15
          Completeness Score: 70.0%
        ============================================================
    """
    report_lines = [
        "=" * 60,
        "EXTRACTION VALIDATION REPORT",
        "=" * 60,
        f"Overall Quality Score: {validation_results['quality_score']:.1%}",
        f"Schema Compliant: {'✅ Yes' if validation_results['schema_compliant'] else '❌ No'}",
        "",
    ]

    # Completeness section
    comp = validation_results["completeness"]
    report_lines.extend(
        [
            "Data Completeness:",
            f"  Required Fields: {comp['required_fields_present']}/{comp['required_fields_total']}",
            f"  Optional Fields: {comp['optional_fields_present']}/{comp['optional_fields_total']}",
            f"  Completeness Score: {comp['completeness_score']:.1%}",
            "",
        ]
    )

    # Validation errors
    if validation_results["validation_errors"]:
        report_lines.extend(
            [
                f"Validation Errors ({len(validation_results['validation_errors'])}):",
            ]
        )
        for i, error in enumerate(validation_results["validation_errors"][:10], 1):
            report_lines.append(f"  {i}. {error}")
        if len(validation_results["validation_errors"]) > 10:
            report_lines.append(
                f"  ... and {len(validation_results['validation_errors']) - 10} more"
            )
        report_lines.append("")

    report_lines.append("=" * 60)

    return "\n".join(report_lines)
