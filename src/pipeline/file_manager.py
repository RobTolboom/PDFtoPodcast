# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
File management for pipeline intermediate and final outputs.

This module provides the PipelineFileManager class for consistent
filename-based file naming and storage throughout the extraction pipeline.
"""

import json
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


class PipelineFileManager:
    """
    Manages filename-based file naming and storage for pipeline outputs.

    Uses PDF filename as the permanent identifier to create consistent naming:
    {pdf_filename}-{step}.json for all intermediate and final outputs.

    Attributes:
        pdf_path: Path to source PDF file
        pdf_stem: PDF filename without extension
        tmp_dir: Directory for temporary/intermediate files
        identifier: File identifier used in all output filenames

    Example:
        >>> from pathlib import Path
        >>> manager = PipelineFileManager(Path("research_paper.pdf"))
        >>> manager.identifier
        'research_paper'
        >>> filepath = manager.save_json({"type": "trial"}, "classification")
        >>> print(filepath)
        tmp/research_paper-classification.json
    """

    def __init__(self, pdf_path: Path):
        """
        Initialize file manager for a PDF.

        Args:
            pdf_path: Path to the PDF file being processed

        Note:
            Creates tmp/ directory if it doesn't exist.
            Prints the file identifier to console for tracking.
        """
        self.pdf_path = pdf_path
        self.pdf_stem = pdf_path.stem

        # Create tmp directory
        self.tmp_dir = Path("tmp")
        self.tmp_dir.mkdir(exist_ok=True)

        # Use PDF filename as permanent identifier (no DOI renaming)
        # This creates consistent naming: {pdf_filename}-{step}.json
        self.identifier = pdf_path.stem
        console.print(f"[blue]📁 File identifier: {self.identifier}[/blue]")

    def get_filename(
        self, step: str, iteration_number: int | None = None, status: str = ""
    ) -> Path:
        """
        Generate consistent filenames for pipeline steps.

        Args:
            step: Pipeline step name (e.g., "classification", "extraction", "validation")
            iteration_number: Optional iteration number for validation-correction loop (0, 1, 2, ...)
            status: Optional status suffix for special cases (e.g., "failed")

        Returns:
            Path to file in tmp directory

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> manager.get_filename("classification")
            PosixPath('tmp/paper-classification.json')
            >>> manager.get_filename("extraction", iteration_number=0)
            PosixPath('tmp/paper-extraction0.json')
            >>> manager.get_filename("validation", iteration_number=2)
            PosixPath('tmp/paper-validation2.json')
            >>> manager.get_filename("extraction", status="failed")
            PosixPath('tmp/paper-extraction-failed.json')
        """
        # Build filename parts
        parts = [self.identifier, step]

        # Add iteration number if provided (extraction0, validation1, etc.)
        if iteration_number is not None:
            parts[-1] = f"{step}{iteration_number}"

        # Add status if provided (for failed cases)
        if status:
            parts.append(status)

        filename = "-".join(parts) + ".json"
        return self.tmp_dir / filename

    def save_json(
        self, data: dict[Any, Any], step: str, iteration_number: int | None = None, status: str = ""
    ) -> Path:
        """
        Save JSON data with consistent filename-based naming.

        Args:
            data: Dictionary to save as JSON
            step: Pipeline step name
            iteration_number: Optional iteration number for validation-correction loop
            status: Optional status suffix

        Returns:
            Path to saved JSON file

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> result = {"publication_type": "interventional_trial"}
            >>> filepath = manager.save_json(result, "classification")
            >>> filepath.exists()
            True
            >>> extraction = {"data": "test"}
            >>> filepath = manager.save_json(extraction, "extraction", iteration_number=0)
            >>> filepath.name
            'paper-extraction0.json'
        """
        filepath = self.get_filename(step, iteration_number, status)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath

    def load_json(
        self, step: str, iteration_number: int | None = None, status: str = ""
    ) -> dict[str, Any] | None:
        """
        Load JSON data from file if it exists.

        Args:
            step: Pipeline step name
            iteration_number: Optional iteration number for validation-correction loop
            status: Optional status suffix

        Returns:
            Dictionary with loaded data, or None if file doesn't exist

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> # Save data first
            >>> manager.save_json({"type": "trial"}, "classification")
            PosixPath('tmp/paper-classification.json')
            >>> # Load it back
            >>> result = manager.load_json("classification")
            >>> result["type"]
            'trial'
            >>> # Load iteration file
            >>> manager.save_json({"data": "v1"}, "extraction", iteration_number=1)
            PosixPath('tmp/paper-extraction1.json')
            >>> result = manager.load_json("extraction", iteration_number=1)
            >>> result["data"]
            'v1'
            >>> # Non-existent file returns None
            >>> manager.load_json("nonexistent")
            None
        """
        filepath = self.get_filename(step, iteration_number, status)
        if not filepath.exists():
            return None

        with open(filepath, encoding="utf-8") as f:
            return json.load(f)

    def save_appraisal_iteration(
        self,
        iteration: int,
        appraisal_result: dict[str, Any],
        validation_result: dict[str, Any] | None = None,
    ) -> tuple[Path, Path | None]:
        """
        Save appraisal iteration files (convenience wrapper).

        Saves both appraisal and validation JSON files for a given iteration
        with consistent naming.

        Args:
            iteration: Iteration number (0, 1, 2, ...)
            appraisal_result: Appraisal JSON output
            validation_result: Optional validation JSON output

        Returns:
            Tuple of (appraisal_path, validation_path)
            validation_path is None if validation_result not provided

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> appraisal = {"risk_of_bias": {"overall": "Low risk"}}
            >>> validation = {"quality_score": 0.92, "overall_status": "passed"}
            >>> appr_path, val_path = manager.save_appraisal_iteration(
            ...     iteration=0,
            ...     appraisal_result=appraisal,
            ...     validation_result=validation,
            ... )
            >>> appr_path.name
            'paper-appraisal0.json'
            >>> val_path.name
            'paper-appraisal_validation0.json'
        """
        appraisal_path = self.save_json(appraisal_result, "appraisal", iteration_number=iteration)

        validation_path = None
        if validation_result is not None:
            validation_path = self.save_json(
                validation_result, "appraisal_validation", iteration_number=iteration
            )

        return (appraisal_path, validation_path)

    def load_appraisal_iteration(
        self,
        iteration: int,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """
        Load appraisal iteration files.

        Args:
            iteration: Iteration number to load

        Returns:
            Tuple of (appraisal_dict, validation_dict)
            validation_dict may be None if file doesn't exist

        Raises:
            FileNotFoundError: If appraisal file doesn't exist

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> # Save first
            >>> appraisal = {"risk_of_bias": {"overall": "Low risk"}}
            >>> validation = {"quality_score": 0.92}
            >>> manager.save_appraisal_iteration(0, appraisal, validation)
            (PosixPath('tmp/paper-appraisal0.json'), PosixPath('tmp/paper-appraisal_validation0.json'))
            >>> # Load back
            >>> loaded_appr, loaded_val = manager.load_appraisal_iteration(0)
            >>> loaded_appr["risk_of_bias"]["overall"]
            'Low risk'
            >>> loaded_val["quality_score"]
            0.92
        """
        appraisal = self.load_json("appraisal", iteration_number=iteration)
        if appraisal is None:
            raise FileNotFoundError(
                f"Appraisal iteration {iteration} not found: "
                f"{self.get_filename('appraisal', iteration_number=iteration)}"
            )

        validation = self.load_json("appraisal_validation", iteration_number=iteration)
        return (appraisal, validation)

    def save_best_appraisal(
        self,
        appraisal_result: dict[str, Any],
        validation_result: dict[str, Any],
    ) -> tuple[Path, Path]:
        """
        Save best appraisal iteration.

        Args:
            appraisal_result: Best appraisal JSON
            validation_result: Corresponding validation JSON

        Returns:
            Tuple of (appraisal_path, validation_path)

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> best_appr = {"risk_of_bias": {"overall": "Low risk"}}
            >>> best_val = {"quality_score": 0.95}
            >>> appr_path, val_path = manager.save_best_appraisal(best_appr, best_val)
            >>> appr_path.name
            'paper-appraisal-best.json'
            >>> val_path.name
            'paper-appraisal_validation-best.json'
        """
        appraisal_path = self.save_json(appraisal_result, "appraisal", status="best")
        validation_path = self.save_json(validation_result, "appraisal_validation", status="best")
        return (appraisal_path, validation_path)

    def get_appraisal_iterations(self) -> list[dict[str, Any]]:
        """
        Get all appraisal iterations with metadata.

        Returns:
            List of dicts with:
                - iteration_num: int
                - appraisal_file: Path
                - validation_file: Path | None
                - appraisal_exists: bool
                - validation_exists: bool
                - created_time: datetime (from file mtime)

        Sorted by iteration number.

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> # Save 2 iterations
            >>> manager.save_appraisal_iteration(0, {"data": "v0"}, {"score": 0.8})
            (PosixPath('tmp/paper-appraisal0.json'), PosixPath('tmp/paper-appraisal_validation0.json'))
            >>> manager.save_appraisal_iteration(1, {"data": "v1"}, {"score": 0.9})
            (PosixPath('tmp/paper-appraisal1.json'), PosixPath('tmp/paper-appraisal_validation1.json'))
            >>> iterations = manager.get_appraisal_iterations()
            >>> len(iterations)
            2
            >>> iterations[0]["iteration_num"]
            0
            >>> iterations[1]["iteration_num"]
            1
            >>> iterations[0]["appraisal_exists"]
            True
            >>> iterations[0]["validation_exists"]
            True
        """
        import re
        from datetime import datetime

        # Find all appraisal iteration files
        pattern = f"{self.identifier}-appraisal[0-9]*.json"
        appraisal_files = sorted(self.tmp_dir.glob(pattern))

        iterations = []
        for appraisal_file in appraisal_files:
            # Extract iteration number from filename
            match = re.search(r"appraisal(\d+)\.json$", appraisal_file.name)
            if not match:
                continue

            iteration_num = int(match.group(1))

            # Check for validation file
            validation_file = self.get_filename(
                "appraisal_validation", iteration_number=iteration_num
            )

            iterations.append(
                {
                    "iteration_num": iteration_num,
                    "appraisal_file": appraisal_file,
                    "validation_file": validation_file if validation_file.exists() else None,
                    "appraisal_exists": appraisal_file.exists(),
                    "validation_exists": validation_file.exists(),
                    "created_time": datetime.fromtimestamp(appraisal_file.stat().st_mtime),
                }
            )

        return sorted(iterations, key=lambda x: x["iteration_num"])

    def save_report_iteration(
        self,
        iteration: int,
        report_result: dict[str, Any],
        validation_result: dict[str, Any] | None = None,
    ) -> tuple[Path, Path | None]:
        """
        Save report iteration files (convenience wrapper).

        Saves both report and validation JSON files for a given iteration
        with consistent naming.

        Args:
            iteration: Iteration number (0, 1, 2, ...)
            report_result: Report JSON output
            validation_result: Optional validation JSON output

        Returns:
            Tuple of (report_path, validation_path)
            validation_path is None if validation_result not provided

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> report = {"report_version": "v1.0", "study_type": "interventional"}
            >>> validation = {"quality_score": 0.92, "overall_status": "passed"}
            >>> rep_path, val_path = manager.save_report_iteration(
            ...     iteration=0,
            ...     report_result=report,
            ...     validation_result=validation,
            ... )
            >>> rep_path.name
            'paper-report0.json'
            >>> val_path.name
            'paper-report_validation0.json'
        """
        report_path = self.save_json(report_result, "report", iteration_number=iteration)

        validation_path = None
        if validation_result is not None:
            validation_path = self.save_json(
                validation_result, "report_validation", iteration_number=iteration
            )

        return (report_path, validation_path)

    def load_report_iteration(
        self,
        iteration: int,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """
        Load report iteration files.

        Args:
            iteration: Iteration number to load

        Returns:
            Tuple of (report_dict, validation_dict)
            validation_dict may be None if file doesn't exist

        Raises:
            FileNotFoundError: If report file doesn't exist

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> # Save first
            >>> report = {"report_version": "v1.0", "study_type": "interventional"}
            >>> validation = {"quality_score": 0.92}
            >>> manager.save_report_iteration(0, report, validation)
            (PosixPath('tmp/paper-report0.json'), PosixPath('tmp/paper-report_validation0.json'))
            >>> # Load back
            >>> loaded_rep, loaded_val = manager.load_report_iteration(0)
            >>> loaded_rep["report_version"]
            'v1.0'
            >>> loaded_val["quality_score"]
            0.92
        """
        report = self.load_json("report", iteration_number=iteration)
        if report is None:
            raise FileNotFoundError(
                f"Report iteration {iteration} not found: "
                f"{self.get_filename('report', iteration_number=iteration)}"
            )

        validation = self.load_json("report_validation", iteration_number=iteration)
        return (report, validation)

    def save_best_report(
        self,
        report_result: dict[str, Any],
        validation_result: dict[str, Any],
    ) -> tuple[Path, Path]:
        """
        Save best report iteration.

        Args:
            report_result: Best report JSON
            validation_result: Corresponding validation JSON

        Returns:
            Tuple of (report_path, validation_path)

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> best_rep = {"report_version": "v1.0", "study_type": "interventional"}
            >>> best_val = {"quality_score": 0.95}
            >>> rep_path, val_path = manager.save_best_report(best_rep, best_val)
            >>> rep_path.name
            'paper-report-best.json'
            >>> val_path.name
            'paper-report_validation-best.json'
        """
        report_path = self.save_json(report_result, "report", status="best")
        validation_path = self.save_json(validation_result, "report_validation", status="best")
        return (report_path, validation_path)

    def get_report_iterations(self) -> list[dict[str, Any]]:
        """
        Get all report iterations with metadata.

        Returns:
            List of dicts with:
                - iteration_num: int
                - report_file: Path
                - validation_file: Path | None
                - report_exists: bool
                - validation_exists: bool
                - created_time: datetime (from file mtime)

        Sorted by iteration number.

        Examples:
            >>> manager = PipelineFileManager(Path("paper.pdf"))
            >>> # Save 2 iterations
            >>> manager.save_report_iteration(0, {"data": "v0"}, {"score": 0.8})
            (PosixPath('tmp/paper-report0.json'), PosixPath('tmp/paper-report_validation0.json'))
            >>> manager.save_report_iteration(1, {"data": "v1"}, {"score": 0.9})
            (PosixPath('tmp/paper-report1.json'), PosixPath('tmp/paper-report_validation1.json'))
            >>> iterations = manager.get_report_iterations()
            >>> len(iterations)
            2
            >>> iterations[0]["iteration_num"]
            0
            >>> iterations[1]["iteration_num"]
            1
            >>> iterations[0]["report_exists"]
            True
            >>> iterations[0]["validation_exists"]
            True
        """
        import re
        from datetime import datetime

        # Find all report iteration files
        pattern = f"{self.identifier}-report[0-9]*.json"
        report_files = sorted(self.tmp_dir.glob(pattern))

        iterations = []
        for report_file in report_files:
            # Extract iteration number from filename
            match = re.search(r"report(\d+)\.json$", report_file.name)
            if not match:
                continue

            iteration_num = int(match.group(1))

            # Check for validation file
            validation_file = self.get_filename("report_validation", iteration_number=iteration_num)

            iterations.append(
                {
                    "iteration_num": iteration_num,
                    "report_file": report_file,
                    "validation_file": validation_file if validation_file.exists() else None,
                    "report_exists": report_file.exists(),
                    "validation_exists": validation_file.exists(),
                    "created_time": datetime.fromtimestamp(report_file.stat().st_mtime),
                }
            )

        return sorted(iterations, key=lambda x: x["iteration_num"])
