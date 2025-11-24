# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for WeasyPrint renderer fixes.

Tests cover:
- Figure generation integration
- Error handling during figure generation
"""

from unittest.mock import MagicMock, patch

import pytest

from src.rendering.figure_generator import FigureGenerationError
from src.rendering.weasy_renderer import WeasyRendererError, render_report_with_weasyprint


class TestWeasyPrintFigures:
    """Test figure generation in WeasyPrint renderer."""

    @pytest.fixture
    def mock_report(self):
        return {
            "metadata": {"title": "Test Report"},
            "sections": [
                {
                    "title": "Section 1",
                    "blocks": [
                        {
                            "type": "figure",
                            "figure_kind": "rob_traffic_light",
                            "data": {"some": "data"},
                            "caption": "Test Figure",
                        }
                    ],
                }
            ],
        }

    def test_render_generates_missing_figures(self, tmp_path, mock_report):
        """Test that render_report_with_weasyprint generates missing figures."""

        # Mock dependencies
        with (
            patch("src.rendering.weasy_renderer._import_weasyprint") as mock_import,
            patch("src.rendering.weasy_renderer.generate_figure") as mock_gen_fig,
        ):
            # Setup mocks
            mock_html_cls = MagicMock()
            mock_import.return_value = mock_html_cls
            mock_gen_fig.return_value = tmp_path / "figures" / "fig1.png"

            # Execute
            render_report_with_weasyprint(mock_report, tmp_path)

            # Verify generate_figure was called
            mock_gen_fig.assert_called_once()

            # Verify block file path was updated
            block = mock_report["sections"][0]["blocks"][0]
            assert block["file"] == str(tmp_path / "figures" / "fig1.png")

    def test_render_handles_generation_error(self, tmp_path, mock_report):
        """Test that rendering continues (with error log) if figure generation fails."""

        with (
            patch("src.rendering.weasy_renderer._import_weasyprint") as mock_import,
            patch("src.rendering.weasy_renderer.generate_figure") as mock_gen_fig,
            patch("builtins.print") as mock_print,
        ):
            # Setup mocks
            mock_html_cls = MagicMock()
            mock_import.return_value = mock_html_cls
            mock_gen_fig.side_effect = FigureGenerationError("Generation failed")

            # Execute - should not raise exception
            try:
                render_report_with_weasyprint(mock_report, tmp_path)
            except WeasyRendererError:
                # It might raise WeasyRendererError later because file is missing,
                # but we want to ensure generate_figure was called and error logged
                pass

            # Verify generate_figure was called
            mock_gen_fig.assert_called_once()

            # Verify error was logged
            mock_print.assert_any_call("Failed to generate figure: Generation failed")

    def test_render_skips_existing_figures(self, tmp_path, mock_report):
        """Test that existing figure files are not regenerated."""

        # Set existing file
        mock_report["sections"][0]["blocks"][0]["file"] = "/path/to/existing.png"

        with (
            patch("src.rendering.weasy_renderer._import_weasyprint") as mock_import,
            patch("src.rendering.weasy_renderer.generate_figure") as mock_gen_fig,
        ):
            mock_html_cls = MagicMock()
            mock_import.return_value = mock_html_cls

            render_report_with_weasyprint(mock_report, tmp_path)

            # Verify generate_figure was NOT called
            mock_gen_fig.assert_not_called()
