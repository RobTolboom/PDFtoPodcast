"""
Iterative correction loop module.

This module provides iteration tracking, quality degradation detection,
best iteration selection, and the generic IterativeLoopRunner for
the iterative validation/correction loops.

Public API:
    - IterationData: Dataclass for single iteration data
    - IterationTracker: Tracks iteration history and detects degradation
    - detect_quality_degradation: Check if quality is degrading
    - select_best_iteration: Select best iteration from list (re-exported from quality)
    - IterativeLoopConfig: Configuration for loop runner
    - IterativeLoopResult: Result from loop runner
    - IterativeLoopRunner: Generic iterative correction loop runner
"""

from ..quality.scoring import select_best_iteration
from .iteration_tracker import IterationData, IterationTracker, detect_quality_degradation
from .loop_runner import IterativeLoopConfig, IterativeLoopResult, IterativeLoopRunner

__all__ = [
    # Iteration tracking
    "IterationData",
    "IterationTracker",
    "detect_quality_degradation",
    "select_best_iteration",
    # Loop runner
    "IterativeLoopConfig",
    "IterativeLoopResult",
    "IterativeLoopRunner",
]
