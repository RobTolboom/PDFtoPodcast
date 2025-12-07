# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Podcast step module.

Re-exports podcast generation functionality from podcast_logic.py for
consistency with other step modules.
"""

from ..podcast_logic import (
    PODCAST_MAX_WORDS,
    PODCAST_MIN_WORDS,
    STEP_PODCAST_GENERATION,
    WORDS_PER_MINUTE,
    run_podcast_generation,
)

__all__ = [
    "run_podcast_generation",
    "STEP_PODCAST_GENERATION",
    "PODCAST_MIN_WORDS",
    "PODCAST_MAX_WORDS",
    "WORDS_PER_MINUTE",
]
