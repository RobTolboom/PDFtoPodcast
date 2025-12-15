# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for streamlit execution artifact helpers.
"""

import pytest

from src.streamlit_app.screens import execution_artifacts as artifacts

pytestmark = pytest.mark.unit


class StubStreamlit:
    def __init__(self, pdf_path=None):
        class SessionState(dict):
            def __getattr__(self_inner, key):
                try:
                    return self_inner[key]
                except KeyError as err:
                    raise AttributeError(key) from err

            def __setattr__(self_inner, key, value):
                self_inner[key] = value

        self.session_state = SessionState({"pdf_path": pdf_path})
        self.calls = []

    def markdown(self, msg):
        self.calls.append(("markdown", msg))

    def download_button(self, label, data, file_name=None):
        self.calls.append(("download", label, file_name))

    def info(self, msg):
        self.calls.append(("info", msg))

    def expander(self, label):
        self.calls.append(("expander", label))

        class Dummy:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                return False

            def markdown(self_inner, content):
                self.calls.append(("expander_markdown", content))

        return Dummy()

    def text_area(self, label, value, height=None, key=None):
        self.calls.append(("text_area", label, key))


def test_display_report_artifacts_no_pdf_path_returns_early(monkeypatch):
    stub = StubStreamlit(pdf_path=None)
    monkeypatch.setattr(artifacts, "st", stub)

    artifacts.display_report_artifacts()

    assert stub.calls == []


def test_display_report_artifacts_no_files_shows_info(monkeypatch, tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("dummy")
    stub = StubStreamlit(pdf_path=pdf_path)
    monkeypatch.setattr(artifacts, "st", stub)

    class FakeFM:
        def __init__(self, pdf):
            self.identifier = pdf.stem
            self.tmp_dir = tmp_path / "tmp"
            self.tmp_dir.mkdir(exist_ok=True)

    monkeypatch.setattr(artifacts, "PipelineFileManager", FakeFM)

    artifacts.display_report_artifacts()

    assert ("markdown", "### Report Artifacts") in stub.calls
    assert any(call[0] == "info" for call in stub.calls)
