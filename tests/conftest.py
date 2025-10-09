"""
Pytest configuration and shared fixtures.
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest


@pytest.fixture
def sample_pdf() -> Path:
    """Path to sample PDF for testing."""
    return Path("tests/fixtures/sample_pdfs/sample_trial.pdf")


@pytest.fixture
def mock_classification_response() -> dict[str, Any]:
    """Mock LLM response for classification step."""
    return {
        "publication_type": "interventional_trial",
        "metadata": {
            "doi": "10.1234/test.2025.001",
            "title": "Test Clinical Trial",
            "authors": ["Smith J", "Doe J", "Johnson A"],
            "journal": "Test Medical Journal",
            "year": 2025,
            "volume": "10",
            "issue": "1",
            "pages": "1-10",
        },
        "classification_confidence": 0.95,
    }


@pytest.fixture
def mock_extraction_response() -> dict[str, Any]:
    """Mock LLM response for extraction step."""
    return {
        "schema_version": "v2.0",
        "metadata": {"doi": "10.1234/test.2025.001", "title": "Test Clinical Trial"},
        "study_design": {
            "design_type": "Randomized Controlled Trial",
            "blinding": "Double-blind",
            "allocation": "Random",
        },
        "population": {
            "total_enrolled": 100,
            "inclusion_criteria": ["Age 18-65", "Diagnosed condition"],
            "exclusion_criteria": ["Pregnancy", "Severe comorbidities"],
        },
        "interventions": [{"name": "Treatment A", "type": "Drug", "dosage": "100mg daily"}],
        "outcomes": [
            {
                "outcome_name": "Primary efficacy",
                "outcome_type": "Primary",
                "measurement": "Change from baseline",
            }
        ],
    }


@pytest.fixture
def mock_validation_response() -> dict[str, Any]:
    """Mock LLM response for validation step."""
    return {
        "verification_summary": {
            "overall_status": "passed",
            "completeness_score": 0.90,
            "accuracy_score": 0.88,
            "schema_compliance_score": 0.95,
            "total_issues": 2,
            "critical_issues": 0,
        },
        "issues": [
            {
                "issue_id": "I001",
                "type": "minor_inaccuracy",
                "severity": "minor",
                "category": "data_accuracy",
                "description": "Sample size slightly different from reported",
                "recommendation": "Verify page 3 for exact enrollment number",
            }
        ],
        "field_validation": {
            "required_fields_complete": True,
            "schema_compliance": True,
            "source_references_valid": True,
            "data_types_correct": True,
        },
    }


@pytest.fixture
def mock_openai_provider(mock_classification_response):
    """Mock OpenAI provider."""
    provider = Mock()
    provider.generate_json_with_pdf.return_value = mock_classification_response
    return provider


@pytest.fixture
def mock_claude_provider(mock_classification_response):
    """Mock Claude provider."""
    provider = Mock()
    provider.generate_json_with_pdf.return_value = mock_classification_response
    return provider


@pytest.fixture
def classification_schema() -> dict[str, Any]:
    """Sample classification schema for testing."""
    return {
        "type": "object",
        "properties": {
            "publication_type": {"type": "string"},
            "metadata": {"type": "object"},
            "classification_confidence": {"type": "number"},
        },
        "required": ["publication_type", "metadata"],
    }


@pytest.fixture
def extraction_schema() -> dict[str, Any]:
    """Sample extraction schema for testing."""
    return {
        "type": "object",
        "properties": {
            "schema_version": {"type": "string"},
            "metadata": {"type": "object"},
            "study_design": {"type": "object"},
        },
        "required": ["metadata"],
    }
