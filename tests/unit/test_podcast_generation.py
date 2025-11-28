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
    llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Test Podcast", "word_count": 1000, "estimated_duration_minutes": 6},
        "transcript": "This is a test transcript that is long enough to pass validation. " * 50,
    }
    return llm


@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_run_podcast_generation_success(
    mock_get_llm, mock_load_prompt, mock_load_schema, mock_file_manager, mock_llm
):
    # Setup mocks
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast from {{EXTRACTION_JSON}}"

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

    # Verify
    assert result["status"] == "success"
    assert result["podcast"]["metadata"]["title"] == "Test Podcast"
    assert result["validation"]["status"] == "passed"

    # Verify LLM call
    mock_llm.generate_json_with_schema.assert_called_once()

    # Verify file saving
    mock_file_manager.save_json.assert_any_call(result["podcast"], "podcast")
    mock_file_manager.save_json.assert_any_call(result["validation"], "podcast_validation")


@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_run_podcast_generation_validation_warning(
    mock_get_llm, mock_load_prompt, mock_load_schema, mock_file_manager, mock_llm
):
    # Setup mocks
    mock_get_llm.return_value = mock_llm
    mock_load_schema.return_value = {"type": "object"}
    mock_load_prompt.return_value = "Generate podcast"

    # Return short transcript with abbreviation
    mock_llm.generate_json_with_schema.return_value = {
        "podcast_version": "v1.0",
        "metadata": {"title": "Short", "word_count": 100, "estimated_duration_minutes": 1},
        "transcript": "Short transcript with ICU abbreviation.",
    }

    # Run function
    result = run_podcast_generation(
        extraction_result={},
        appraisal_result={},
        classification_result={},
        llm_provider="openai",
        file_manager=mock_file_manager,
    )

    # Verify warnings
    assert result["status"] == "success"  # Still success, but with warnings
    assert result["validation"]["status"] == "warnings"
    assert any("too short" in issue for issue in result["validation"]["issues"])
    assert any("abbreviations" in issue for issue in result["validation"]["issues"])


@patch("src.pipeline.podcast_logic.render_podcast_to_markdown")
@patch("src.pipeline.podcast_logic.load_schema")
@patch("src.pipeline.podcast_logic.load_podcast_generation_prompt")
@patch("src.pipeline.podcast_logic.get_llm_provider")
def test_run_podcast_generation_creates_markdown(
    mock_get_llm, mock_load_prompt, mock_load_schema, mock_render, mock_file_manager, mock_llm
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
