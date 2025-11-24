# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for figure generation (Phase 5).
"""

import importlib.util

import pytest

from src.rendering.figure_generator import (
    FigureGenerationError,
    generate_figure,
)

# Skip tests that require matplotlib if it's not installed
HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None

requires_matplotlib = pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib not installed")


@requires_matplotlib
class TestGenerateFigure:
    """Tests for the generate_figure function (requires matplotlib)."""

    def test_generate_rob_traffic_light(self, tmp_path):
        """Test RoB traffic light figure generation."""
        block = {
            "type": "figure",
            "figure_kind": "rob_traffic_light",
            "label": "fig_rob",
            "data": {
                "domains": ["Randomization", "Blinding", "Outcome"],
                "judgements": ["Low", "Some concerns", "High"],
            },
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.exists()
        assert fig_path.suffix == ".png"
        assert fig_path.name == "fig_rob.png"
        # Check file is not empty
        assert fig_path.stat().st_size > 0

    def test_generate_forest_basic(self, tmp_path):
        """Test basic forest plot generation."""
        block = {
            "type": "figure",
            "figure_kind": "forest",
            "label": "fig_forest",
            "data": {
                "outcomes": [
                    {"name": "Pain reduction", "effect": -0.5, "ci": (-0.8, -0.2)},
                    {"name": "Quality of life", "effect": 0.3, "ci": (0.1, 0.5)},
                ]
            },
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.exists()
        assert fig_path.suffix == ".png"
        assert fig_path.name == "fig_forest.png"
        assert fig_path.stat().st_size > 0

    def test_generate_rob_traffic_light_empty_data(self, tmp_path):
        """Test RoB traffic light with default data when empty."""
        block = {
            "type": "figure",
            "figure_kind": "rob_traffic_light",
            "label": "fig_rob_empty",
            "data": {},
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.exists()
        assert fig_path.name == "fig_rob_empty.png"

    def test_generate_forest_basic_empty_data(self, tmp_path):
        """Test forest plot with default data when empty."""
        block = {
            "type": "figure",
            "figure_kind": "forest",
            "label": "fig_forest_empty",
            "data": {},
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.exists()
        assert fig_path.name == "fig_forest_empty.png"

    def test_generate_unsupported_figure_kind_raises_error(self, tmp_path):
        """Test that unsupported figure types raise FigureGenerationError."""
        block = {
            "type": "figure",
            "figure_kind": "unsupported_type",
            "label": "fig_unknown",
        }
        with pytest.raises(FigureGenerationError, match="Unsupported figure_kind"):
            generate_figure(block, tmp_path)

    def test_generate_prisma_flow(self, tmp_path):
        """Test PRISMA flow diagram generation with complete data."""
        block = {
            "type": "figure",
            "figure_kind": "prisma",
            "label": "fig_prisma",
            "data": {
                "records_identified": 1234,
                "records_after_duplicates": 987,
                "records_screened": 987,
                "records_excluded": 800,
                "full_text_assessed": 187,
                "full_text_excluded": 145,
                "studies_included": 42,
                "reasons_excluded": ["Not RCT (n=80)", "Wrong population (n=45)", "Other (n=20)"],
            },
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.exists()
        assert fig_path.suffix == ".png"
        assert fig_path.name == "fig_prisma.png"
        assert fig_path.stat().st_size > 0

    def test_generate_prisma_flow_minimal_data(self, tmp_path):
        """Test PRISMA flow diagram with minimal required data."""
        block = {
            "type": "figure",
            "figure_kind": "prisma",
            "label": "fig_prisma_minimal",
            "data": {
                "records_identified": 100,
                "studies_included": 10,
            },
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.exists()
        assert fig_path.name == "fig_prisma_minimal.png"

    def test_generate_prisma_flow_empty_data(self, tmp_path):
        """Test PRISMA flow diagram with empty data uses defaults."""
        block = {
            "type": "figure",
            "figure_kind": "prisma",
            "label": "fig_prisma_empty",
            "data": {},
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.exists()
        assert fig_path.name == "fig_prisma_empty.png"

    def test_generate_consort_flow(self, tmp_path):
        """Test CONSORT flow diagram generation with complete data."""
        block = {
            "type": "figure",
            "figure_kind": "consort",
            "label": "fig_consort",
            "data": {
                "n_screened": 500,
                "n_excluded_screening": 300,
                "n_randomised": 200,
                "exclusion_reasons": ["Not meeting criteria (n=250)", "Declined (n=50)"],
                "arms": [
                    {
                        "label": "Treatment",
                        "n_assigned": 100,
                        "n_analysed": 95,
                        "lost_to_followup": 3,
                        "discontinued": 2,
                    },
                    {
                        "label": "Control",
                        "n_assigned": 100,
                        "n_analysed": 92,
                        "lost_to_followup": 5,
                        "discontinued": 3,
                    },
                ],
            },
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.exists()
        assert fig_path.suffix == ".png"
        assert fig_path.name == "fig_consort.png"
        assert fig_path.stat().st_size > 0

    def test_generate_consort_flow_three_arms(self, tmp_path):
        """Test CONSORT flow diagram with 3 treatment arms."""
        block = {
            "type": "figure",
            "figure_kind": "consort",
            "label": "fig_consort_3arm",
            "data": {
                "n_screened": 600,
                "n_randomised": 300,
                "arms": [
                    {"label": "Drug A", "n_assigned": 100, "n_analysed": 95},
                    {"label": "Drug B", "n_assigned": 100, "n_analysed": 97},
                    {"label": "Placebo", "n_assigned": 100, "n_analysed": 98},
                ],
            },
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.exists()
        assert fig_path.name == "fig_consort_3arm.png"

    def test_generate_consort_flow_empty_data(self, tmp_path):
        """Test CONSORT flow diagram with empty data uses defaults."""
        block = {
            "type": "figure",
            "figure_kind": "consort",
            "label": "fig_consort_empty",
            "data": {},
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.exists()
        assert fig_path.name == "fig_consort_empty.png"

    def test_generate_figure_creates_output_directory(self, tmp_path):
        """Test that generate_figure creates output directory if needed."""
        nested_dir = tmp_path / "nested" / "figures"
        block = {
            "type": "figure",
            "figure_kind": "rob_traffic_light",
            "label": "fig_nested",
            "data": {},
        }
        fig_path = generate_figure(block, nested_dir)

        assert nested_dir.exists()
        assert fig_path.exists()

    def test_generate_figure_uses_label_as_filename(self, tmp_path):
        """Test that the label is used as the filename."""
        block = {
            "type": "figure",
            "figure_kind": "rob_traffic_light",
            "label": "my_custom_label",
            "data": {},
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.name == "my_custom_label.png"

    def test_generate_figure_default_label(self, tmp_path):
        """Test that 'figure' is used as default label when not provided."""
        block = {
            "type": "figure",
            "figure_kind": "rob_traffic_light",
            "data": {},
        }
        fig_path = generate_figure(block, tmp_path)

        assert fig_path.name == "figure.png"


class TestFigureGenerationError:
    """Tests for the FigureGenerationError exception."""

    def test_exception_is_runtime_error(self):
        """Test that FigureGenerationError inherits from RuntimeError."""
        assert issubclass(FigureGenerationError, RuntimeError)

    def test_exception_can_be_raised_with_message(self):
        """Test that the exception can be raised with a custom message."""
        with pytest.raises(FigureGenerationError, match="Custom error message"):
            raise FigureGenerationError("Custom error message")
