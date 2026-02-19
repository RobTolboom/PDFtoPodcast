from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.podcast_logic import run_podcast_generation


@pytest.fixture
def mock_file_manager():
    fm = MagicMock()
    fm.save_json.return_value = "mock_podcast.json"
    return fm


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    # Need 800+ words: 11 words * 75 = 825 words
    llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test Podcast", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This is a test transcript that is long enough to pass validation. " * 75,
    }
    return llm


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt", side_effect=Exception("skip"))
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_run_podcast_generation_success(
    mock_get_llm, mock_load_prompt, mock_load_schema, _mock_summary, mock_file_manager, mock_llm
):
    # Setup mocks
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast from {{EXTRACTION_JSON}}"

    # Override transcript to include primary outcome (mortality) for validation
    # Need 800+ words: 9 words * 90 = 810 words
    mock_llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test Podcast", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This study examined mortality outcomes and found significant results. " * 90,
    }

    # Input data with required fields to pass all validation checks
    extraction = {
        "interventions": [{"name": "Drug X"}],
        "outcomes": {"primary": {"description": "mortality"}},
    }
    appraisal = {"grade": {"certainty_overall": "high"}}  # High GRADE to pass language check
    classification = {"type": "trial"}

    # Run function
    result = run_podcast_generation(
        extraction_result=extraction,
        appraisal_result=appraisal,
        classification_result=classification,
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    # Verify
    assert result["status"] == "success"
    assert result["podcast"]["metadata"]["title"] == "Test Podcast"
    assert result["validation"]["status"] == "passed"

    # Verify LLM call
    mock_llm.generate_json_with_schema.assert_called_once()

    # Verify file saving
    mock_file_manager.save_json.assert_any_call(result["podcast"], "podcast")
    mock_file_manager.save_json.assert_any_call(result["validation"], "podcast_validation")


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt", side_effect=Exception("skip"))
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_run_podcast_generation_fails_on_short_transcript(
    mock_get_llm, mock_load_prompt, mock_load_schema, _mock_summary, mock_file_manager, mock_llm
):
    """Test that short transcript (<800 words) returns status 'failed' but saves files."""
    # Setup mocks
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast"

    # Return short transcript (critical issue)
    mock_llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Short", "word_count": 100, "estimated_duration_minutes": 1},
        "transcript": "Short transcript that is way too short.",
    }

    # Run function - should return status "failed" (not raise)
    result = run_podcast_generation(
        extraction_result={},
        appraisal_result={},
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    # Verify result
    assert result["status"] == "failed"
    assert result["validation"]["status"] == "failed"
    assert "Transcript too short" in str(result["validation"]["critical_issues"])
    assert result["validation"]["ready_for_tts"] is False

    # Verify files WERE saved (per spec: always save, even on failure)
    assert mock_file_manager.save_json.call_count == 2  # podcast + validation


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt", side_effect=Exception("skip"))
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_run_podcast_generation_validation_warning_abbreviations(
    mock_get_llm, mock_load_prompt, mock_load_schema, _mock_summary, mock_file_manager, mock_llm
):
    """Test that abbreviations trigger warning (not failure) with valid length."""
    # Setup mocks
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast"

    # Return valid-length transcript with abbreviation (9 words × 90 = 810)
    mock_llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This study found results in the ICU intensive care unit. " * 90,
    }

    # Run function
    result = run_podcast_generation(
        extraction_result={"interventions": [{"name": "X"}], "outcomes": {"primary": {}}},
        appraisal_result={},
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    # Verify warnings (not failure)
    assert result["status"] == "success"
    assert result["validation"]["status"] == "warnings"
    assert any("abbreviations" in issue for issue in result["validation"]["issues"])


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt", side_effect=Exception("skip"))
@patch("src.pipeline.podcast_logic.render_podcast_to_markdown")
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_run_podcast_generation_creates_markdown(
    mock_get_llm,
    mock_load_prompt,
    mock_load_schema,
    mock_render,
    _mock_summary,
    mock_file_manager,
    mock_llm,
):
    """Verify podcast generation creates markdown file."""
    # Setup mocks
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast"
    mock_file_manager.identifier = "test-paper"
    mock_file_manager.tmp_dir = MagicMock()
    mock_file_manager.tmp_dir.__truediv__ = lambda self, other: f"tmp/{other}"

    # Input data
    extraction = {"data": "test"}
    appraisal = {"rob": "low"}
    classification = {"type": "trial"}

    # Run function
    result = run_podcast_generation(
        extraction_result=extraction,
        appraisal_result=appraisal,
        classification_result=classification,
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    # Verify podcast JSON saved
    mock_file_manager.save_json.assert_any_call(result["podcast"], "podcast")

    # Verify validation JSON saved
    mock_file_manager.save_json.assert_any_call(result["validation"], "podcast_validation")

    # Verify markdown rendering was called
    mock_render.assert_called_once()
    # Verify it was called with the podcast JSON and correct path
    call_args = mock_render.call_args
    assert call_args[0][0] == result["podcast"]  # First arg is podcast JSON
    assert "test-paper-podcast.md" in str(call_args[0][1])  # Second arg is path


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt", side_effect=Exception("skip"))
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_validation_detects_missing_primary_outcome(
    mock_get_llm, mock_load_prompt, mock_load_schema, _mock_summary, mock_file_manager, mock_llm
):
    """Test that validation detects when primary outcome is not mentioned."""
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast"

    # Transcript does NOT mention the primary outcome (need 800+ words: 8 words × 100 = 800)
    mock_llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This is a long transcript about a study. " * 100,
    }

    # Extraction has a primary outcome that should be mentioned
    extraction = {
        "outcomes": {"primary": {"description": "mortality rate reduction"}},
        "interventions": [{"name": "Drug X"}],
    }

    result = run_podcast_generation(
        extraction_result=extraction,
        appraisal_result={},
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    assert result["validation"]["status"] == "warnings"
    assert any(
        "Primary outcome may not be mentioned" in issue for issue in result["validation"]["issues"]
    )


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt", side_effect=Exception("skip"))
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_validation_detects_grade_language_mismatch(
    mock_get_llm, mock_load_prompt, mock_load_schema, _mock_summary, mock_file_manager, mock_llm
):
    """Test that validation detects high-certainty language with low GRADE evidence."""
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast"

    # Transcript uses high-certainty words like "demonstrates" (need 800+ words: 6 words × 135 = 810)
    mock_llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This study demonstrates a clear benefit. " * 135,
    }

    # Appraisal indicates low GRADE certainty
    appraisal = {"grade": {"certainty_overall": "low"}}

    result = run_podcast_generation(
        extraction_result={"interventions": [{"name": "X"}], "outcomes": {"primary": {}}},
        appraisal_result=appraisal,
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    assert result["validation"]["status"] == "warnings"
    assert any(
        "High-certainty word" in issue and "low GRADE" in issue
        for issue in result["validation"]["issues"]
    )


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt", side_effect=Exception("skip"))
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_validation_warns_missing_insufficiently_reported(
    mock_get_llm, mock_load_prompt, mock_load_schema, _mock_summary, mock_file_manager, mock_llm
):
    """Test that validation warns when missing data isn't acknowledged."""
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast"

    # Transcript does NOT mention "insufficiently reported" (need 800+ words: 7 words × 115 = 805)
    mock_llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This is a study about something important. " * 115,
    }

    # Extraction is missing key fields (no interventions, no primary outcome)
    extraction = {}  # Missing interventions and outcomes

    result = run_podcast_generation(
        extraction_result=extraction,
        appraisal_result={},
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    assert result["validation"]["status"] == "warnings"
    assert any("insufficiently reported" in issue for issue in result["validation"]["issues"])


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt", side_effect=Exception("skip"))
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_validation_warns_on_too_many_numbers(
    mock_get_llm, mock_load_prompt, mock_load_schema, _mock_summary, mock_file_manager, mock_llm
):
    """Test that validation warns when transcript contains >3 numerical values."""
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast"

    # Transcript with many numbers (>3 significant numbers)
    # Base sentence repeated to get 800+ words, with numbers interspersed
    base = "This study enrolled participants and measured outcomes carefully. "
    numbers_section = (
        "The study found 42 patients improved, 37 showed no change, 15 declined, and 8 withdrew. "
    )
    mock_llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": base * 100 + numbers_section,  # 100 × 8 = 800 words + numbers section
    }

    result = run_podcast_generation(
        extraction_result={"interventions": [{"name": "X"}], "outcomes": {"primary": {}}},
        appraisal_result={},
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    assert result["validation"]["status"] == "warnings"
    assert any("numerical values" in issue for issue in result["validation"]["issues"])


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt", side_effect=Exception("skip"))
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_metadata_recalculated_from_transcript(
    mock_get_llm, mock_load_prompt, mock_load_schema, _mock_summary, mock_file_manager, mock_llm
):
    """Test that word_count and estimated_duration are recalculated from actual transcript."""
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast"

    # LLM returns incorrect metadata, but actual transcript has ~900 words (9 × 100)
    mock_llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {
            "title": "Test",
            "word_count": 500,  # Wrong - should be recalculated
            "estimated_duration_minutes": 3,  # Wrong - should be recalculated
        },
        "transcript": "This study examined mortality outcomes and found significant results. "
        * 100,
    }

    result = run_podcast_generation(
        extraction_result={
            "interventions": [{"name": "X"}],
            "outcomes": {"primary": {"description": "mortality"}},
        },
        appraisal_result={"grade": {"certainty_overall": "high"}},
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    # Verify metadata was recalculated
    assert result["podcast"]["metadata"]["word_count"] == 900  # 9 words × 100
    assert result["podcast"]["metadata"]["estimated_duration_minutes"] == 6  # 900 / 150 = 6


# ── Show Summary Generation Tests ──────────────────────────────────────────────


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt")
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_show_summary_generation_success(
    mock_get_llm,
    mock_load_prompt,
    mock_load_schema,
    mock_load_summary_prompt,
    mock_file_manager,
    mock_llm,
):
    """Test that a valid show summary is generated and merged into podcast JSON."""
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {
        "type": "object",
        "properties": {
            "show_summary": {
                "type": "object",
                "properties": {
                    "synopsis": {"type": "string"},
                    "study_at_a_glance": {"type": "array"},
                    "citation": {"type": "string"},
                },
            }
        },
    }
    mock_load_prompt.return_value = "Generate podcast"
    mock_load_summary_prompt.return_value = "Generate show summary"

    # First call returns transcript, second call returns valid summary
    valid_transcript = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test Podcast", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This study examined mortality outcomes and found significant results. " * 90,
    }
    valid_summary = {
        "synopsis": (
            "This study examined a novel treatment approach for patients with chronic disease "
            "and found statistically significant improvements in mortality outcomes."
        ),
        "study_at_a_glance": [
            {"label": "Design", "content": "Randomized controlled trial with 500 participants"},
            {"label": "Result", "content": "Treatment group showed 30% improvement"},
            {"label": "Follow-up", "content": "Follow-up period of 12 months"},
        ],
        "citation": "Smith et al. (2025). Journal of Medicine.",
    }
    mock_llm.generate_json_with_schema.side_effect = [valid_transcript, valid_summary]

    extraction = {
        "interventions": [{"name": "Drug X"}],
        "outcomes": {"primary": {"description": "mortality"}},
    }
    appraisal = {"grade": {"certainty_overall": "high"}}
    classification = {"type": "trial"}

    result = run_podcast_generation(
        extraction_result=extraction,
        appraisal_result=appraisal,
        classification_result=classification,
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    # Verify podcast succeeded
    assert result["status"] == "success"

    # Verify show_summary was merged into podcast JSON
    assert "show_summary" in result["podcast"]
    assert result["podcast"]["show_summary"]["synopsis"] == valid_summary["synopsis"]
    assert len(result["podcast"]["show_summary"]["study_at_a_glance"]) == 3

    # Verify summary validation passed
    assert result["validation"]["summary_validation"]["status"] == "passed"

    # Verify LLM was called twice (transcript + summary)
    assert mock_llm.generate_json_with_schema.call_count == 2


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt", side_effect=Exception("not found"))
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_show_summary_generation_failure_nonfatal(
    mock_get_llm,
    mock_load_prompt,
    mock_load_schema,
    _mock_summary_prompt,
    mock_file_manager,
    mock_llm,
):
    """Test that summary generation failure does not fail the podcast step."""
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast"

    # Transcript only — summary prompt will raise
    mock_llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test Podcast", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This study examined mortality outcomes and found significant results. " * 90,
    }

    extraction = {
        "interventions": [{"name": "Drug X"}],
        "outcomes": {"primary": {"description": "mortality"}},
    }
    appraisal = {"grade": {"certainty_overall": "high"}}

    result = run_podcast_generation(
        extraction_result=extraction,
        appraisal_result=appraisal,
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    # Podcast should still succeed
    assert result["status"] == "success"

    # show_summary should NOT be in the podcast JSON
    assert "show_summary" not in result["podcast"]

    # Summary validation should record the failure
    summary_val = result["validation"]["summary_validation"]
    assert summary_val["status"] == "warnings"
    assert any("Generation failed" in issue for issue in summary_val["issues"])

    # LLM should have been called only once (transcript only)
    mock_llm.generate_json_with_schema.assert_called_once()


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt")
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_show_summary_validation_synopsis_too_short(
    mock_get_llm,
    mock_load_prompt,
    mock_load_schema,
    mock_load_summary_prompt,
    mock_file_manager,
    mock_llm,
):
    """Test that synopsis < 50 chars fails summary validation and is NOT merged."""
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {
        "type": "object",
        "properties": {
            "show_summary": {
                "type": "object",
                "properties": {
                    "synopsis": {"type": "string"},
                    "study_at_a_glance": {"type": "array"},
                    "citation": {"type": "string"},
                },
            }
        },
    }
    mock_load_prompt.return_value = "Generate podcast"
    mock_load_summary_prompt.return_value = "Generate show summary"

    # First call returns transcript, second call returns summary with short synopsis
    valid_transcript = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test Podcast", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This study examined mortality outcomes and found significant results. " * 90,
    }
    short_synopsis_summary = {
        "synopsis": "Too short.",  # Only 10 chars, below 50-char minimum
        "study_at_a_glance": [
            {"label": "Design", "content": "Randomized controlled trial"},
            {"label": "Result", "content": "Treatment showed improvement"},
            {"label": "Follow-up", "content": "12-month follow-up period"},
        ],
        "citation": "Smith et al. (2025). Journal of Medicine.",
    }
    mock_llm.generate_json_with_schema.side_effect = [valid_transcript, short_synopsis_summary]

    extraction = {
        "interventions": [{"name": "Drug X"}],
        "outcomes": {"primary": {"description": "mortality"}},
    }
    appraisal = {"grade": {"certainty_overall": "high"}}

    result = run_podcast_generation(
        extraction_result=extraction,
        appraisal_result=appraisal,
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    # Podcast should still succeed (summary failure is non-fatal)
    assert result["status"] == "success"

    # show_summary should NOT be merged (validation failed)
    assert "show_summary" not in result["podcast"]

    # Summary validation should be "failed"
    summary_val = result["validation"]["summary_validation"]
    assert summary_val["status"] == "failed"
    assert any("Synopsis too short" in issue for issue in summary_val["critical_issues"])


@patch("src.pipeline.podcast_logic.load_podcast_summary_prompt")
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_show_summary_validation_synopsis_too_long(
    mock_get_llm,
    mock_load_prompt,
    mock_load_schema,
    mock_load_summary_prompt,
    mock_file_manager,
    mock_llm,
):
    """Test that synopsis > 500 chars fails summary validation and is NOT merged."""
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {
        "type": "object",
        "properties": {
            "show_summary": {
                "type": "object",
                "properties": {
                    "synopsis": {"type": "string"},
                    "study_at_a_glance": {"type": "array"},
                    "citation": {"type": "string"},
                },
            }
        },
    }
    mock_load_prompt.return_value = "Generate podcast"
    mock_load_summary_prompt.return_value = "Generate show summary"

    # First call returns transcript, second call returns summary with long synopsis
    valid_transcript = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test Podcast", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This study examined mortality outcomes and found significant results. " * 90,
    }
    long_synopsis_summary = {
        "synopsis": "A" * 501,  # 501 chars, above 500-char maximum
        "study_at_a_glance": [
            {"label": "Design", "content": "Randomized controlled trial"},
            {"label": "Result", "content": "Treatment showed improvement"},
            {"label": "Follow-up", "content": "12-month follow-up period"},
        ],
        "citation": "Smith et al. (2025). Journal of Medicine.",
    }
    mock_llm.generate_json_with_schema.side_effect = [valid_transcript, long_synopsis_summary]

    extraction = {
        "interventions": [{"name": "Drug X"}],
        "outcomes": {"primary": {"description": "mortality"}},
    }
    appraisal = {"grade": {"certainty_overall": "high"}}

    result = run_podcast_generation(
        extraction_result=extraction,
        appraisal_result=appraisal,
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    # Podcast should still succeed (summary failure is non-fatal)
    assert result["status"] == "success"

    # show_summary should NOT be merged (validation failed)
    assert "show_summary" not in result["podcast"]

    # Summary validation should be "failed"
    summary_val = result["validation"]["summary_validation"]
    assert summary_val["status"] == "failed"
    assert any("Synopsis too long" in issue for issue in summary_val["critical_issues"])
