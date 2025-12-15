# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Centralized version retrieval for pipeline metadata.

This module provides a single source of truth for the pipeline version,
used in report metadata and other contexts.
"""

import functools
import re
from pathlib import Path


@functools.cache
def get_pipeline_version() -> str:
    """
    Retrieve pipeline version from installed package or pyproject.toml.

    Attempts to get version from:
    1. Installed package metadata (importlib.metadata)
    2. pyproject.toml [project] section (fallback for development)
    3. Returns "0.0.0" if neither is available

    Returns:
        str: Version string (e.g., "0.1.0")

    Example:
        >>> from src.pipeline.version import get_pipeline_version
        >>> version = get_pipeline_version()
        >>> print(f"Pipeline v{version}")
        Pipeline v0.1.0
    """
    # Try installed package first
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("pdftopodcast")
    except ImportError:
        pass
    except PackageNotFoundError:
        pass

    # Fallback: parse pyproject.toml
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject_path.exists():
        in_project_section = False
        for line in pyproject_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "[project]":
                in_project_section = True
            elif stripped.startswith("[") and stripped.endswith("]"):
                in_project_section = False
            elif in_project_section and stripped.startswith("version"):
                match = re.search(r'version\s*=\s*"([^"]+)"', stripped)
                if match:
                    return match.group(1)

    return "0.0.0"
