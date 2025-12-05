"""
Unit tests for the iterative module.

Tests cover:
- IterationData dataclass
- IterationTracker class
- detect_quality_degradation function
- Legacy format compatibility
"""

from datetime import datetime
from pathlib import Path

import pytest

from src.pipeline.iterative import (
    IterationData,
    IterationTracker,
    detect_quality_degradation,
    select_best_iteration,
)
from src.pipeline.quality import MetricType, QualityMetrics


class TestIterationData:
    """Tests for IterationData dataclass."""

    def test_creation(self):
        """Test creating IterationData with required fields."""
        metrics = QualityMetrics(quality_score=0.85, completeness_score=0.90)
        iteration = IterationData(
            iteration_num=0,
            result={"key": "value"},
            validation={"status": "passed"},
            metrics=metrics,
        )

        assert iteration.iteration_num == 0
        assert iteration.result == {"key": "value"}
        assert iteration.validation == {"status": "passed"}
        assert iteration.metrics.quality_score == 0.85
        assert iteration.result_path is None
        assert iteration.validation_path is None
        assert isinstance(iteration.timestamp, datetime)

    def test_with_paths(self):
        """Test IterationData with file paths."""
        metrics = QualityMetrics(quality_score=0.85)
        result_path = Path("/tmp/result.json")
        validation_path = Path("/tmp/validation.json")

        iteration = IterationData(
            iteration_num=1,
            result={},
            validation={},
            metrics=metrics,
            result_path=result_path,
            validation_path=validation_path,
        )

        assert iteration.result_path == result_path
        assert iteration.validation_path == validation_path

    def test_to_dict(self):
        """Test serialization to dict."""
        metrics = QualityMetrics(quality_score=0.85, completeness_score=0.90)
        iteration = IterationData(
            iteration_num=0,
            result={"key": "value"},
            validation={"status": "passed"},
            metrics=metrics,
        )

        result = iteration.to_dict()

        assert result["iteration_num"] == 0
        assert result["result"] == {"key": "value"}
        assert result["metrics"]["quality_score"] == 0.85
        assert "timestamp" in result

    def test_to_legacy_dict(self):
        """Test conversion to legacy dict format."""
        metrics = QualityMetrics(quality_score=0.85)
        result_path = Path("/tmp/result.json")

        iteration = IterationData(
            iteration_num=0,
            result={"key": "value"},
            validation={"status": "passed"},
            metrics=metrics,
            result_path=result_path,
        )

        legacy = iteration.to_legacy_dict()

        assert legacy["iteration_num"] == 0
        assert legacy["result"] == {"key": "value"}
        assert legacy["result_path"] == result_path
        assert isinstance(legacy["metrics"], dict)


