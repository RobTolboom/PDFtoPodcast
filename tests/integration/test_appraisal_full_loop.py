"""
Integration tests for the complete appraisal loop with validation and correction.

Tests the full workflow:
    1. Appraisal execution (route to correct prompt by study type)
    2. Appraisal validation (quality scoring)
    3. Correction loop (if quality insufficient)
    4. Best iteration selection
    5. File management (save/load iterations)

Covers all 5 study types:
    - interventional_trial (RoB 2)
    - observational_analytic (ROBINS-I)
    - evidence_synthesis (AMSTAR 2 + ROBIS)
    - prediction_prognosis (PROBAST)
    - editorials_opinion (Argument quality)
"""

from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from src.pipeline.file_manager import PipelineFileManager
from src.pipeline.orchestrator import run_appraisal_with_correction


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
        "study_id": "NCT12345678",
        "publication_type": "interventional_trial",
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
                "name": "Pain at 24 hours",
                "results": {"effect_size": 0.5, "ci_lower": 0.2, "ci_upper": 0.8},
            }
        ],
    }


@pytest.fixture
def mock_classification_interventional():
    """Mock classification result for interventional trial."""
    return {"publication_type": "interventional_trial", "confidence": 0.95}


@pytest.fixture
def mock_appraisal_response():
    """Mock successful appraisal response."""
    return {
        "appraisal_version": "v1.0",
        "study_id": "NCT12345678",
        "study_type": "interventional",
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
                    "rationale": "Computer-generated sequence with central randomization provides adequate allocation concealment",
                    "source_refs": [{"page": 3}],
                },
                {
                    "domain": "deviations_from_intended_interventions",
                    "judgement": "Low risk",
                    "rationale": "No deviations reported and double-blind design maintained",
                    "source_refs": [{"page": 4}],
                },
                {
                    "domain": "missing_outcome_data",
                    "judgement": "Some concerns",
                    "rationale": "15% loss to follow-up with no sensitivity analysis",
                    "source_refs": [{"page": 5}],
                },
                {
                    "domain": "measurement_of_outcome",
                    "judgement": "Low risk",
                    "rationale": "Validated pain scale used with blinded outcome assessors",
                    "source_refs": [{"page": 4}],
                },
                {
                    "domain": "selection_of_reported_result",
                    "judgement": "Low risk",
                    "rationale": "Pre-registered outcomes reported as specified",
                    "source_refs": [{"page": 2}],
                },
            ],
        },
        "grade_per_outcome": [
            {
                "outcome_id": "outcome1",
                "certainty": "Moderate",
                "downgrades": [
                    {
                        "factor": "imprecision",
                        "levels": -1,
                        "rationale": "Confidence interval crosses null",
                    }
                ],
            }
        ],
        "bottom_line": {
            "short": "RCT with some concerns about missing data",
            "for_podcast": "This randomized trial had generally low risk of bias but some concerns about participant dropout",
        },
    }


@pytest.fixture
def mock_validation_passed():
    """Mock validation report with passing quality."""
    return {
        "validation_version": "v1.0",
        "schema_validation": {"quality_score": 1.0},
        "validation_summary": {
            "overall_status": "passed",
            "logical_consistency_score": 0.95,
            "completeness_score": 0.92,
            "evidence_support_score": 0.90,
            "schema_compliance_score": 1.0,
            "critical_issues": 0,
            "quality_score": 0.94,
        },
        "issues": [],
    }


@pytest.fixture
def mock_validation_failed():
    """Mock validation report with failing quality."""
    return {
        "validation_version": "v1.0",
        "schema_validation": {"quality_score": 0.80},
        "validation_summary": {
            "overall_status": "failed",
            "logical_consistency_score": 0.70,
            "completeness_score": 0.65,
            "evidence_support_score": 0.60,
            "schema_compliance_score": 0.80,
            "critical_issues": 2,
            "quality_score": 0.69,
        },
        "issues": [
            {
                "severity": "critical",
                "category": "logical_inconsistency",
                "field_path": "risk_of_bias.overall",
                "description": "Overall judgement 'Low risk' contradicts domain 'missing_outcome_data: Some concerns'",
                "recommendation": "Set overall to 'Some concerns' per RoB 2 worst-domain rule",
            }
        ],
    }


