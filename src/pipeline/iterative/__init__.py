"""
Iterative correction loop module.

This module provides iteration tracking, quality degradation detection,
and best iteration selection for the iterative validation/correction loops.

Public API:
    - IterationData: Dataclass for single iteration data
    - IterationTracker: Tracks iteration history and detects degradation
    - detect_quality_degradation: Check if quality is degrading
    - select_best_iteration: Select best iteration from list (re-exported from quality)
"""

from ..quality.scoring import select_best_iteration
from .iteration_tracker import IterationData, IterationTracker, detect_quality_degradation

__all__ = [
    "IterationData",
    "IterationTracker",
    "detect_quality_degradation",
    "select_best_iteration",
]
