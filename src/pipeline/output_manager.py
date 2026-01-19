# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Centralized output management for consistent CLI experience.

This module provides the PipelineOutputManager class that handles all console
output for the pipeline, ensuring consistent formatting, proper verbosity levels,
and professional appearance.

Output Levels:
    QUIET (0): Errors only - for CI/scripting
    NORMAL (1): Progress and key results - default
    VERBOSE (2): All details for debugging

Example:
    >>> from src.pipeline.output_manager import PipelineOutputManager, OutputLevel
    >>> output = PipelineOutputManager(level=OutputLevel.NORMAL)
    >>> output.info("Processing PDF...")
    >>> output.success("Classification complete")
    >>> output.detail("Token usage: 1500")  # Only shown in VERBOSE mode
"""

from enum import Enum

from rich.console import Console


class OutputLevel(Enum):
    """Output verbosity levels for CLI."""

    QUIET = 0  # Errors only
    NORMAL = 1  # Progress, key results (default)
    VERBOSE = 2  # All details for debugging


class PipelineOutputManager:
    """
    Centralized output management for consistent CLI experience.

    This class provides a single point of control for all console output,
    ensuring consistent formatting and proper verbosity filtering.

    Attributes:
        console: Rich Console instance for output
        level: Current output verbosity level

    Example:
        >>> output = PipelineOutputManager(level=OutputLevel.NORMAL)
        >>> output.info("Starting pipeline...")
        >>> output.success("Step completed")
        >>> output.warning("Low quality score")
        >>> output.error("Validation failed")
    """

    _instance: "PipelineOutputManager | None" = None

    def __init__(
        self,
        console: Console | None = None,
        level: OutputLevel = OutputLevel.NORMAL,
    ):
        """
        Initialize the output manager.

        Args:
            console: Rich Console instance (creates new one if None)
            level: Output verbosity level (default: NORMAL)
        """
        self.console = console or Console()
        self.level = level

    @classmethod
    def get_instance(
        cls,
        console: Console | None = None,
        level: OutputLevel = OutputLevel.NORMAL,
    ) -> "PipelineOutputManager":
        """
        Get or create singleton instance.

        Args:
            console: Rich Console instance (only used on first call)
            level: Output verbosity level (only used on first call)

        Returns:
            Singleton PipelineOutputManager instance
        """
        if cls._instance is None:
            cls._instance = cls(console=console, level=level)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None

    def info(self, message: str, level: OutputLevel = OutputLevel.NORMAL) -> None:
        """
        Print info message if verbosity level permits.

        Args:
            message: Message to print
            level: Minimum level required to show this message
        """
        if self.level.value >= level.value:
            self.console.print(message)

    def success(self, message: str) -> None:
        """
        Print success message with green color.

        Args:
            message: Success message to print
        """
        if self.level.value >= OutputLevel.NORMAL.value:
            self.console.print(f"[green]{message}[/green]")

    def warning(self, message: str) -> None:
        """
        Print warning message with yellow color.

        Args:
            message: Warning message to print
        """
        if self.level.value >= OutputLevel.NORMAL.value:
            self.console.print(f"[yellow]{message}[/yellow]")

    def error(self, message: str) -> None:
        """
        Print error message with red color (always shown).

        Args:
            message: Error message to print
        """
        # Errors are always shown, regardless of level
        self.console.print(f"[red]{message}[/red]")

    def detail(self, message: str) -> None:
        """
        Print detail message (only in VERBOSE mode).

        Args:
            message: Detail message to print
        """
        if self.level == OutputLevel.VERBOSE:
            self.console.print(f"[dim]{message}[/dim]")

    def step_header(self, step_num: int, name: str) -> None:
        """
        Print step header with consistent formatting.

        Args:
            step_num: Step number (1-6)
            name: Step name
        """
        if self.level.value >= OutputLevel.NORMAL.value:
            self.console.print(
                f"\n[bold magenta]═══ STEP {step_num}: {name.upper()} ═══[/bold magenta]\n"
            )

    def iteration_summary(
        self,
        iteration: int,
        quality_score: float,
        schema_score: float,
        completeness_score: float,
        status: str = "",
    ) -> None:
        """
        Print compact iteration summary on single line.

        Args:
            iteration: Iteration number
            quality_score: Overall quality score (0.0-1.0)
            schema_score: Schema compliance score (0.0-1.0)
            completeness_score: Completeness score (0.0-1.0)
            status: Optional status string
        """
        if self.level.value >= OutputLevel.NORMAL.value:
            status_str = f" | {status}" if status else ""
            self.console.print(
                f"[cyan]Iteration {iteration}:[/cyan] "
                f"Quality {quality_score:.1%} | "
                f"Schema {schema_score:.1%} | "
                f"Complete {completeness_score:.1%}{status_str}"
            )