@pytest.fixture
def mock_corrected_appraisal(mock_appraisal_response):
    """Mock corrected appraisal with improved quality."""
    corrected = mock_appraisal_response.copy()
    # Add more detailed rationales
    for domain in corrected["risk_of_bias"]["domains"]:
        domain["rationale"] = (
            domain["rationale"] + " [Corrected with additional evidence from extraction data]"
        )
    return corrected


@pytest.mark.integration
class TestAppraisalFullLoop:
    """Integration tests for complete appraisal workflow."""

    def test_appraisal_passes_first_iteration(
        self,
        mock_extraction_interventional,
        mock_classification_interventional,
        file_manager,
        mock_appraisal_response,
        mock_validation_passed,
    ):
        """Test appraisal that passes quality check on first iteration."""
        with patch("src.pipeline.steps.appraisal.get_llm_provider") as mock_get_provider:
            # Setup mock LLM
            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_appraisal_response,  # Appraisal call
                mock_validation_passed,  # Validation call
            ]
            mock_get_provider.return_value = mock_llm

            # Run appraisal
            result = run_appraisal_with_correction(
                extraction_result=mock_extraction_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=3,
            )

            # Assertions
            assert result["final_status"] == "passed"
            assert result["iteration_count"] == 1
            assert result["best_appraisal"]["risk_of_bias"]["overall"] == "Some concerns"
            assert len(result["iterations"]) == 1
            assert result["improvement_trajectory"][0] == 0.94

            # Verify files created
            assert (file_manager.tmp_dir / "test-paper-appraisal0.json").exists()
            assert (file_manager.tmp_dir / "test-paper-appraisal_validation0.json").exists()
            assert (file_manager.tmp_dir / "test-paper-appraisal-best.json").exists()

    def test_appraisal_requires_correction(
        self,
        mock_extraction_interventional,
        mock_classification_interventional,
        file_manager,
        mock_appraisal_response,
        mock_validation_failed,
        mock_validation_passed,
        mock_corrected_appraisal,
    ):
        """Test appraisal that requires correction iteration."""
        with patch("src.pipeline.steps.appraisal.get_llm_provider") as mock_get_provider:
            # Setup mock LLM
            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_appraisal_response,  # Initial appraisal
                mock_validation_failed,  # Initial validation (fails)
                mock_corrected_appraisal,  # Correction
                mock_validation_passed,  # Re-validation (passes)
            ]
            mock_get_provider.return_value = mock_llm

            # Run appraisal
            result = run_appraisal_with_correction(
                extraction_result=mock_extraction_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=3,
            )

            # Assertions
            assert result["final_status"] == "passed"
            assert result["iteration_count"] == 2
            assert len(result["iterations"]) == 2
            assert result["improvement_trajectory"][0] == 0.69  # Failed first
            assert result["improvement_trajectory"][1] == 0.94  # Passed second

            # Verify iteration files
            assert (file_manager.tmp_dir / "test-paper-appraisal0.json").exists()
            assert (file_manager.tmp_dir / "test-paper-appraisal1.json").exists()
            assert (file_manager.tmp_dir / "test-paper-appraisal-best.json").exists()

    def test_appraisal_max_iterations_reached(
        self,
        mock_extraction_interventional,
        mock_classification_interventional,
        file_manager,
        mock_appraisal_response,
        mock_validation_failed,
    ):
        """Test appraisal that reaches max iterations without passing."""
        with patch("src.pipeline.steps.appraisal.get_llm_provider") as mock_get_provider:
            # Setup mock LLM - all iterations fail
            mock_llm = Mock()

            # Create progressively improving quality scores
            validation_iter0 = deepcopy(mock_validation_failed)
            validation_iter0["validation_summary"]["quality_score"] = 0.60

            validation_iter1 = deepcopy(mock_validation_failed)
            validation_iter1["validation_summary"]["quality_score"] = 0.70

            validation_iter2 = deepcopy(mock_validation_failed)
            validation_iter2["validation_summary"]["quality_score"] = 0.75

            mock_llm.generate_json_with_schema.side_effect = [
                mock_appraisal_response,  # iter 0 appraisal
                validation_iter0,  # iter 0 validation (fail)
                mock_appraisal_response,  # iter 1 correction
                validation_iter1,  # iter 1 validation (fail)
                mock_appraisal_response,  # iter 2 correction
                validation_iter2,  # iter 2 validation (fail)
            ]
            mock_get_provider.return_value = mock_llm

            # Run appraisal with max_iterations=2
            result = run_appraisal_with_correction(
                extraction_result=mock_extraction_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=2,
            )

            # Assertions
            assert result["final_status"] == "max_iterations_reached"
            assert result["iteration_count"] == 3  # iter 0, 1, 2
            assert len(result["iterations"]) == 3
            # Best should be iteration 2 (highest quality score 0.75)
            assert result["best_iteration"] == 2
            assert result["improvement_trajectory"] == [0.60, 0.70, 0.75]

    def test_appraisal_routing_observational(self, mock_extraction_interventional, file_manager):
        """Test correct routing for observational study."""
        classification = {"publication_type": "observational_analytic"}

        mock_appraisal = {
            "appraisal_version": "v1.0",
            "study_id": "test",
            "study_type": "observational",
            "tool": {"name": "ROBINS-I", "version": "2016", "judgement_scale": "robins"},
            "risk_of_bias": {"overall": "Moderate risk", "domains": []},
        }

        mock_validation = {
            "validation_version": "v1.0",
            "validation_summary": {
                "overall_status": "passed",
                "logical_consistency_score": 0.90,
                "completeness_score": 0.90,
                "evidence_support_score": 0.90,
                "schema_compliance_score": 0.95,
                "critical_issues": 0,
                "quality_score": 0.91,
            },
            "issues": [],
        }

        with patch("src.pipeline.steps.appraisal.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_appraisal,
                mock_validation,
            ]
            mock_get_provider.return_value = mock_llm

            with patch(
                "src.pipeline.orchestrator.load_appraisal_prompt"
            ) as mock_load_appraisal_prompt:
                mock_load_appraisal_prompt.return_value = "Test prompt"

                result = run_appraisal_with_correction(
                    extraction_result=mock_extraction_interventional,
                    classification_result=classification,
                    llm_provider="openai",
                    file_manager=file_manager,
                    max_iterations=3,
                )

                # Verify correct prompt loaded
                mock_load_appraisal_prompt.assert_called_with("observational_analytic")
                assert result["final_status"] == "passed"

    def test_appraisal_routing_evidence_synthesis(
        self, mock_extraction_interventional, file_manager
    ):
        """Test correct routing for evidence synthesis."""
        classification = {"publication_type": "evidence_synthesis"}

        mock_appraisal = {
            "appraisal_version": "v1.0",
            "study_id": "test",
            "study_type": "evidence_synthesis",
            "tool": {"name": "AMSTAR 2", "version": "2017", "judgement_scale": "amstar2"},
            "amstar2": {"overall_confidence": "Moderate", "critical_weaknesses": 1},
        }

        mock_validation = {
            "validation_version": "v1.0",
            "validation_summary": {
                "overall_status": "passed",
                "logical_consistency_score": 0.90,
                "completeness_score": 0.90,
                "evidence_support_score": 0.90,
                "schema_compliance_score": 0.95,
                "critical_issues": 0,
                "quality_score": 0.91,
            },
            "issues": [],
        }

        with patch("src.pipeline.steps.appraisal.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_appraisal,
                mock_validation,
            ]
            mock_get_provider.return_value = mock_llm

            with patch(
                "src.pipeline.orchestrator.load_appraisal_prompt"
            ) as mock_load_appraisal_prompt:
                mock_load_appraisal_prompt.return_value = "Test prompt"

                result = run_appraisal_with_correction(
                    extraction_result=mock_extraction_interventional,
                    classification_result=classification,
                    llm_provider="openai",
                    file_manager=file_manager,
                    max_iterations=3,
                )

                # Verify correct prompt loaded
                mock_load_appraisal_prompt.assert_called_with("evidence_synthesis")
                assert result["final_status"] == "passed"

    def test_file_management_iterations(
        self,
        mock_extraction_interventional,
        mock_classification_interventional,
        file_manager,
        mock_appraisal_response,
        mock_validation_failed,
        mock_validation_passed,
        mock_corrected_appraisal,
    ):
        """Test that all iteration files are correctly saved and can be loaded."""
        with patch("src.pipeline.steps.appraisal.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_appraisal_response,  # iter 0 appraisal
                mock_validation_failed,  # iter 0 validation (fail)
                mock_corrected_appraisal,  # iter 1 correction
                mock_validation_passed,  # iter 1 validation (pass)
            ]
            mock_get_provider.return_value = mock_llm

            # Run appraisal
            run_appraisal_with_correction(
                extraction_result=mock_extraction_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=3,
            )

            # Test file_manager methods
            iterations = file_manager.get_appraisal_iterations()
            assert len(iterations) == 2
            assert iterations[0]["iteration_num"] == 0
            assert iterations[1]["iteration_num"] == 1

            # Test load iteration
            loaded_appr, loaded_val = file_manager.load_appraisal_iteration(0)
            assert loaded_appr["study_id"] == "NCT12345678"
            assert loaded_val["validation_summary"]["overall_status"] == "failed"

            # Test best files exist
            best_appr_path = file_manager.tmp_dir / "test-paper-appraisal-best.json"
            best_val_path = file_manager.tmp_dir / "test-paper-appraisal_validation-best.json"
            assert best_appr_path.exists()
            assert best_val_path.exists()

    def test_custom_quality_thresholds(
        self,
        mock_extraction_interventional,
        mock_classification_interventional,
        file_manager,
        mock_appraisal_response,
    ):
        """Test appraisal with custom quality thresholds."""
        custom_thresholds = {
            "logical_consistency_score": 0.95,
            "completeness_score": 0.95,
            "evidence_support_score": 0.95,
            "schema_compliance_score": 0.98,
            "critical_issues": 0,
        }

        # Validation that would pass default thresholds but fails custom
        validation_marginal = {
            "validation_version": "v1.0",
            "validation_summary": {
                "overall_status": "warning",
                "logical_consistency_score": 0.92,  # Below custom 0.95
                "completeness_score": 0.93,  # Below custom 0.95
                "evidence_support_score": 0.91,  # Below custom 0.95
                "schema_compliance_score": 0.96,  # Below custom 0.98
                "critical_issues": 0,
                "quality_score": 0.93,
            },
            "issues": [],
        }

        with patch("src.pipeline.steps.appraisal.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            mock_llm.generate_json_with_schema.side_effect = [
                mock_appraisal_response,
                validation_marginal,
            ]
            mock_get_provider.return_value = mock_llm

            result = run_appraisal_with_correction(
                extraction_result=mock_extraction_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=0,  # No corrections, just check threshold
                quality_thresholds=custom_thresholds,
            )

            # Should fail with strict thresholds
            assert result["final_status"] == "max_iterations_reached"


