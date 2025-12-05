"""
Iteration tracking and quality degradation detection.

This module provides IterationData and IterationTracker classes for managing
iteration state during iterative correction loops, replacing the inline
tracking logic in orchestrator.py.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..quality.metrics import MetricType, QualityMetrics


@dataclass
class IterationData:
    """
    Data for a single iteration in an iterative correction loop.

    Attributes:
        iteration_num: Iteration number (0-indexed)
        result: The extraction/appraisal/report result dict
        validation: The validation result dict
        metrics: Extracted quality metrics
        result_path: Path to saved result file (optional)
        validation_path: Path to saved validation file (optional)
        timestamp: When this iteration was created
    """

    iteration_num: int
    result: dict
    validation: dict
    metrics: QualityMetrics
    result_path: Path | None = None
    validation_path: Path | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dict for serialization and compatibility with existing code."""
        return {
            "iteration_num": self.iteration_num,
            "result": self.result,
            "validation": self.validation,
            "metrics": self.metrics.to_dict(),
            "result_path": str(self.result_path) if self.result_path else None,
            "validation_path": str(self.validation_path) if self.validation_path else None,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_legacy_dict(self) -> dict:
        """
        Convert to legacy dict format for backward compatibility.

        The existing orchestrator code expects iterations in this format:
        {
            'iteration_num': int,
            'result': dict,
            'validation': dict,
            'metrics': dict (not QualityMetrics),
            'result_path': Path,
            'validation_path': Path,
        }
        """
        return {
            "iteration_num": self.iteration_num,
            "result": self.result,
            "validation": self.validation,
            "metrics": self.metrics.to_dict(),
            "result_path": self.result_path,
            "validation_path": self.validation_path,
        }


class IterationTracker:
    """
    Tracks iteration history and manages state for iterative correction loops.

    This class consolidates the iteration tracking logic that was previously
    spread across multiple places in orchestrator.py.

    Example:
        >>> tracker = IterationTracker(metric_type=MetricType.EXTRACTION)
        >>> tracker.add_iteration(result, validation, metrics)
        >>> if tracker.detect_degradation():
        ...     best = tracker.get_best_iteration()
    """

    def __init__(self, metric_type: MetricType, degradation_window: int = 2):
        """
        Initialize the iteration tracker.

        Args:
            metric_type: Type of metrics being tracked (EXTRACTION, APPRAISAL, REPORT)
            degradation_window: Number of consecutive degrading iterations to trigger early stop
        """
        self.metric_type = metric_type
        self.degradation_window = degradation_window
        self._iterations: list[IterationData] = []

    @property
    def iterations(self) -> list[IterationData]:
        """Get all iterations."""
        return self._iterations

    @property
    def iteration_count(self) -> int:
        """Get number of iterations."""
        return len(self._iterations)

    @property
    def current_iteration_num(self) -> int:
        """Get current iteration number (next iteration to run)."""
        return len(self._iterations)

    def add_iteration(
        self,
        result: dict,
        validation: dict,
        metrics: QualityMetrics,
        result_path: Path | None = None,
        validation_path: Path | None = None,
    ) -> IterationData:
        """
        Add a new iteration to the tracker.

        Args:
            result: The extraction/appraisal/report result
            validation: The validation result
            metrics: Extracted quality metrics
            result_path: Path to saved result file
            validation_path: Path to saved validation file

        Returns:
            The created IterationData instance
        """
        iteration = IterationData(
            iteration_num=len(self._iterations),
            result=result,
            validation=validation,
            metrics=metrics,
            result_path=result_path,
            validation_path=validation_path,
        )
        self._iterations.append(iteration)
        return iteration

    def get_iteration(self, iteration_num: int) -> IterationData | None:
        """Get iteration by number."""
        if 0 <= iteration_num < len(self._iterations):
            return self._iterations[iteration_num]
        return None

    def get_latest_iteration(self) -> IterationData | None:
        """Get the most recent iteration."""
        if self._iterations:
            return self._iterations[-1]
        return None

    def get_quality_scores(self) -> list[float]:
        """Get quality scores from all iterations."""
        return [it.metrics.quality_score for it in self._iterations]

    def get_peak_quality(self) -> float:
        """Get the highest quality score achieved."""
        scores = self.get_quality_scores()
        return max(scores) if scores else 0.0

    def get_improvement_trajectory(self) -> list[float]:
        """
        Get quality improvement trajectory.

        Returns list of quality deltas between consecutive iterations.
        Positive = improvement, negative = degradation.
        """
        scores = self.get_quality_scores()
        if len(scores) < 2:
            return []
        return [scores[i] - scores[i - 1] for i in range(1, len(scores))]

    def detect_degradation(self, window: int | None = None) -> bool:
        """
        Detect if quality has been degrading for the last N iterations.

        Early stopping prevents wasted LLM calls when corrections are making things worse.

        Args:
            window: Number of consecutive degrading iterations to trigger stop
                   (defaults to self.degradation_window)

        Returns:
            True if quality degraded for 'window' consecutive iterations

        Logic:
            - Need at least (window + 1) iterations to detect trend
            - Compare last 'window' iterations against the OVERALL best score
            - Degradation = all iterations in window are worse than peak
        """
        if window is None:
            window = self.degradation_window

        return detect_quality_degradation(self._iterations, window)

    def to_legacy_list(self) -> list[dict]:
        """
        Convert iterations to legacy list format for backward compatibility.

        Returns list of dicts in the format expected by existing orchestrator code.
        """
        return [it.to_legacy_dict() for it in self._iterations]


def detect_quality_degradation(
    iterations: list[IterationData] | list[dict], window: int = 2
) -> bool:
    """
    Detect if quality has been degrading for the last N iterations.

    This function replaces _detect_quality_degradation() in orchestrator.py
    and works with both IterationData instances and legacy dict format.

    Args:
        iterations: List of iterations (IterationData or dict with 'metrics')
        window: Number of consecutive degrading iterations to trigger stop (default: 2)

    Returns:
        True if quality degraded for 'window' consecutive iterations

    Example:
        >>> iterations = [
        ...     {'metrics': {'quality_score': 0.85}},  # iter 0
        ...     {'metrics': {'quality_score': 0.88}},  # iter 1 (BEST)
        ...     {'metrics': {'quality_score': 0.86}},  # iter 2 (degraded)
        ...     {'metrics': {'quality_score': 0.84}}   # iter 3 (degraded again)
        ... ]
        >>> detect_quality_degradation(iterations, window=2)
        True
    """
    if len(iterations) < window + 1:
        return False

    # Extract quality scores, handling both IterationData and dict formats
    scores = []
    for it in iterations:
        if isinstance(it, IterationData):
            scores.append(it.metrics.quality_score)
        else:
            # Legacy dict format
            metrics = it.get("metrics", {})
            if isinstance(metrics, QualityMetrics):
                scores.append(metrics.quality_score)
            else:
                # Dict metrics - try quality_score, then overall_quality (extraction legacy)
                score = metrics.get("quality_score", metrics.get("overall_quality", 0))
                scores.append(score)

    # Find OVERALL peak quality
    peak_quality = max(scores)

    # Check if last 'window' iterations are ALL worse than peak
    window_scores = scores[-window:]
    all_degraded = all(score < peak_quality for score in window_scores)

    return all_degraded
