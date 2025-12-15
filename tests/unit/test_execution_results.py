# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for streamlit execution result helpers.
"""

import pytest

from src.streamlit_app.screens import execution_results as results

pytestmark = pytest.mark.unit


def test_check_validation_warnings_flags_low_quality_and_minor_errors():
    validation_result = {
        "quality_score": 7.5,
        "is_valid": True,
        "errors": [{"field": "x"}],
    }

    warnings = results._check_validation_warnings(validation_result)

    assert "Quality score is 7.5/10" in warnings[0]
    assert "minor schema issue(s)" in warnings[1]


class StubStreamlit:
    def __init__(self):
        self.calls = []

    def write(self, msg):
        self.calls.append(("write", msg))


def test_display_classification_result_writes_publication_and_doi(monkeypatch):
    stub = StubStreamlit()
    monkeypatch.setattr(results, "st", stub)

    results.display_classification_result(
        {"publication_type": "interventional_trial", "metadata": {"doi": "10.1234/test"}}
    )

    assert ("write", "**Publication Type:** `interventional_trial`") in stub.calls
    assert ("write", "**DOI:** `10.1234/test`") in stub.calls