@pytest.mark.integration
class TestAppraisalEdgeCases:
    """Test edge cases and error handling."""

    def test_unsupported_publication_type(self, mock_extraction_interventional, file_manager):
        """Test that unsupported publication type raises error."""
        classification = {"publication_type": "overig"}  # Not supported

        with patch("src.pipeline.steps.appraisal.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            mock_get_provider.return_value = mock_llm

            with pytest.raises(ValueError, match="not supported.*publication type"):
                run_appraisal_with_correction(
                    extraction_result=mock_extraction_interventional,
                    classification_result=classification,
                    llm_provider="openai",
                    file_manager=file_manager,
                    max_iterations=3,
                )

    def test_schema_validation_error_handling(
        self, mock_extraction_interventional, mock_classification_interventional, file_manager
    ):
        """Test handling of invalid/incomplete appraisal data."""
        # Invalid appraisal (missing required fields)
        invalid_appraisal = {
            "appraisal_version": "v1.0"
            # Missing study_id, study_type, etc.
        }

        # Validation result for invalid data (all zeros)
        invalid_validation = {
            "validation_version": "v1.0",
            "validation_summary": {
                "overall_status": "failed",
                "logical_consistency_score": 0.0,
                "completeness_score": 0.0,
                "evidence_support_score": 0.0,
                "schema_compliance_score": 0.0,
                "critical_issues": 5,
                "quality_score": 0.0,
            },
            "issues": [],
        }

        with patch("src.pipeline.steps.appraisal.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()
            # Appraisal + validation repeated for max iterations
            mock_llm.generate_json_with_schema.side_effect = [
                invalid_appraisal,  # iter 0 appraisal
                invalid_validation,  # iter 0 validation
            ] * 4  # Repeat for iterations 0-3
            mock_get_provider.return_value = mock_llm

            # Should handle gracefully and return max_iterations_reached
            result = run_appraisal_with_correction(
                extraction_result=mock_extraction_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=3,
            )

            # Verify it completed and selected best available
            assert result["final_status"] == "max_iterations_reached"
            assert result["improvement_trajectory"] == [0.0, 0.0, 0.0, 0.0]

    def test_quality_degradation_early_stop(
        self,
        mock_extraction_interventional,
        mock_classification_interventional,
        file_manager,
        mock_appraisal_response,
    ):
        """Test early stopping when quality degrades."""
        with patch("src.pipeline.steps.appraisal.get_llm_provider") as mock_get_provider:
            mock_llm = Mock()

            # Quality degrades over iterations
            validation1 = {
                "validation_version": "v1.0",
                "validation_summary": {
                    "overall_status": "warning",
                    "logical_consistency_score": 0.85,
                    "completeness_score": 0.85,
                    "evidence_support_score": 0.85,
                    "schema_compliance_score": 0.95,
                    "critical_issues": 0,
                    "quality_score": 0.87,
                },
                "issues": [],
            }

            validation2 = {
                "validation_version": "v1.0",
                "validation_summary": {
                    "overall_status": "failed",
                    "logical_consistency_score": 0.75,
                    "completeness_score": 0.75,
                    "evidence_support_score": 0.75,
                    "schema_compliance_score": 0.85,
                    "critical_issues": 0,
                    "quality_score": 0.77,
                },
                "issues": [],
            }

            validation3 = {
                "validation_version": "v1.0",
                "validation_summary": {
                    "overall_status": "failed",
                    "logical_consistency_score": 0.65,
                    "completeness_score": 0.65,
                    "evidence_support_score": 0.65,
                    "schema_compliance_score": 0.75,
                    "critical_issues": 0,
                    "quality_score": 0.67,
                },
                "issues": [],
            }

            mock_llm.generate_json_with_schema.side_effect = [
                mock_appraisal_response,  # iter 0
                validation1,  # iter 0 validation
                mock_appraisal_response,  # iter 1 correction
                validation2,  # iter 1 validation (degraded)
                mock_appraisal_response,  # iter 2 correction
                validation3,  # iter 2 validation (degraded more)
            ]
            mock_get_provider.return_value = mock_llm

            result = run_appraisal_with_correction(
                extraction_result=mock_extraction_interventional,
                classification_result=mock_classification_interventional,
                llm_provider="openai",
                file_manager=file_manager,
                max_iterations=5,
            )

            # Should stop early due to degradation
            assert result["final_status"] in ["early_stopped_degradation", "max_iterations_reached"]
            # Best should be iteration 0 (highest quality)
            assert result["best_iteration"] == 0