class TestIterationTracker:
    """Tests for IterationTracker class."""

    def test_initialization(self):
        """Test tracker initialization."""
        tracker = IterationTracker(metric_type=MetricType.EXTRACTION)

        assert tracker.metric_type == MetricType.EXTRACTION
        assert tracker.degradation_window == 2
        assert tracker.iteration_count == 0
        assert tracker.current_iteration_num == 0

    def test_add_iteration(self):
        """Test adding iterations."""
        tracker = IterationTracker(metric_type=MetricType.EXTRACTION)
        metrics = QualityMetrics(quality_score=0.85)

        iteration = tracker.add_iteration(
            result={"data": "test"},
            validation={"status": "passed"},
            metrics=metrics,
        )

        assert iteration.iteration_num == 0
        assert tracker.iteration_count == 1
        assert tracker.current_iteration_num == 1

    def test_add_multiple_iterations(self):
        """Test adding multiple iterations."""
        tracker = IterationTracker(metric_type=MetricType.EXTRACTION)

        for i in range(3):
            metrics = QualityMetrics(quality_score=0.80 + i * 0.05)
            tracker.add_iteration(
                result={"iteration": i},
                validation={},
                metrics=metrics,
            )

        assert tracker.iteration_count == 3
        assert tracker.current_iteration_num == 3

    def test_get_iteration(self):
        """Test getting iteration by number."""
        tracker = IterationTracker(metric_type=MetricType.EXTRACTION)
        metrics = QualityMetrics(quality_score=0.85)
        tracker.add_iteration(result={}, validation={}, metrics=metrics)

        iteration = tracker.get_iteration(0)
        assert iteration is not None
        assert iteration.metrics.quality_score == 0.85

        # Invalid index
        assert tracker.get_iteration(5) is None
        assert tracker.get_iteration(-1) is None

    def test_get_latest_iteration(self):
        """Test getting latest iteration."""
        tracker = IterationTracker(metric_type=MetricType.EXTRACTION)

        # Empty tracker
        assert tracker.get_latest_iteration() is None

        # After adding
        metrics1 = QualityMetrics(quality_score=0.80)
        tracker.add_iteration(result={"v": 1}, validation={}, metrics=metrics1)

        metrics2 = QualityMetrics(quality_score=0.90)
        tracker.add_iteration(result={"v": 2}, validation={}, metrics=metrics2)

        latest = tracker.get_latest_iteration()
        assert latest is not None
        assert latest.result == {"v": 2}
        assert latest.metrics.quality_score == 0.90

    def test_get_quality_scores(self):
        """Test getting quality scores from all iterations."""
        tracker = IterationTracker(metric_type=MetricType.EXTRACTION)

        for score in [0.80, 0.85, 0.90]:
            metrics = QualityMetrics(quality_score=score)
            tracker.add_iteration(result={}, validation={}, metrics=metrics)

        scores = tracker.get_quality_scores()
        assert scores == [0.80, 0.85, 0.90]

    def test_get_peak_quality(self):
        """Test getting peak quality score."""
        tracker = IterationTracker(metric_type=MetricType.EXTRACTION)

        # Empty tracker
        assert tracker.get_peak_quality() == 0.0

        # With iterations
        for score in [0.80, 0.92, 0.88]:
            metrics = QualityMetrics(quality_score=score)
            tracker.add_iteration(result={}, validation={}, metrics=metrics)

        assert tracker.get_peak_quality() == 0.92

    def test_get_improvement_trajectory(self):
        """Test getting improvement trajectory."""
        tracker = IterationTracker(metric_type=MetricType.EXTRACTION)

        # Not enough iterations
        metrics = QualityMetrics(quality_score=0.80)
        tracker.add_iteration(result={}, validation={}, metrics=metrics)
        assert tracker.get_improvement_trajectory() == []

        # Add more
        for score in [0.85, 0.82]:
            metrics = QualityMetrics(quality_score=score)
            tracker.add_iteration(result={}, validation={}, metrics=metrics)

        trajectory = tracker.get_improvement_trajectory()
        assert len(trajectory) == 2
        assert trajectory[0] == pytest.approx(0.05)  # 0.85 - 0.80
        assert trajectory[1] == pytest.approx(-0.03)  # 0.82 - 0.85

    def test_detect_degradation_via_tracker(self):
        """Test degradation detection through tracker."""
        tracker = IterationTracker(metric_type=MetricType.EXTRACTION, degradation_window=2)

        # Add improving iterations
        for score in [0.80, 0.88]:
            metrics = QualityMetrics(quality_score=score)
            tracker.add_iteration(result={}, validation={}, metrics=metrics)

        assert tracker.detect_degradation() is False

        # Add degrading iterations
        for score in [0.85, 0.82]:
            metrics = QualityMetrics(quality_score=score)
            tracker.add_iteration(result={}, validation={}, metrics=metrics)

        assert tracker.detect_degradation() is True

    def test_to_legacy_list(self):
        """Test conversion to legacy list format."""
        tracker = IterationTracker(metric_type=MetricType.EXTRACTION)

        metrics = QualityMetrics(quality_score=0.85)
        tracker.add_iteration(
            result={"data": "test"},
            validation={"status": "ok"},
            metrics=metrics,
        )

        legacy_list = tracker.to_legacy_list()

        assert len(legacy_list) == 1
        assert legacy_list[0]["iteration_num"] == 0
        assert legacy_list[0]["result"] == {"data": "test"}
        assert isinstance(legacy_list[0]["metrics"], dict)


