# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for pipeline orchestrator helper functions.

Tests the _strip_metadata_for_pipeline() function that removes
execution metadata before passing data to dependent pipeline steps.
"""

from src.pipeline.orchestrator import _strip_metadata_for_pipeline


class TestStripMetadataForPipeline:
    """Tests for _strip_metadata_for_pipeline() helper function."""

    def test_strip_metadata_removes_usage(self):
        """Test that usage field is removed."""
        data = {
            "publication_type": "interventional_trial",
            "metadata": {"title": "Test Study"},
            "usage": {"input_tokens": 1000, "output_tokens": 500},
        }

        clean = _strip_metadata_for_pipeline(data)

        assert "usage" not in clean
        assert "publication_type" in clean
        assert "metadata" in clean

    def test_strip_metadata_removes_llm_metadata(self):
        """Test that _metadata field is removed."""
        data = {
            "publication_type": "interventional_trial",
            "_metadata": {
                "response_id": "resp_123",
                "model": "gpt-5-2025-04-14",
            },
        }

        clean = _strip_metadata_for_pipeline(data)

        assert "_metadata" not in clean
        assert "publication_type" in clean

    def test_strip_metadata_removes_pipeline_metadata(self):
        """Test that _pipeline_metadata field is removed."""
        data = {
            "publication_type": "interventional_trial",
            "_pipeline_metadata": {
                "step": "classification",
                "timestamp": "2025-10-27T13:45:23Z",
                "duration_seconds": 12.4,
            },
        }

        clean = _strip_metadata_for_pipeline(data)

        assert "_pipeline_metadata" not in clean
        assert "publication_type" in clean

    def test_strip_metadata_removes_correction_notes(self):
        """Test that correction_notes field is removed."""
        data = {
            "publication_type": "interventional_trial",
            "metadata": {"title": "Test Study"},
            "correction_notes": "Corrections applied based on validation feedback",
        }

        clean = _strip_metadata_for_pipeline(data)

        assert "correction_notes" not in clean
        assert "publication_type" in clean
        assert "metadata" in clean

    def test_strip_metadata_handles_missing_fields(self):
        """Test that function works when metadata fields are absent."""
        data = {
            "publication_type": "interventional_trial",
            "metadata": {"title": "Test Study"},
        }

        clean = _strip_metadata_for_pipeline(data)

        # Should work without errors even though no metadata fields present
        assert clean == data

    def test_strip_metadata_preserves_schema_fields(self):
        """Test that all schema-defined fields are preserved."""
        data = {
            "publication_type": "interventional_trial",
            "metadata": {"title": "Test Study", "authors": ["Smith J"]},
            "study_design": {"design_label": "RCT"},
            "outcomes": [{"outcome_id": "o1", "label": "Primary"}],
            "usage": {"input_tokens": 1000},
            "_metadata": {"response_id": "resp_123"},
            "_pipeline_metadata": {"step": "extraction"},
            "correction_notes": "Corrections applied based on validation feedback",
        }

        clean = _strip_metadata_for_pipeline(data)

        # All schema fields should be preserved
        assert clean["publication_type"] == "interventional_trial"
        assert clean["metadata"]["title"] == "Test Study"
        assert clean["study_design"]["design_label"] == "RCT"
        assert len(clean["outcomes"]) == 1

        # Metadata fields should be removed
        assert "usage" not in clean
        assert "_metadata" not in clean
        assert "_pipeline_metadata" not in clean
        assert "correction_notes" not in clean

    def test_strip_metadata_removes_all_metadata_fields_together(self):
        """Test that all four metadata fields are removed in one call."""
        data = {
            "field": "value",
            "usage": {"tokens": 100},
            "_metadata": {"model": "gpt-5"},
            "_pipeline_metadata": {"step": "classification"},
            "correction_notes": "Corrections applied",
        }

        clean = _strip_metadata_for_pipeline(data)

        assert clean == {"field": "value"}

    def test_strip_metadata_does_not_modify_original(self):
        """Test that original dict is not modified (copy is returned)."""
        data = {
            "field": "value",
            "usage": {"tokens": 100},
        }

        clean = _strip_metadata_for_pipeline(data)

        # Original should still have usage
        assert "usage" in data
        # Clean should not have usage
        assert "usage" not in clean
