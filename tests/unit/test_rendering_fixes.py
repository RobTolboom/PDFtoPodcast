# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for rendering fixes (Phase 9).

Tests cover:
- Enhanced LaTeX escaping
- Enhanced Markdown escaping
- LaTeX engine security validation
- Figure generator error handling
"""

from unittest.mock import MagicMock, patch

import pytest

from src.rendering.figure_generator import FigureGenerationError, _import_matplotlib
from src.rendering.latex_renderer import _escape_latex, render_report_to_pdf
from src.rendering.markdown_renderer import _escape_md


class TestLatexEscaping:
    """Test enhanced LaTeX escaping."""

    def test_escape_latex_special_chars(self):
        """Test escaping of all special characters."""
        text = r"\ & % $ # _ { } ~ ^ [ ] | < > * + = / @"
        escaped = _escape_latex(text)

        assert r"\textbackslash{}" in escaped
        assert r"\&" in escaped
        assert r"\%" in escaped
        assert r"\$" in escaped
        assert r"\#" in escaped
        assert r"\_" in escaped
        assert r"\{" in escaped
        assert r"\}" in escaped
        assert r"\textasciitilde{}" in escaped
        assert r"\textasciicircum{}" in escaped
        assert r"{[}" in escaped
        assert r"{]}" in escaped
        assert r"\textbar{}" in escaped
        assert r"\textless{}" in escaped
        assert r"\textgreater{}" in escaped
        assert r"\textasteriskcentered{}" in escaped
        assert r"{+}" in escaped
        assert r"{=}" in escaped
        assert r"{/}" in escaped
        assert "@" in escaped  # @ is preserved

    def test_escape_latex_grade_symbols(self):
        """Test escaping of GRADE symbols."""
        text = "⊕ ○ ≥ ≤ α"
        escaped = _escape_latex(text)

        assert r"$\oplus$" in escaped
        assert r"$\circ$" in escaped
        assert r"$\geq$" in escaped
        assert r"$\leq$" in escaped
        assert r"$\alpha$" in escaped


class TestMarkdownEscaping:
    """Test enhanced Markdown escaping."""

    def test_escape_md_special_chars(self):
        """Test escaping of markdown special characters."""
        text = r"\ ` * _ { } [ ] ( ) # + - . ! |"
        escaped = _escape_md(text)

        assert r"\\" in escaped
        assert r"\`" in escaped
        assert r"\*" in escaped
        assert r"\_" in escaped
        assert r"\{" in escaped
        assert r"\}" in escaped
        assert r"\[" in escaped
        assert r"\]" in escaped
        assert r"\(" in escaped
        assert r"\)" in escaped
        assert r"\#" in escaped
        assert r"\+" in escaped
        assert r"\-" in escaped
        assert r"\." in escaped
        assert r"\!" in escaped
        assert r"\|" in escaped


class TestLatexSecurity:
    """Test LaTeX renderer security."""

    def test_render_report_to_pdf_invalid_engine(self, tmp_path):
        """Test that invalid engine raises ValueError."""
        report = {"sections": []}

        with pytest.raises(ValueError, match="Invalid LaTeX engine"):
            render_report_to_pdf(
                report,
                output_dir=tmp_path,
                engine="rm -rf /",
                compile_pdf=True,  # Malicious input
            )

    def test_render_report_to_pdf_valid_engine(self, tmp_path):
        """Test that valid engine is accepted."""
        report = {"sections": []}

        # Mock subprocess and template reading to avoid actual execution
        with (
            patch("src.rendering.latex_renderer.render_report_to_tex", return_value="tex content"),
            patch("shutil.copy"),
            patch("shutil.which", return_value="/usr/bin/pdflatex"),
            patch("subprocess.run"),
        ):
            # Should not raise error
            render_report_to_pdf(report, output_dir=tmp_path, engine="pdflatex", compile_pdf=True)


class TestFigureGeneratorErrors:
    """Test figure generator error handling."""

    def test_import_matplotlib_missing(self):
        """Test error when matplotlib is missing."""
        with patch.dict("sys.modules", {"matplotlib": None}):
            with pytest.raises(FigureGenerationError, match="matplotlib is required"):
                _import_matplotlib()

    def test_import_matplotlib_other_error(self):
        """Test error when matplotlib import fails for other reasons."""
        with patch.dict("sys.modules", {"matplotlib": MagicMock()}):
            # Simulate an error during use("Agg")
            with patch("matplotlib.use", side_effect=RuntimeError("Something broke")):
                with pytest.raises(FigureGenerationError, match="Failed to import matplotlib"):
                    _import_matplotlib()
