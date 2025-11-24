# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""Tests for propagating CLI report flags through the full pipeline."""

from pathlib import Path

from src.pipeline import orchestrator


def test_run_four_step_pipeline_passes_report_flags(monkeypatch, tmp_path):
    """Ensure report renderer/compile/figure flags flow through the full pipeline."""

    pdf_path = Path(tmp_path / "paper.pdf")
    pdf_path.write_text("dummy")

    calls: list[dict[str, object]] = []

    def fake_run_single_step(
        step_name,
        pdf_path,
        max_pages,
        llm_provider,
        file_manager,
        progress_callback=None,
        previous_results=None,
        max_correction_iterations=None,
        quality_thresholds=None,
        enable_iterative_correction=True,
        report_language=None,
        report_compile_pdf=True,
        report_enable_figures=True,
        report_renderer="latex",
    ):
        calls.append(
            {
                "step": step_name,
                "renderer": report_renderer,
                "compile_pdf": report_compile_pdf,
                "enable_figures": report_enable_figures,
            }
        )
        if step_name == orchestrator.STEP_CLASSIFICATION:
            return {"publication_type": "interventional_trial"}
        if step_name == orchestrator.STEP_EXTRACTION:
            return {"data": {}}
        if step_name == orchestrator.STEP_VALIDATION_CORRECTION:
            return {"final_status": "passed", "verification_summary": {"overall_status": "passed"}}
        if step_name == orchestrator.STEP_APPRAISAL:
            return {"final_status": "passed"}
        if step_name == orchestrator.STEP_REPORT_GENERATION:
            return {"rendered_paths": {}}
        return {}

    monkeypatch.setattr(orchestrator, "run_single_step", fake_run_single_step)

    orchestrator.run_four_step_pipeline(
        pdf_path=pdf_path,
        llm_provider="openai",
        report_language="nl",
        report_renderer="weasyprint",
        report_compile_pdf=False,
        report_enable_figures=False,
        have_llm_support=True,
    )

    report_call = next(c for c in calls if c["step"] == orchestrator.STEP_REPORT_GENERATION)
    assert report_call["renderer"] == "weasyprint"
    assert report_call["compile_pdf"] is False
    assert report_call["enable_figures"] is False
