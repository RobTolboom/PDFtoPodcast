# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for report schema loading and validation.
"""

import pytest

from src.schemas_loader import load_schema


def test_load_report_schema():
    """Test loading the report schema"""
    schema = load_schema("report")

    assert schema is not None
    assert isinstance(schema, dict)
    assert schema["title"] == "Structured Report Output (report_v1)"
    assert "report_version" in schema["properties"]
    assert "study_type" in schema["properties"]
    assert "metadata" in schema["properties"]
    assert "layout" in schema["properties"]
    assert "sections" in schema["properties"]


def test_load_report_validation_schema():
    """Test loading the report validation schema"""
    schema = load_schema("report_validation")

    assert schema is not None
    assert isinstance(schema, dict)
    assert schema["title"] == "Report Validation Report Schema"
    assert "validation_version" in schema["properties"]
    assert "validation_summary" in schema["properties"]
    assert "issues" in schema["properties"]


def test_report_schema_required_fields():
    """Test that report schema has correct required fields"""
    schema = load_schema("report")

    required = schema["required"]
    assert "report_version" in required
    assert "study_type" in required
    assert "metadata" in required
    assert "layout" in required
    assert "sections" in required


def test_report_schema_study_type_enum():
    """Test that study_type has correct enum values"""
    schema = load_schema("report")

    study_type_enum = schema["properties"]["study_type"]["enum"]
    expected_types = [
        "interventional",
        "observational",
        "systematic_review",
        "prediction",
        "editorials",
    ]

    assert set(study_type_enum) == set(expected_types)


def test_report_schema_block_types():
    """Test that all block types are defined in schema"""
    schema = load_schema("report")

    # Check that block definition exists and has oneOf with all block types
    block_def = schema["$defs"]["block"]
    assert "oneOf" in block_def

    # Should have references to all 4 block types
    block_refs = [ref["$ref"] for ref in block_def["oneOf"]]
    assert "#/$defs/textBlock" in block_refs
    assert "#/$defs/tableBlock" in block_refs
    assert "#/$defs/figureBlock" in block_refs
    assert "#/$defs/calloutBlock" in block_refs


def test_report_schema_text_block_styles():
    """Test that textBlock has correct style enum"""
    schema = load_schema("report")

    text_block = schema["$defs"]["textBlock"]
    style_enum = text_block["properties"]["style"]["enum"]

    assert "paragraph" in style_enum
    assert "bullets" in style_enum
    assert "numbered" in style_enum


def test_report_schema_table_kinds():
    """Test that tableBlock has correct table_kind enum"""
    schema = load_schema("report")

    table_block = schema["$defs"]["tableBlock"]
    table_kind_enum = table_block["properties"]["table_kind"]["enum"]

    expected_kinds = [
        "generic",
        "snapshot",
        "outcomes",
        "harms",
        "rob_domains",
        "grade_sof",
        "confounding_matrix",
        "meta_results",
        "model_metrics",
    ]

    assert set(table_kind_enum) == set(expected_kinds)


def test_report_schema_figure_kinds():
    """Test that figureBlock has correct figure_kind enum"""
    schema = load_schema("report")

    figure_block = schema["$defs"]["figureBlock"]
    figure_kind_enum = figure_block["properties"]["figure_kind"]["enum"]

    expected_kinds = [
        "image",
        "rob_traffic_light",
        "forest",
        "roc",
        "calibration",
        "prisma",
        "consort",
        "dag",
    ]

    assert set(figure_kind_enum) == set(expected_kinds)


def test_report_schema_callout_variants():
    """Test that calloutBlock has correct variant enum"""
    schema = load_schema("report")

    callout_block = schema["$defs"]["calloutBlock"]
    variant_enum = callout_block["properties"]["variant"]["enum"]

    expected_variants = ["warning", "note", "implication", "clinical_pearl"]

    assert set(variant_enum) == set(expected_variants)


def test_report_validation_schema_required_fields():
    """Test that report validation schema has correct required fields"""
    schema = load_schema("report_validation")

    required = schema["required"]
    assert "validation_version" in required
    assert "validation_summary" in required
    assert "issues" in required


def test_report_validation_schema_scores():
    """Test that validation summary has all required scores"""
    schema = load_schema("report_validation")

    summary_props = schema["properties"]["validation_summary"]["properties"]

    # Check all score fields exist
    assert "completeness_score" in summary_props
    assert "accuracy_score" in summary_props
    assert "cross_reference_consistency_score" in summary_props
    assert "data_consistency_score" in summary_props
    assert "schema_compliance_score" in summary_props
    assert "quality_score" in summary_props
    assert "critical_issues" in summary_props


def test_report_validation_issue_categories():
    """Test that issue categories enum is complete"""
    schema = load_schema("report_validation")

    issue_props = schema["properties"]["issues"]["items"]["properties"]
    category_enum = issue_props["category"]["enum"]

    expected_categories = [
        "missing_section",
        "missing_outcome",
        "data_mismatch",
        "broken_reference",
        "schema_violation",
        "hallucinated_data",
        "grade_mismatch",
        "rob_mismatch",
        "incomplete_source_map",
        "inconsistent_bottom_line",
        "other",
    ]

    assert set(category_enum) == set(expected_categories)


def test_report_schema_label_patterns():
    """Test that table and figure labels have correct patterns"""
    schema = load_schema("report")

    # Check table label pattern
    table_label_pattern = schema["$defs"]["tableBlock"]["properties"]["label"]["pattern"]
    assert table_label_pattern == "^tbl_[a-z0-9_]+$"

    # Check figure label pattern
    figure_label_pattern = schema["$defs"]["figureBlock"]["properties"]["label"]["pattern"]
    assert figure_label_pattern == "^fig_[a-z0-9_]+$"


def test_report_schema_source_ref_pattern():
    """Test that source reference code has correct pattern"""
    schema = load_schema("report")

    source_ref = schema["$defs"]["sourceRef"]
    code_pattern = source_ref["properties"]["code"]["pattern"]

    assert code_pattern == "^S[0-9]+$"


def test_report_schema_language_enum():
    """Test that layout language has correct enum"""
    schema = load_schema("report")

    language_enum = schema["properties"]["layout"]["properties"]["language"]["enum"]

    assert "nl" in language_enum
    assert "en" in language_enum
    assert len(language_enum) == 2


def test_report_schema_no_additional_properties():
    """Test that additionalProperties is false at root level"""
    schema = load_schema("report")

    assert schema.get("additionalProperties") is False


def test_report_validation_schema_severity_enum():
    """Test that issue severity has correct enum"""
    schema = load_schema("report_validation")

    issue_props = schema["properties"]["issues"]["items"]["properties"]
    severity_enum = issue_props["severity"]["enum"]

    assert "critical" in severity_enum
    assert "moderate" in severity_enum
    assert "minor" in severity_enum


def test_report_schema_metadata_timestamps():
    """Test that metadata has correct timestamp fields"""
    schema = load_schema("report")

    metadata_props = schema["properties"]["metadata"]["properties"]

    # Check generation_timestamp is required and has format
    assert "generation_timestamp" in metadata_props
    assert metadata_props["generation_timestamp"]["format"] == "date-time"

    # Check pipeline_version is required
    assert "pipeline_version" in metadata_props


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
