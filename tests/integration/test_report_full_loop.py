# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Integration tests for the complete report generation loop with validation and correction.

Tests the full Phase 3 workflow:
    1. Report generation (from extraction + appraisal)
    2. Report validation (quality scoring)
    3. Correction loop (if quality insufficient)
    4. Best iteration selection
    5. File management (save/load iterations)
    6. Early stopping on degradation
    7. Dependency gating (upstream quality checks)

Covers:
    - Pass on first iteration
    - Improvement over iterations
    - Max iterations reached
    - Quality degradation detection
    - Dependency blocking/warnings
    - File persistence
"""

from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from src.pipeline.file_manager import PipelineFileManager
from src.pipeline.orchestrator import run_report_with_correction


@pytest.fixture
def temp_dir(tmp_path):
    """Create temporary directory for test files."""
    return tmp_path


@pytest.fixture
def file_manager(temp_dir):
    """Create file manager for tests."""
    # Create a mock PDF path in temp directory
    pdf_path = temp_dir / "test-paper.pdf"
    pdf_path.touch()  # Create empty file

    # Create PipelineFileManager with the PDF path
    fm = PipelineFileManager(pdf_path)
    # Override tmp_dir to use the test temp directory
    fm.tmp_dir = temp_dir
    return fm


@pytest.fixture
def mock_extraction_interventional():
    """Mock extraction result for interventional trial."""
    return {
        "extraction_version": "v1.0",
        "study_id": "NCT12345678",
        "publication_type": "interventional_trial",
        "quality_score": 0.92,  # Good quality
        "study_design": {
            "design_type": "parallel-RCT",
            "randomization": {
                "method": "computer-generated sequence",
                "allocation_concealment": "central randomization",
            },
        },
        "outcomes": [
            {
                "outcome_id": "outcome1",
                "is_primary": True,
                "name": "Pain reduction at 24h",
                "measure_type": "continuous",
                "results": {
                    "intervention_mean": 3.2,
                    "control_mean": 5.1,
                    "effect_size": -1.9,
                    "ci_lower": -2.5,
                    "ci_upper": -1.3,
                    "p_value": 0.001,
                },
            }
        ],
    }


@pytest.fixture
def mock_appraisal_interventional():
    """Mock appraisal result for interventional trial."""
    return {
        "appraisal_version": "v1.0",
        "study_id": "NCT12345678",
        "study_type": "interventional",
        "quality_score": 0.88,  # Good quality
        "tool": {
            "name": "RoB 2",
            "version": "2019-08-22",
            "variant": "parallel-RCT",
            "judgement_scale": "rob2",
        },
        "risk_of_bias": {
            "overall": "Some concerns",
            "domains": [
                {
                    "domain": "randomization_process",
                    "judgement": "Low risk",
                    "rationale": "Computer-generated sequence with central randomization",
                    "source_refs": [{"page": 3}],
                },
                {
                    "domain": "deviations_from_intended",
                    "judgement": "Low risk",
                    "rationale": "Double-blind trial with adherence monitoring",
                    "source_refs": [{"page": 4}],
                },
            ],
        },
        "grade_certainty": {
            "outcome_assessments": [
                {
                    "outcome_id": "outcome1",
                    "overall_certainty": "Moderate",
                    "domains": {
                        "risk_of_bias": {"rating": "not serious"},
                        "inconsistency": {"rating": "not serious"},
                        "indirectness": {"rating": "not serious"},
                        "imprecision": {"rating": "serious"},
                        "publication_bias": {"rating": "undetected"},
                    },
                }
            ]
        },
    }


@pytest.fixture
def mock_classification_interventional():
    """Mock classification result for interventional trial."""
    return {
        "publication_type": "interventional_trial",
        "confidence": 0.95,
        "metadata": {
            "title": "Effect of Treatment X on Pain in RCT",
            "authors": ["Smith J", "Doe A"],
            "journal": "JAMA",
            "year": 2024,
        },
    }


@pytest.fixture
def mock_report_response():
    """Mock successful report generation response."""
    return {
        "report_version": "v1.0",
        "study_type": "interventional",
        "metadata": {
            "title": "Effect of Treatment X on Pain in RCT",
            "generation_timestamp": "2025-01-20T10:00:00Z",
            "pipeline_version": "1.0.0",
        },
        "layout": {
            "language": "nl",
        },
        "sections": [
            {
                "id": "summary",
                "title": "Samenvatting",
                "blocks": [
                    {
                        "type": "text",
                        "style": "paragraph",
                        "content": [
                            "Parallelle RCT met Treatment X vs placebo voor adults with chronic pain."
                        ],
                    }
                ],
            },
            {
                "id": "rob",
                "title": "Risk of Bias",
                "blocks": [
                    {
                        "type": "text",
                        "style": "paragraph",
                        "content": [
                            "Overall: Some concerns. Low risk in randomization and blinding."
                        ],
                    }
                ],
            },
        ],
    }


@pytest.fixture
def mock_validation_passed():
    """Mock validation report with passing quality."""
    return {
        "validation_version": "v1.0",
        "validation_summary": {
            "overall_status": "passed",
            "completeness_score": 0.92,
            "accuracy_score": 0.96,
            "cross_reference_consistency_score": 0.94,
            "data_consistency_score": 0.93,
            "schema_compliance_score": 0.98,
            "critical_issues": 0,
            "quality_score": 0.95,
        },
        "issues": [],
    }


@pytest.fixture
def mock_validation_failed():
    """Mock validation report with failing quality."""
    return {
        "validation_version": "v1.0",
        "validation_summary": {
            "overall_status": "failed",
            "completeness_score": 0.70,  # Below threshold
            "accuracy_score": 0.88,  # Below threshold
            "cross_reference_consistency_score": 0.82,
            "data_consistency_score": 0.80,
            "schema_compliance_score": 0.90,
            "critical_issues": 2,
            "quality_score": 0.82,
        },
        "issues": [
            {
                "severity": "critical",
                "category": "completeness",
                "field_path": "sections.grade",
                "description": "GRADE assessment missing for primary outcome",
                "recommendation": "Add GRADE certainty rating for outcome 'outcome1'",
            },
            {
                "severity": "critical",
                "category": "accuracy",
                "field_path": "sections.results.outcome1.effect_size",
                "description": "Effect size mismatch: report shows -1.5 but extraction has -1.9",
                "recommendation": "Correct effect size to match extraction data (-1.9)",
            },
        ],
    }


@pytest.fixture
def mock_validation_improved():
    """Mock validation report with improved quality after correction."""
    return {
        "validation_version": "v1.0",
        "validation_summary": {
            "overall_status": "passed",
            "completeness_score": 0.90,  # Improved
            "accuracy_score": 0.96,  # Improved
            "cross_reference_consistency_score": 0.92,
            "data_consistency_score": 0.91,
            "schema_compliance_score": 0.96,
            "critical_issues": 0,  # Fixed
            "quality_score": 0.93,
        },
        "issues": [],
    }


@pytest.fixture
def mock_corrected_report(mock_report_response):
    """Mock corrected report with improvements."""
    corrected = deepcopy(mock_report_response)
    # Add missing GRADE section
    corrected["sections"].append(
        {
            "id": "grade",
            "title": "GRADE Certainty",
            "blocks": [
                {
                    "type": "text",
                    "style": "paragraph",
                    "content": [
                        "Outcome 'Pain reduction at 24h': Moderate certainty (downgraded for imprecision)."
                    ],
                }
            ],
        }
    )
    return corrected


@pytest.mark.integration
class TestReportFullLoop:
    """Integration tests for complete report generation workflow."""

    def test_report_passes_first_iteration(
        self,
        mock_extraction_interventional,
        mock_appraisal_interventional,
        mock_classification_interventional,
        file_manager,
        mock_report_response,
        mock_validation_passed,
    ):
        """Test report that passes quality check on first iteration."""
        with patch("src.pipeline.orchestrator.get_llm_provider") as mock_get_provider:
            # Setup mock LLM
            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_report_response,  # Initial report generation
                mock_validation_passed,  # Validation call
            ]
            mock_get_provider.return_value = mock_llm

            # Run report generation with correction
            result = run_report_with_correction(
                extraction_result=mock_extraction_interventional,
                appraisal_result=mock_appraisal_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
                max_iterations=3,
            )

            # Assertions
            assert result["final_status"] == "passed"
            assert result["iteration_count"] == 1
            assert result["best_report"]["report_version"] == "v1.0"
            assert len(result["iterations"]) == 1
            assert result["improvement_trajectory"][0] == 0.95
            # LaTeX artefact should be rendered (compile_pdf=False)
            rendered_tex = file_manager.tmp_dir / "render" / "report.tex"
            assert rendered_tex.exists()

            # Verify files created
            assert (file_manager.tmp_dir / "test-paper-report0.json").exists()
            assert (file_manager.tmp_dir / "test-paper-report_validation0.json").exists()
            assert (file_manager.tmp_dir / "test-paper-report-best.json").exists()

    def test_report_requires_correction(
        self,
        mock_extraction_interventional,
        mock_appraisal_interventional,
        mock_classification_interventional,
        file_manager,
        mock_report_response,
        mock_validation_failed,
        mock_corrected_report,
        mock_validation_improved,
    ):
        """Test report that requires correction to meet quality thresholds."""
        with patch("src.pipeline.orchestrator.get_llm_provider") as mock_get_provider:
            # Setup mock LLM
            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_report_response,  # Iteration 0: initial report
                mock_validation_failed,  # Iteration 0: validation (fails)
                mock_corrected_report,  # Iteration 1: correction
                mock_validation_improved,  # Iteration 1: validation (passes)
            ]
            mock_get_provider.return_value = mock_llm

            # Run report generation with correction
            result = run_report_with_correction(
                extraction_result=mock_extraction_interventional,
                appraisal_result=mock_appraisal_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
                max_iterations=3,
            )

            # Assertions
            assert result["final_status"] == "passed"
            assert result["iteration_count"] == 2
            assert len(result["iterations"]) == 2
            assert result["improvement_trajectory"] == [0.82, 0.93]
            assert result["improvement_trajectory"][-1] > result["improvement_trajectory"][0]

            # Verify best iteration selected
            assert result["best_iteration"] == 1
            assert result["best_report"]["sections"][-1]["id"] == "grade"

            # Verify files created for both iterations
            assert (file_manager.tmp_dir / "test-paper-report0.json").exists()
            assert (file_manager.tmp_dir / "test-paper-report1.json").exists()
            assert (file_manager.tmp_dir / "test-paper-report-best.json").exists()

    def test_max_iterations_reached(
        self,
        mock_extraction_interventional,
        mock_appraisal_interventional,
        mock_classification_interventional,
        file_manager,
        mock_report_response,
        mock_validation_failed,
        mock_corrected_report,
    ):
        """Test that loop stops at max_iterations even if quality not met."""
        with patch("src.pipeline.orchestrator.get_llm_provider") as mock_get_provider:
            # Setup mock LLM - all validations fail
            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_report_response,  # Iter 0: report
                mock_validation_failed,  # Iter 0: validation
                mock_corrected_report,  # Iter 1: correction
                mock_validation_failed,  # Iter 1: validation
                mock_corrected_report,  # Iter 2: correction
                mock_validation_failed,  # Iter 2: validation
                mock_corrected_report,  # Iter 3: correction
                mock_validation_failed,  # Iter 3: validation
            ]
            mock_get_provider.return_value = mock_llm

            # Run with max_iterations=3
            result = run_report_with_correction(
                extraction_result=mock_extraction_interventional,
                appraisal_result=mock_appraisal_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
                max_iterations=3,
            )

            # Assertions
            assert result["final_status"] == "max_iterations_reached"
            assert result["iteration_count"] == 4  # 0, 1, 2, 3
            assert len(result["iterations"]) == 4

            # Best iteration selected even though all failed
            assert "best_iteration" in result
            assert "best_report" in result

    def test_early_stopping_on_degradation(
        self,
        mock_extraction_interventional,
        mock_appraisal_interventional,
        mock_classification_interventional,
        file_manager,
        mock_report_response,
        mock_validation_passed,
        mock_corrected_report,
    ):
        """Test early stopping when quality degrades."""
        with patch("src.pipeline.orchestrator.get_llm_provider") as mock_get_provider:
            # Setup mock LLM
            validation_degraded = {
                "validation_version": "v1.0",
                "validation_summary": {
                    "overall_status": "failed",
                    "completeness_score": 0.70,
                    "accuracy_score": 0.75,
                    "cross_reference_consistency_score": 0.72,
                    "data_consistency_score": 0.70,
                    "schema_compliance_score": 0.80,
                    "critical_issues": 3,
                    "quality_score": 0.73,  # Worse than 0.95
                },
                "issues": [],
            }

            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_report_response,  # Iter 0: report
                mock_validation_passed,  # Iter 0: quality 0.95 (good)
                mock_corrected_report,  # Iter 1: correction
                validation_degraded,  # Iter 1: quality 0.73 (degraded!)
            ]
            mock_get_provider.return_value = mock_llm

            # Run report generation
            result = run_report_with_correction(
                extraction_result=mock_extraction_interventional,
                appraisal_result=mock_appraisal_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
                max_iterations=3,
            )

            # Should have stopped after iteration 1 due to degradation
            # But iteration 0 passes quality, so final_status should be "passed"
            assert result["final_status"] == "passed"
            assert result["best_iteration"] == 0  # Best is iteration 0
            assert result["improvement_trajectory"] == [0.95]  # Stopped after first iteration

    def test_dependency_gating_blocks_low_extraction_quality(
        self,
        mock_extraction_interventional,
        mock_appraisal_interventional,
        mock_classification_interventional,
        file_manager,
    ):
        """Test that low extraction quality blocks report generation."""
        # Set extraction quality below 0.70 threshold
        low_quality_extraction = deepcopy(mock_extraction_interventional)
        low_quality_extraction["quality_score"] = 0.65

        with patch("src.pipeline.orchestrator.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            mock_get_provider.return_value = mock_llm

            # Run report generation
            result = run_report_with_correction(
                extraction_result=low_quality_extraction,
                appraisal_result=mock_appraisal_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
                max_iterations=3,
            )

            # Should be blocked
            assert result["status"] == "blocked"
            assert "extraction quality" in result["message"].lower()
            assert result["extraction_quality"] == 0.65
            assert result["minimum_required"] == 0.70

    def test_dependency_gating_blocks_failed_appraisal(
        self,
        mock_extraction_interventional,
        mock_appraisal_interventional,
        mock_classification_interventional,
        file_manager,
    ):
        """Test that failed appraisal (final_status) blocks report generation."""
        bad_appraisal = deepcopy(mock_appraisal_interventional)
        bad_appraisal["final_status"] = "failed_schema_validation"
        bad_appraisal["risk_of_bias"] = None

        with patch("src.pipeline.orchestrator.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            mock_get_provider.return_value = mock_llm

            result = run_report_with_correction(
                extraction_result=mock_extraction_interventional,
                appraisal_result=bad_appraisal,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
                max_iterations=3,
            )

            assert result["status"] == "blocked"
            assert result["appraisal_final_status"] == "failed_schema_validation"
            assert result["has_risk_of_bias"] is False

    def test_dependency_gating_blocks_failed_appraisal_validation(
        self,
        mock_extraction_interventional,
        mock_appraisal_interventional,
        mock_classification_interventional,
        file_manager,
    ):
        """Test that failed appraisal validation blocks report generation even with RoB present."""
        bad_appraisal = deepcopy(mock_appraisal_interventional)
        bad_appraisal["risk_of_bias"] = {"overall": "High risk"}  # present
        bad_appraisal["best_validation"] = {"validation_summary": {"overall_status": "failed"}}

        with patch("src.pipeline.orchestrator.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            mock_get_provider.return_value = mock_llm

            result = run_report_with_correction(
                extraction_result=mock_extraction_interventional,
                appraisal_result=bad_appraisal,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
                max_iterations=3,
            )

            assert result["status"] == "blocked"
            assert result["appraisal_validation_status"] == "failed"
            assert result["has_risk_of_bias"] is True

            # LLM should not have been called
            mock_llm.generate_json_with_schema.assert_not_called()

    def test_dependency_gating_blocks_missing_appraisal_data(
        self,
        mock_extraction_interventional,
        mock_classification_interventional,
        file_manager,
    ):
        """Test that missing appraisal RoB data blocks report generation."""
        # Appraisal without risk_of_bias
        incomplete_appraisal = {
            "appraisal_version": "v1.0",
            "study_id": "NCT12345678",
            "status": "completed",
            # Missing: risk_of_bias
        }

        with patch("src.pipeline.orchestrator.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            mock_get_provider.return_value = mock_llm

            # Run report generation
            result = run_report_with_correction(
                extraction_result=mock_extraction_interventional,
                appraisal_result=incomplete_appraisal,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
                max_iterations=3,
            )

            # Should be blocked
            assert result["status"] == "blocked"
            assert "appraisal" in result["message"].lower()
            assert result["has_risk_of_bias"] is False

            # LLM should not have been called
            mock_llm.generate_json_with_schema.assert_not_called()

    def test_custom_quality_thresholds(
        self,
        mock_extraction_interventional,
        mock_appraisal_interventional,
        mock_classification_interventional,
        file_manager,
        mock_report_response,
    ):
        """Test using custom quality thresholds."""
        with patch("src.pipeline.orchestrator.get_llm_provider") as mock_get_provider:
            # Validation with quality that would fail default but passes custom
            custom_validation = {
                "validation_version": "v1.0",
                "validation_summary": {
                    "overall_status": "passed",
                    "completeness_score": 0.80,  # Default threshold is 0.85
                    "accuracy_score": 0.92,  # Default threshold is 0.95
                    "cross_reference_consistency_score": 0.88,
                    "data_consistency_score": 0.87,
                    "schema_compliance_score": 0.93,
                    "critical_issues": 0,
                    "quality_score": 0.88,
                },
                "issues": [],
            }

            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_report_response,
                custom_validation,
            ]
            mock_get_provider.return_value = mock_llm

            # Custom thresholds (more lenient)
            custom_thresholds = {
                "completeness_score": 0.75,
                "accuracy_score": 0.90,
                "cross_reference_consistency_score": 0.85,
                "data_consistency_score": 0.85,
                "schema_compliance_score": 0.90,
                "critical_issues": 0,
            }

            # Run with custom thresholds
            result = run_report_with_correction(
                extraction_result=mock_extraction_interventional,
                appraisal_result=mock_appraisal_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
                max_iterations=3,
                quality_thresholds=custom_thresholds,
            )

            # Should pass with custom thresholds
            assert result["final_status"] == "passed"
            assert result["iteration_count"] == 1

    def test_file_persistence_across_iterations(
        self,
        mock_extraction_interventional,
        mock_appraisal_interventional,
        mock_classification_interventional,
        file_manager,
        mock_report_response,
        mock_validation_failed,
        mock_corrected_report,
        mock_validation_improved,
    ):
        """Test that all iteration files are persisted correctly."""
        with patch("src.pipeline.orchestrator.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_report_response,  # Iter 0
                mock_validation_failed,
                mock_corrected_report,  # Iter 1
                mock_validation_improved,
            ]
            mock_get_provider.return_value = mock_llm

            # Run report generation
            result = run_report_with_correction(
                extraction_result=mock_extraction_interventional,
                appraisal_result=mock_appraisal_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                language="en",
                max_iterations=3,
            )

            # Verify all iteration files exist
            for i in range(result["iteration_count"]):
                report_file = file_manager.tmp_dir / f"test-paper-report{i}.json"
                validation_file = file_manager.tmp_dir / f"test-paper-report_validation{i}.json"
                assert report_file.exists(), f"Missing report file for iteration {i}"
                assert validation_file.exists(), f"Missing validation file for iteration {i}"

            # Verify best report file exists
            best_file = file_manager.tmp_dir / "test-paper-report-best.json"
            assert best_file.exists()

            # Verify best file content matches best iteration
            import json

            with open(best_file) as f:
                best_content = json.load(f)
            assert best_content == result["best_report"]
