# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for src/streamlit_app/screens/execution.py

Tests execution screen state management, callback handlers, and helper functions.
Uses mocking to avoid Streamlit dependency and real pipeline execution.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

# Import functions to test
from src.streamlit_app.screens.execution import (
    _check_validation_warnings,
    _extract_token_usage,
    create_progress_callback,
    init_execution_state,
    reset_execution_state,
)

pytestmark = pytest.mark.unit


class MockSessionState(dict):
    """Mock Streamlit session_state that supports both dict and attribute access."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as err:
            raise AttributeError(f"'MockSessionState' object has no attribute '{key}'") from err

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError as err:
            raise AttributeError(f"'MockSessionState' object has no attribute '{key}'") from err


class TestStateManagement:
    """Test execution state initialization and reset."""

    @patch("src.streamlit_app.screens.execution.st")
    def test_init_execution_state(self, mock_st):
        """Test that init_execution_state() initializes all state correctly."""
        # Arrange: Mock session_state
        mock_st.session_state = MockSessionState()

        # Act: Initialize execution state
        init_execution_state()

        # Assert: Execution state initialized
        assert "execution" in mock_st.session_state
        execution = mock_st.session_state["execution"]
        assert execution["status"] == "idle"
        assert execution["start_time"] is None
        assert execution["end_time"] is None
        assert execution["error"] is None
        assert execution["results"] is None
        assert execution["auto_redirect_enabled"] is False  # Changed: timer disabled
        assert execution["redirect_cancelled"] is False
        assert execution["redirect_countdown"] is None

        # Assert: Step status initialized for all 6 steps (including podcast_generation)
        assert "step_status" in mock_st.session_state
        step_status = mock_st.session_state["step_status"]
        assert len(step_status) == 6
        for step_name in [
            "classification",
            "extraction",
            "validation_correction",
            "appraisal",
            "report_generation",
            "podcast_generation",
        ]:
            assert step_name in step_status
            step = step_status[step_name]
            assert step["status"] == "pending"
            assert step["start_time"] is None
            assert step["end_time"] is None
            assert step["result"] is None
            assert step["error"] is None
            assert step["elapsed_seconds"] is None
            assert step["verbose_data"] == {}

    @patch("src.streamlit_app.screens.execution.st")
    def test_reset_execution_state(self, mock_st):
        """Test that reset_execution_state() resets all state to initial values."""
        # Arrange: Mock session_state with completed execution
        mock_st.session_state = MockSessionState(
            {
                "execution": {
                    "status": "completed",
                    "start_time": datetime.now(),
                    "end_time": datetime.now(),
                    "error": "Some error",
                    "results": {"data": "value"},
                    "auto_redirect_enabled": False,
                    "redirect_cancelled": True,
                    "redirect_countdown": 0,
                },
                "step_status": {
                    "classification": {
                        "status": "success",
                        "start_time": datetime.now(),
                        "end_time": datetime.now(),
                        "result": {"publication_type": "interventional_trial"},
                        "error": None,
                        "elapsed_seconds": 10.5,
                        "verbose_data": {"starting": {}},
                    }
                },
            }
        )

        # Act: Reset execution state
        reset_execution_state()

        # Assert: Execution state reset to idle
        execution = mock_st.session_state["execution"]
        assert execution["status"] == "idle"
        assert execution["start_time"] is None
        assert execution["end_time"] is None
        assert execution["error"] is None
        assert execution["results"] is None
        assert execution["auto_redirect_enabled"] is False  # Changed: timer disabled
        assert execution["redirect_cancelled"] is False
        assert execution["redirect_countdown"] is None

        # Assert: Step status reset for all 6 steps (including podcast_generation)
        step_status = mock_st.session_state["step_status"]
        assert len(step_status) == 6
        for step_name in [
            "classification",
            "extraction",
            "validation_correction",
            "appraisal",
            "report_generation",
            "podcast_generation",
        ]:
            assert step_name in step_status
            step = step_status[step_name]
            assert step["status"] == "pending"
            assert step["start_time"] is None
            assert step["end_time"] is None
            assert step["result"] is None
            assert step["error"] is None
            assert step["elapsed_seconds"] is None
            assert step["verbose_data"] == {}


class TestProgressCallback:
    """Test progress callback handler logic."""

    @patch("src.streamlit_app.screens.execution.st")
    def test_progress_callback_starting(self, mock_st):
        """Test callback updates step to 'running' status on 'starting' event."""
        # Arrange: Mock session_state with initialized step_status
        mock_st.session_state = MockSessionState(
            {
                "step_status": {
                    "classification": {
                        "status": "pending",
                        "start_time": None,
                        "end_time": None,
                        "result": None,
                        "error": None,
                        "elapsed_seconds": None,
                        "verbose_data": {},
                    }
                }
            }
        )

        # Act: Create callback and call with "starting" status
        callback = create_progress_callback()
        callback("classification", "starting", {"pdf_path": "test.pdf", "max_pages": 10})

        # Assert: Step status updated to "running"
        step = mock_st.session_state["step_status"]["classification"]
        assert step["status"] == "running"
        assert step["start_time"] is not None
        assert isinstance(step["start_time"], datetime)
        assert "starting" in step["verbose_data"]
        assert step["verbose_data"]["starting"]["pdf_path"] == "test.pdf"
        assert step["verbose_data"]["starting"]["max_pages"] == 10

    @patch("src.streamlit_app.screens.execution.st")
    def test_progress_callback_completed(self, mock_st):
        """Test callback updates step to 'success' status on 'completed' event."""
        # Arrange: Mock session_state with running step
        start_time = datetime.now()
        mock_st.session_state = MockSessionState(
            {
                "settings": {
                    "steps_to_run": ["classification", "extraction"],
                },
                "step_status": {
                    "classification": {
                        "status": "running",
                        "start_time": start_time,
                        "end_time": None,
                        "result": None,
                        "error": None,
                        "elapsed_seconds": None,
                        "verbose_data": {},
                    },
                    "extraction": {
                        "status": "pending",
                        "start_time": None,
                        "end_time": None,
                        "result": None,
                        "error": None,
                        "elapsed_seconds": None,
                        "verbose_data": {},
                    },
                },
            }
        )

        # Act: Create callback and call with "completed" status
        callback = create_progress_callback()
        callback(
            "classification",
            "completed",
            {
                "result": {"publication_type": "interventional_trial"},
                "elapsed_seconds": 8.3,
                "file_path": "tmp/test-classification.json",
            },
        )

        # Assert: Step status updated to "success"
        step = mock_st.session_state["step_status"]["classification"]
        assert step["status"] == "success"
        assert step["end_time"] is not None
        assert isinstance(step["end_time"], datetime)
        assert step["result"] == {"publication_type": "interventional_trial"}
        assert step["elapsed_seconds"] == 8.3
        assert step["file_path"] == "tmp/test-classification.json"
        assert "completed" in step["verbose_data"]

        # Assert: Next step (extraction) marked as running
        next_step = mock_st.session_state["step_status"]["extraction"]
        assert next_step["status"] == "running"
        assert next_step["start_time"] is not None
        assert isinstance(next_step["start_time"], datetime)

    @patch("src.streamlit_app.screens.execution.st")
    def test_progress_callback_failed(self, mock_st):
        """Test callback updates step to 'failed' status on 'failed' event."""
        # Arrange: Mock session_state with running step
        start_time = datetime.now()
        mock_st.session_state = MockSessionState(
            {
                "settings": {
                    "steps_to_run": ["classification"],
                },
                "step_status": {
                    "classification": {
                        "status": "running",
                        "start_time": start_time,
                        "end_time": None,
                        "result": None,
                        "error": None,
                        "elapsed_seconds": None,
                        "verbose_data": {},
                    }
                },
            }
        )

        # Act: Create callback and call with "failed" status
        callback = create_progress_callback()
        callback(
            "classification",
            "failed",
            {
                "error": "API key invalid",
                "error_type": "AuthenticationError",
                "elapsed_seconds": 2.1,
            },
        )

        # Assert: Step status updated to "failed"
        step = mock_st.session_state["step_status"]["classification"]
        assert step["status"] == "failed"
        assert step["end_time"] is not None
        assert isinstance(step["end_time"], datetime)
        assert step["error"] == "API key invalid"
        assert step["elapsed_seconds"] == 2.1
        assert "failed" in step["verbose_data"]
        assert step["verbose_data"]["failed"]["error_type"] == "AuthenticationError"


class TestHelperFunctions:
    """Test helper utility functions."""

    def test_extract_token_usage_openai_format(self):
        """Test token extraction from OpenAI format response."""
        # Arrange: OpenAI format result
        result = {"usage": {"input_tokens": 1000, "output_tokens": 250}}

        # Act: Extract token usage
        token_usage = _extract_token_usage(result)

        # Assert: Standardized format returned
        assert token_usage is not None
        assert token_usage["input"] == 1000
        assert token_usage["output"] == 250
        assert token_usage["total"] == 1250

    def test_extract_token_usage_claude_format(self):
        """Test token extraction from Claude format response."""
        # Arrange: Claude format result
        result = {"usage": {"prompt_tokens": 500, "completion_tokens": 150}}

        # Act: Extract token usage
        token_usage = _extract_token_usage(result)

        # Assert: Standardized format returned
        assert token_usage is not None
        assert token_usage["input"] == 500
        assert token_usage["output"] == 150
        assert token_usage["total"] == 650

    def test_extract_token_usage_missing_usage(self):
        """Test token extraction returns None when usage data missing."""
        # Arrange: Result without usage data
        result = {"data": "value"}

        # Act: Extract token usage
        token_usage = _extract_token_usage(result)

        # Assert: None returned
        assert token_usage is None

    def test_extract_token_usage_empty_result(self):
        """Test token extraction handles empty result."""
        # Arrange: Empty result
        result = {}

        # Act: Extract token usage
        token_usage = _extract_token_usage(result)

        # Assert: None returned
        assert token_usage is None

    def test_check_validation_warnings_low_quality_score(self):
        """Test validation warning detected for low quality score."""
        # Arrange: Validation result with low quality score
        result = {"is_valid": True, "quality_score": 6, "errors": []}

        # Act: Check for warnings
        warnings = _check_validation_warnings(result)

        # Assert: Warning about low quality score
        assert len(warnings) == 1
        assert "quality score is 6/10" in warnings[0].lower()
        assert "below recommended 8" in warnings[0].lower()

    def test_check_validation_warnings_minor_schema_errors(self):
        """Test validation warning detected for minor schema errors."""
        # Arrange: Validation result with errors but passed
        result = {
            "is_valid": True,
            "quality_score": 9,
            "errors": ["Field X missing", "Field Y empty"],
        }

        # Act: Check for warnings
        warnings = _check_validation_warnings(result)

        # Assert: Warning about minor errors
        assert len(warnings) == 1
        assert "2 minor schema issue(s)" in warnings[0]
        assert "validation passed" in warnings[0]

    def test_check_validation_warnings_no_warnings(self):
        """Test no warnings for valid result with good quality score."""
        # Arrange: Validation result with good quality score
        result = {"is_valid": True, "quality_score": 9, "errors": []}

        # Act: Check for warnings
        warnings = _check_validation_warnings(result)

        # Assert: No warnings
        assert len(warnings) == 0

    def test_check_validation_warnings_multiple_issues(self):
        """Test multiple warnings detected simultaneously."""
        # Arrange: Validation result with low score AND minor errors
        result = {"is_valid": True, "quality_score": 7, "errors": ["Field X issue"]}

        # Act: Check for warnings
        warnings = _check_validation_warnings(result)

        # Assert: Both warnings present
        assert len(warnings) == 2
        assert any("quality score is 7/10" in w.lower() for w in warnings)
        assert any("1 minor schema issue(s)" in w for w in warnings)
