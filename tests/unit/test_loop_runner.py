"""
Unit tests for the IterativeLoopRunner.

Tests cover:
- IterativeLoopConfig dataclass
- IterativeLoopResult dataclass
- IterativeLoopRunner with various scenarios
- Success, early stop, max iterations, and error cases
"""

from pathlib import Path
from unittest.mock import MagicMock

from src.pipeline.iterative import (
    IterativeLoopConfig,
    IterativeLoopResult,
    IterativeLoopRunner,
)
from src.pipeline.iterative.loop_runner import (
    FINAL_STATUS_EARLY_STOPPED,
    FINAL_STATUS_FAILED,
    FINAL_STATUS_FAILED_SCHEMA,
    FINAL_STATUS_MAX_ITERATIONS,
    FINAL_STATUS_PASSED,
)
from src.pipeline.quality import MetricType, QualityThresholds


class TestIterativeLoopConfig:
    """Tests for IterativeLoopConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = IterativeLoopConfig(metric_type=MetricType.EXTRACTION)

        assert config.metric_type == MetricType.EXTRACTION
        assert config.max_iterations == 3
        assert config.quality_thresholds is None
        assert config.degradation_window == 2
        assert config.step_name == "ITERATIVE LOOP"

    def test_custom_values(self):
        """Test custom configuration values."""
        thresholds = QualityThresholds(completeness_score=0.80)
        config = IterativeLoopConfig(
            metric_type=MetricType.APPRAISAL,
            max_iterations=5,
            quality_thresholds=thresholds,
            degradation_window=3,
            step_name="APPRAISAL CORRECTION",
        )

        assert config.metric_type == MetricType.APPRAISAL
        assert config.max_iterations == 5
        assert config.quality_thresholds == thresholds
        assert config.degradation_window == 3


class TestIterativeLoopResult:
    """Tests for IterativeLoopResult dataclass."""

    def test_creation(self):
        """Test creating a result."""
        result = IterativeLoopResult(
            best_result={"data": "test"},
            best_validation={"status": "passed"},
            iterations=[{"iteration_num": 0}],
            final_status=FINAL_STATUS_PASSED,
            iteration_count=1,
        )

        assert result.best_result == {"data": "test"}
        assert result.final_status == FINAL_STATUS_PASSED
        assert result.iteration_count == 1

    def test_to_dict(self):
        """Test conversion to dict."""
        result = IterativeLoopResult(
            best_result={"data": "test"},
            best_validation={"status": "passed"},
            iterations=[],
            final_status=FINAL_STATUS_PASSED,
            iteration_count=1,
            improvement_trajectory=[0.85, 0.90],
        )

        d = result.to_dict("best_extraction")

        assert d["best_extraction"] == {"data": "test"}
        assert d["best_validation"] == {"status": "passed"}
        assert d["final_status"] == FINAL_STATUS_PASSED
        assert d["improvement_trajectory"] == [0.85, 0.90]

    def test_to_dict_with_error(self):
        """Test conversion to dict with error info."""
        result = IterativeLoopResult(
            best_result=None,
            best_validation=None,
            iterations=[],
            final_status=FINAL_STATUS_FAILED,
            iteration_count=1,
            error="Something went wrong",
            failed_at_iteration=0,
        )

        d = result.to_dict()

        assert d["error"] == "Something went wrong"
        assert d["failed_at_iteration"] == 0


class TestIterativeLoopRunner:
    """Tests for IterativeLoopRunner class."""

    def _create_validation_result(
        self,
        completeness: float = 0.95,
        accuracy: float = 0.98,
        schema_compliance: float = 0.97,
        critical_issues: int = 0,
        schema_quality: float = 1.0,
    ) -> dict:
        """Create a mock validation result."""
        return {
            "verification_summary": {
                "completeness_score": completeness,
                "accuracy_score": accuracy,
                "schema_compliance_score": schema_compliance,
                "critical_issues": critical_issues,
                "overall_status": "passed" if critical_issues == 0 else "failed",
            },
            "schema_validation": {
                "quality_score": schema_quality,
            },
        }

    def test_immediate_success(self):
        """Test loop that passes immediately on first validation."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            show_banner=False,
        )

        # Mock functions
        validate_fn = MagicMock(
            return_value=self._create_validation_result(
                completeness=0.95, accuracy=0.98, schema_compliance=0.97
            )
        )
        correct_fn = MagicMock()

        # Create and run
        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
        )
        result = runner.run()

        # Assert
        assert result.final_status == FINAL_STATUS_PASSED
        assert result.iteration_count == 1
        assert result.best_result == {"data": "test"}
        assert validate_fn.call_count == 1
        assert correct_fn.call_count == 0  # No correction needed

    def test_success_after_one_correction(self):
        """Test loop that passes after one correction."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            show_banner=False,
        )

        # First validation fails, corrected validation passes
        validation_fail = self._create_validation_result(
            completeness=0.80, accuracy=0.85, schema_compliance=0.90
        )
        validation_pass = self._create_validation_result(
            completeness=0.95, accuracy=0.98, schema_compliance=0.97
        )

        validate_fn = MagicMock(side_effect=[validation_fail, validation_pass])
        correct_fn = MagicMock(return_value={"data": "corrected"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_PASSED
        assert result.iteration_count == 2
        assert result.best_result == {"data": "corrected"}
        assert validate_fn.call_count == 2
        assert correct_fn.call_count == 1

    def test_max_iterations_reached(self):
        """Test loop that reaches max iterations."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=2,
            show_banner=False,
        )

        # All validations fail (below threshold)
        validation_fail = self._create_validation_result(
            completeness=0.80, accuracy=0.85, schema_compliance=0.90
        )

        validate_fn = MagicMock(return_value=validation_fail)
        correct_fn = MagicMock(return_value={"data": "corrected"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_MAX_ITERATIONS
        # Initial + 2 corrections = 3 validations, but correction happens after validation
        # So: iter 0 (validate, correct), iter 1 (validate from correction, correct), iter 2 (validate from correction)
        assert result.iteration_count == 3
        assert result.best_result is not None

    def test_early_stop_on_degradation(self):
        """Test early stopping when quality degrades."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=5,
            degradation_window=2,
            show_banner=False,
        )

        # Quality improves then degrades
        validations = [
            self._create_validation_result(
                completeness=0.80, accuracy=0.85, schema_compliance=0.90
            ),
            self._create_validation_result(
                completeness=0.88, accuracy=0.90, schema_compliance=0.92
            ),  # Peak
            self._create_validation_result(
                completeness=0.85, accuracy=0.87, schema_compliance=0.91
            ),  # Degrade
            self._create_validation_result(
                completeness=0.82, accuracy=0.84, schema_compliance=0.89
            ),  # Degrade again
        ]

        validate_fn = MagicMock(side_effect=validations)
        correct_fn = MagicMock(return_value={"data": "corrected"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_EARLY_STOPPED
        assert result.best_iteration_num == 1  # Peak was at iteration 1

    def test_schema_validation_failure(self):
        """Test handling of schema validation failure."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            show_banner=False,
        )

        # Low schema_compliance triggers schema failure (schema_compliance_score is read by _get_schema_quality)
        validation_schema_fail = self._create_validation_result(schema_compliance=0.3)

        validate_fn = MagicMock(return_value=validation_schema_fail)
        correct_fn = MagicMock()

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            check_schema_quality=True,
            schema_quality_threshold=0.5,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_FAILED_SCHEMA
        assert result.best_result is None
        assert result.error is not None
        assert "Schema validation failed" in result.error

    def test_exception_handling(self):
        """Test handling of exceptions during iteration."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            show_banner=False,
        )

        validate_fn = MagicMock(side_effect=Exception("API Error"))
        correct_fn = MagicMock()

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_FAILED
        assert result.error == "API Error"

    def test_save_callbacks_called(self):
        """Test that save callbacks are called correctly."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            show_banner=False,
        )

        validate_fn = MagicMock(
            return_value=self._create_validation_result(
                completeness=0.95, accuracy=0.98, schema_compliance=0.97
            )
        )
        correct_fn = MagicMock()
        save_iteration_fn = MagicMock(
            return_value=(Path("/tmp/result.json"), Path("/tmp/val.json"))
        )
        save_best_fn = MagicMock(return_value=(Path("/tmp/best.json"), Path("/tmp/best_val.json")))

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            save_iteration_fn=save_iteration_fn,
            save_best_fn=save_best_fn,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_PASSED
        assert save_iteration_fn.call_count == 1  # Called for iteration 0
        assert save_best_fn.call_count == 1  # Called on success

    def test_progress_callback(self):
        """Test that progress callbacks are called."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            show_banner=False,
        )

        validate_fn = MagicMock(
            return_value=self._create_validation_result(
                completeness=0.95, accuracy=0.98, schema_compliance=0.97
            )
        )
        correct_fn = MagicMock()
        progress_callback = MagicMock()

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            progress_callback=progress_callback,
        )
        runner.run()

        assert progress_callback.call_count >= 1

    def test_improvement_trajectory_tracked(self):
        """Test that improvement trajectory is tracked."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=2,
            show_banner=False,
        )

        validations = [
            self._create_validation_result(
                completeness=0.80, accuracy=0.85, schema_compliance=0.90
            ),
            self._create_validation_result(
                completeness=0.85, accuracy=0.88, schema_compliance=0.92
            ),
            self._create_validation_result(
                completeness=0.95, accuracy=0.98, schema_compliance=0.97
            ),
        ]

        validate_fn = MagicMock(side_effect=validations)
        correct_fn = MagicMock(return_value={"data": "corrected"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
        )
        result = runner.run()

        assert len(result.improvement_trajectory) == 3
        # Quality should improve
        assert result.improvement_trajectory[-1] > result.improvement_trajectory[0]

    def test_save_failed_fn_called_on_schema_failure(self):
        """Test that save_failed_fn is called when schema validation fails."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            show_banner=False,
        )

        # Low schema_compliance triggers schema failure
        validation_schema_fail = self._create_validation_result(schema_compliance=0.3)

        validate_fn = MagicMock(return_value=validation_schema_fail)
        correct_fn = MagicMock()
        save_failed_fn = MagicMock(
            return_value=(Path("/tmp/failed.json"), Path("/tmp/failed_val.json"))
        )

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            check_schema_quality=True,
            schema_quality_threshold=0.5,
            save_failed_fn=save_failed_fn,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_FAILED_SCHEMA
        assert save_failed_fn.call_count == 1
        # Verify correct arguments passed
        save_failed_fn.assert_called_once_with({"data": "test"}, validation_schema_fail)

    def test_initial_retry_exhaustion(self):
        """Test that initial retry exhaustion returns schema failure."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            max_initial_retries=2,
            show_banner=False,
        )

        # Low schema_compliance triggers schema failure
        validation_schema_fail = self._create_validation_result(schema_compliance=0.3)

        validate_fn = MagicMock(return_value=validation_schema_fail)
        correct_fn = MagicMock()
        regenerate_initial_fn = MagicMock(return_value={"data": "regenerated"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            regenerate_initial_fn=regenerate_initial_fn,
            check_schema_quality=True,
            schema_quality_threshold=0.5,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_FAILED_SCHEMA
        # With max_initial_retries=2 and the off-by-one fix (> instead of >=),
        # we get exactly 2 regenerate calls (original + 2 retries = 3 attempts)
        assert regenerate_initial_fn.call_count == 2
        # Correct should not have been called (never passed schema check)
        assert correct_fn.call_count == 0

    def test_initial_retry_success_on_second_attempt(self):
        """Test that initial retry succeeds on second attempt."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            max_initial_retries=2,
            show_banner=False,
        )

        validation_schema_fail = self._create_validation_result(schema_compliance=0.3)
        validation_pass = self._create_validation_result(
            completeness=0.95, accuracy=0.98, schema_compliance=0.97
        )

        # First validation fails, second succeeds
        validate_fn = MagicMock(side_effect=[validation_schema_fail, validation_pass])
        correct_fn = MagicMock()
        regenerate_initial_fn = MagicMock(return_value={"data": "regenerated"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            regenerate_initial_fn=regenerate_initial_fn,
            check_schema_quality=True,
            schema_quality_threshold=0.5,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_PASSED
        assert regenerate_initial_fn.call_count == 1
        assert result.best_result == {"data": "regenerated"}

    def test_correction_retry_exhaustion(self):
        """Test that correction retry exhaustion returns max iterations result."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            max_correction_retries=2,
            show_banner=False,
        )

        # Initial validation passes schema check but needs correction
        validation_needs_correction = self._create_validation_result(
            completeness=0.80, accuracy=0.85, schema_compliance=0.90
        )
        # Correction produces result that fails schema check
        validation_correction_fail = self._create_validation_result(schema_compliance=0.3)

        validate_fn = MagicMock(
            side_effect=[validation_needs_correction] + [validation_correction_fail] * 10
        )
        correct_fn = MagicMock(return_value={"data": "corrected"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            check_schema_quality=True,
            schema_quality_threshold=0.5,
        )
        result = runner.run()

        # Should return max iterations since correction retries exhausted
        assert result.final_status == FINAL_STATUS_MAX_ITERATIONS
        # Correct should have been called (retries happen)
        assert correct_fn.call_count >= 1

    def test_correction_retry_count_resets_per_iteration(self):
        """Test that correction retry count resets for each new iteration.

        This verifies the fix for the bug where correction_retry_count persisted
        across iterations, causing premature max retry failures.

        Scenario:
        - Iteration 0: Initial passes, correction fails once then succeeds
        - Iteration 1: Correction fails once then succeeds
        - Iteration 2: Quality passes

        Without the fix, the retry count would accumulate across iterations.
        With the fix, each iteration starts with retry_count=0.
        """
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=5,
            max_correction_retries=2,
            show_banner=False,
        )

        # Initial validation needs correction (good schema, low quality)
        validation_needs_correction = self._create_validation_result(
            completeness=0.80, accuracy=0.85, schema_compliance=0.90
        )
        # Correction fails schema first time
        validation_correction_fail = self._create_validation_result(schema_compliance=0.3)
        # Correction succeeds on retry (good schema, still needs more correction)
        validation_correction_retry_ok = self._create_validation_result(
            completeness=0.85, accuracy=0.87, schema_compliance=0.92
        )
        # Final pass
        validation_pass = self._create_validation_result(
            completeness=0.95, accuracy=0.98, schema_compliance=0.97
        )

        # Sequence:
        # 1. iter 0: validate initial -> needs correction
        # 2. iter 0: correct -> validate -> schema fail
        # 3. iter 0: retry correct -> validate -> ok but needs more
        # 4. iter 1: reuse validation from step 3 (correction result)
        # 5. iter 1: correct -> validate -> schema fail
        # 6. iter 1: retry correct -> validate -> ok but needs more
        # 7. iter 2: reuse validation, correct -> validate -> pass
        validate_fn = MagicMock(
            side_effect=[
                validation_needs_correction,  # iter 0 initial
                validation_correction_fail,  # iter 0 correction 1
                validation_correction_retry_ok,  # iter 0 correction retry
                validation_correction_fail,  # iter 1 correction 1
                validation_correction_retry_ok,  # iter 1 correction retry
                validation_pass,  # iter 2 correction -> pass
            ]
        )
        correct_fn = MagicMock(return_value={"data": "corrected"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            check_schema_quality=True,
            schema_quality_threshold=0.5,
        )
        result = runner.run()

        # Should pass because retry count resets per iteration
        assert result.final_status == FINAL_STATUS_PASSED
        # Multiple corrections should have been called
        assert correct_fn.call_count >= 3

    def test_save_failed_fn_called_on_correction_retry_exhaustion_with_history(self):
        """Test that save_failed_fn is called even when iteration_count > 0.

        This verifies the fix for inconsistent save_failed_fn behavior.
        Previously, save_failed_fn was only called when iteration_count == 0.
        """
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            max_correction_retries=1,
            show_banner=False,
        )

        # First validation passes schema but needs correction
        validation_needs_correction = self._create_validation_result(
            completeness=0.80, accuracy=0.85, schema_compliance=0.90
        )
        # Correction always fails schema
        validation_correction_fail = self._create_validation_result(schema_compliance=0.3)

        validate_fn = MagicMock(
            side_effect=[validation_needs_correction] + [validation_correction_fail] * 10
        )
        correct_fn = MagicMock(return_value={"data": "corrected"})
        save_failed_fn = MagicMock(
            return_value=(Path("/tmp/failed.json"), Path("/tmp/failed_val.json"))
        )

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            check_schema_quality=True,
            schema_quality_threshold=0.5,
            save_failed_fn=save_failed_fn,
        )
        result = runner.run()

        # Should return max iterations (we have history from iteration 0)
        assert result.final_status == FINAL_STATUS_MAX_ITERATIONS
        # save_failed_fn MUST be called even though iteration_count > 0
        assert save_failed_fn.call_count >= 1

    def test_initial_retry_allows_full_retry_count(self):
        """Test that max_initial_retries=2 allows exactly 2 retries (3 total attempts).

        This verifies the off-by-one fix where >= was changed to >.
        """
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            max_initial_retries=2,
            show_banner=False,
        )

        validation_schema_fail = self._create_validation_result(schema_compliance=0.3)

        validate_fn = MagicMock(return_value=validation_schema_fail)
        correct_fn = MagicMock()
        regenerate_initial_fn = MagicMock(return_value={"data": "regenerated"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            regenerate_initial_fn=regenerate_initial_fn,
            check_schema_quality=True,
            schema_quality_threshold=0.5,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_FAILED_SCHEMA
        # With max_initial_retries=2, we should get exactly 2 regenerate calls
        # (original attempt + 2 retries = 3 attempts, but 2 regenerates)
        assert regenerate_initial_fn.call_count == 2


class TestIterativeLoopRunnerAppraisal:
    """Tests for IterativeLoopRunner with appraisal metrics."""

    def _create_appraisal_validation(
        self,
        logical_consistency: float = 0.95,
        completeness: float = 0.90,
        evidence_support: float = 0.92,
        schema_compliance: float = 0.97,
        critical_issues: int = 0,
    ) -> dict:
        """Create mock appraisal validation result."""
        return {
            "validation_summary": {
                "logical_consistency_score": logical_consistency,
                "completeness_score": completeness,
                "evidence_support_score": evidence_support,
                "schema_compliance_score": schema_compliance,
                "critical_issues": critical_issues,
                "overall_status": "passed",
                "quality_score": (
                    logical_consistency * 0.35
                    + completeness * 0.25
                    + evidence_support * 0.25
                    + schema_compliance * 0.15
                ),
            },
            "schema_validation": {"quality_score": 1.0},
        }

    def test_appraisal_immediate_success(self):
        """Test appraisal loop that passes immediately."""
        config = IterativeLoopConfig(
            metric_type=MetricType.APPRAISAL,
            max_iterations=3,
            show_banner=False,
        )

        validate_fn = MagicMock(return_value=self._create_appraisal_validation())
        correct_fn = MagicMock()

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"appraisal": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            check_schema_quality=False,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_PASSED
        assert result.iteration_count == 1


class TestIterativeLoopRunnerReport:
    """Tests for IterativeLoopRunner with report metrics."""

    def _create_report_validation(
        self,
        accuracy: float = 0.95,
        completeness: float = 0.90,
        cross_ref: float = 0.92,
        data_consistency: float = 0.90,
        schema_compliance: float = 0.97,
        critical_issues: int = 0,
    ) -> dict:
        """Create mock report validation result."""
        return {
            "validation_summary": {
                "accuracy_score": accuracy,
                "completeness_score": completeness,
                "cross_reference_consistency_score": cross_ref,
                "data_consistency_score": data_consistency,
                "schema_compliance_score": schema_compliance,
                "critical_issues": critical_issues,
                "overall_status": "passed",
                "quality_score": (
                    accuracy * 0.35
                    + completeness * 0.30
                    + cross_ref * 0.10
                    + data_consistency * 0.10
                    + schema_compliance * 0.15
                ),
            },
            "schema_validation": {"quality_score": 1.0},
        }

    def test_report_immediate_success(self):
        """Test report loop that passes immediately."""
        config = IterativeLoopConfig(
            metric_type=MetricType.REPORT,
            max_iterations=3,
            show_banner=False,
        )

        validate_fn = MagicMock(return_value=self._create_report_validation())
        correct_fn = MagicMock()

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"report": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
            check_schema_quality=False,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_PASSED
        assert result.iteration_count == 1