class TestDetectQualityDegradation:
    """Tests for detect_quality_degradation function."""

    def test_not_enough_iterations(self):
        """Test with insufficient iterations."""
        # Need at least window + 1 iterations
        iterations = [{"metrics": {"quality_score": 0.85}}]
        assert detect_quality_degradation(iterations, window=2) is False

        iterations = [
            {"metrics": {"quality_score": 0.85}},
            {"metrics": {"quality_score": 0.90}},
        ]
        assert detect_quality_degradation(iterations, window=2) is False

    def test_no_degradation(self):
        """Test when quality is improving."""
        iterations = [
            {"metrics": {"quality_score": 0.80}},
            {"metrics": {"quality_score": 0.85}},
            {"metrics": {"quality_score": 0.90}},
        ]
        assert detect_quality_degradation(iterations, window=2) is False

    def test_degradation_detected(self):
        """Test when quality is degrading."""
        iterations = [
            {"metrics": {"quality_score": 0.85}},
            {"metrics": {"quality_score": 0.88}},  # Peak
            {"metrics": {"quality_score": 0.86}},  # Degraded
            {"metrics": {"quality_score": 0.84}},  # Degraded again
        ]
        assert detect_quality_degradation(iterations, window=2) is True

    def test_single_degradation_not_triggered(self):
        """Test that single degradation doesn't trigger with window=2."""
        iterations = [
            {"metrics": {"quality_score": 0.85}},
            {"metrics": {"quality_score": 0.90}},  # Peak
            {"metrics": {"quality_score": 0.88}},  # Single degradation
        ]
        # Only one iteration worse than peak, need 2
        assert detect_quality_degradation(iterations, window=2) is False

    def test_with_overall_quality_key(self):
        """Test with legacy overall_quality key (extraction)."""
        iterations = [
            {"metrics": {"overall_quality": 0.85}},
            {"metrics": {"overall_quality": 0.90}},
            {"metrics": {"overall_quality": 0.87}},
            {"metrics": {"overall_quality": 0.84}},
        ]
        assert detect_quality_degradation(iterations, window=2) is True

    def test_with_iteration_data_objects(self):
        """Test with IterationData objects instead of dicts."""
        iterations = [
            IterationData(
                iteration_num=0,
                result={},
                validation={},
                metrics=QualityMetrics(quality_score=0.85),
            ),
            IterationData(
                iteration_num=1,
                result={},
                validation={},
                metrics=QualityMetrics(quality_score=0.90),
            ),
            IterationData(
                iteration_num=2,
                result={},
                validation={},
                metrics=QualityMetrics(quality_score=0.87),
            ),
            IterationData(
                iteration_num=3,
                result={},
                validation={},
                metrics=QualityMetrics(quality_score=0.84),
            ),
        ]
        assert detect_quality_degradation(iterations, window=2) is True

    def test_window_parameter(self):
        """Test different window sizes."""
        iterations = [
            {"metrics": {"quality_score": 0.90}},  # Peak
            {"metrics": {"quality_score": 0.88}},
            {"metrics": {"quality_score": 0.86}},
            {"metrics": {"quality_score": 0.84}},
        ]

        # Window=2: last 2 (0.86, 0.84) worse than peak
        assert detect_quality_degradation(iterations, window=2) is True

        # Window=3: last 3 (0.88, 0.86, 0.84) all worse than peak
        assert detect_quality_degradation(iterations, window=3) is True

        # Window=4: need 5 iterations, only have 4
        assert detect_quality_degradation(iterations, window=4) is False


class TestSelectBestIterationReexport:
    """Test that select_best_iteration is properly re-exported."""

    def test_import_works(self):
        """Test that select_best_iteration can be imported from iterative module."""
        from src.pipeline.iterative import select_best_iteration

        assert callable(select_best_iteration)

    def test_basic_functionality(self):
        """Test basic select_best_iteration functionality."""
        iterations = [
            {
                "iteration_num": 0,
                "metrics": {
                    "quality_score": 0.85,
                    "completeness_score": 0.90,
                    "critical_issues": 0,
                },
            },
            {
                "iteration_num": 1,
                "metrics": {
                    "quality_score": 0.92,
                    "completeness_score": 0.95,
                    "critical_issues": 0,
                },
            },
        ]

        best = select_best_iteration(iterations, MetricType.EXTRACTION)

        assert best["iteration_num"] == 1
        assert best["selection_reason"] == "final_iteration_best"
