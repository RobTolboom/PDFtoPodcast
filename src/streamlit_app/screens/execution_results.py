# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Step result display functions for pipeline execution screen.

This module provides result rendering for each pipeline step, showing
summaries, metrics tables, and iteration history. Extracted from
execution_display.py for modularity.

Public API:
    - display_classification_result(): Show publication type and DOI
    - display_extraction_result(): Show field count and title
    - display_validation_result(): Show validation status and quality
    - display_correction_result(): Show correction status
    - display_validation_correction_result(): Show iterative loop results
    - display_appraisal_result(): Show RoB, GRADE, applicability
    - display_report_result(): Show report generation results
    - trigger_appraisal_rerun(): Reset state for appraisal rerun
    - trigger_report_rerun(): Reset state for report rerun
"""

import pandas as pd
import streamlit as st

from src.pipeline.orchestrator import (
    ALL_PIPELINE_STEPS,
    STEP_APPRAISAL,
    STEP_REPORT_GENERATION,
)


def display_classification_result(result: dict):
    """Display classification step result summary."""
    if not result:
        return

    pub_type = result.get("publication_type", "Unknown")
    st.write(f"**Publication Type:** `{pub_type}`")

    # Show DOI if available
    metadata = result.get("metadata", {})
    if isinstance(metadata, dict) and "doi" in metadata:
        doi = metadata["doi"]
        st.write(f"**DOI:** `{doi}`")


def display_extraction_result(result: dict):
    """Display extraction step result summary."""
    if not result:
        return

    # Count extracted fields (rough estimate)
    field_count = len(result) if isinstance(result, dict) else 0
    if field_count > 0:
        st.write(f"**Extracted fields:** {field_count}")

    # Show title if available
    if isinstance(result, dict):
        title = result.get("title") or result.get("metadata", {}).get("title")
        if title:
            st.write(f"**Title:** {title[:80]}{'...' if len(title) > 80 else ''}")


def display_validation_result(result: dict):
    """Display validation step result summary."""
    if not result:
        return

    # Show overall validation status
    is_valid = result.get("is_valid", False)
    status_text = "Valid" if is_valid else "Issues found"
    st.write(f"**Validation:** {status_text}")

    # Show error count if available
    errors = result.get("errors", [])
    if errors:
        error_count = len(errors)
        st.write(f"**Issues:** {error_count} schema validation error(s)")

    # Show quality score if available (from LLM validation)
    quality_score = result.get("quality_score")
    if quality_score is not None:
        st.write(f"**Quality Score:** {quality_score}/10")

    # Check for non-critical warnings
    warnings = _check_validation_warnings(result)
    if warnings:
        for warning in warnings:
            st.warning(f"{warning}")


def _check_validation_warnings(validation_result: dict) -> list[str]:
    """
    Check validation result for non-critical warnings.

    Args:
        validation_result: Validation result dictionary

    Returns:
        List of warning messages (empty if no warnings)
    """
    warnings = []

    # Check quality score
    quality_score = validation_result.get("quality_score")
    if quality_score is not None and quality_score < 8:
        warnings.append(f"Quality score is {quality_score}/10 (below recommended 8)")

    # Check for minor schema errors (errors exist but validation passed)
    is_valid = validation_result.get("is_valid", False)
    errors = validation_result.get("errors", [])
    if is_valid and errors:
        error_count = len(errors)
        warnings.append(f"{error_count} minor schema issue(s) found but validation passed")

    return warnings


def display_correction_result(result: dict):
    """Display correction step result summary."""
    if not result:
        return

    # Check if correction was applied or skipped
    correction_applied = result.get("correction_applied", False)
    if correction_applied:
        st.write("**Correction:** Applied")

        # Show number of corrections if available
        corrections = result.get("corrections", [])
        if corrections:
            st.write(f"**Changes:** {len(corrections)} corrections made")
    else:
        st.write("**Correction:** Not needed (validation passed)")


def display_validation_correction_result(result: dict):
    """Display validation & correction iterative loop result summary."""
    if not result:
        return

    final_status = result.get("final_status", "unknown")
    iteration_count = result.get("iteration_count", 0)
    iterations = result.get("iterations", [])

    # Display final status with appropriate icon
    status_messages = {
        "passed": "**Quality thresholds met!**",
        "max_iterations_reached": f"**Max iterations reached ({iteration_count})**",
        "early_stopped_degradation": "**Early stopping: quality degraded**",
    }

    status_msg = status_messages.get(final_status, f"**Failed:** {final_status}")
    st.write(status_msg)

    # Show iteration count and best iteration
    best_iteration = result.get("best_iteration", 0)
    st.write(f"**Iterations completed:** {iteration_count}")
    st.write(f"**Best iteration selected:** {best_iteration}")

    # Display iteration history table
    if iterations:
        st.markdown("#### Iteration History")

        # Build table data
        table_data = []
        for iter_data in iterations:
            metrics = iter_data.get("metrics", {})
            is_best = iter_data.get("iteration_num") == best_iteration

            table_data.append(
                {
                    "Iteration": iter_data.get("iteration_num", 0),
                    "Completeness": f"{metrics.get('completeness_score', 0):.1%}",
                    "Accuracy": f"{metrics.get('accuracy_score', 0):.1%}",
                    "Schema": f"{metrics.get('schema_compliance_score', 0):.1%}",
                    "Critical": metrics.get("critical_issues", 0),
                    "Overall": f"{metrics.get('overall_quality', 0):.1%}",
                    "Status": "BEST" if is_best else "",
                }
            )

        # Display as DataFrame
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        trajectory = result.get("improvement_trajectory", [])
        if trajectory:
            st.caption("Quality score trajectory per iteration")
            chart_df = pd.DataFrame(
                {"Quality Score": trajectory}, index=[f"Iter {i}" for i in range(len(trajectory))]
            )
            st.line_chart(chart_df)

    # Show metrics from best iteration
    if iterations and best_iteration < len(iterations):
        best_iter_data = iterations[best_iteration]
        best_metrics = best_iter_data.get("metrics", {})

        st.markdown("#### Best Iteration Metrics")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            comp = best_metrics.get("completeness_score", 0)
            st.metric("Completeness", f"{comp:.1%}")

        with col2:
            acc = best_metrics.get("accuracy_score", 0)
            st.metric("Accuracy", f"{acc:.1%}")

        with col3:
            schema = best_metrics.get("schema_compliance_score", 0)
            st.metric("Schema", f"{schema:.1%}")

        with col4:
            critical = best_metrics.get("critical_issues", 0)
            st.metric("Critical Issues", critical)


def display_appraisal_result(result: dict):
    """Display appraisal result summary with RoB, GRADE, and iteration history."""
    if not result:
        return

    best_appraisal = result.get("best_appraisal") or {}
    final_status = result.get("final_status", "unknown")
    iteration_count = result.get("iteration_count", 0)
    iterations = result.get("iterations", [])

    # Display final status
    status_messages = {
        "passed": "**Appraisal quality thresholds met!**",
        "max_iterations_reached": f"**Max iterations reached ({iteration_count})**",
        "early_stopped_degradation": "**Early stopping: quality degraded**",
    }

    status_msg = status_messages.get(final_status, f"**Failed:** {final_status}")
    st.write(status_msg)

    # Show iteration count and best iteration
    best_iteration = result.get("best_iteration", 0)
    st.write(f"**Iterations completed:** {iteration_count}")
    st.write(f"**Best iteration selected:** {best_iteration}")

    # Display Risk of Bias Summary
    if "risk_of_bias" in best_appraisal:
        st.markdown("#### Risk of Bias Assessment")

        rob = best_appraisal["risk_of_bias"]
        tool_info = best_appraisal.get("tool", {})
        tool_name = tool_info.get("name", "Unknown")
        tool_variant = tool_info.get("variant", "")

        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("Tool", tool_name)
        with col2:
            if tool_variant:
                st.metric("Variant", tool_variant)

        # Overall judgement
        overall = rob.get("overall", "—")
        st.write(f"**Overall Risk of Bias:** {overall}")

        # Domain assessments
        domains = rob.get("domains", [])
        if domains:
            st.markdown(f"**Domains Assessed:** {len(domains)}")

            # Show first few domains
            for domain in domains[:5]:
                domain_name = domain.get("domain", "Unknown")
                judgement = domain.get("judgement", "—")
                st.write(f"  - {domain_name}: {judgement}")

            if len(domains) > 5:
                st.caption(f"_...and {len(domains) - 5} more domains (view full JSON for details)_")

    # Display GRADE Certainty
    grade_outcomes = best_appraisal.get("grade_per_outcome", [])
    if grade_outcomes:
        st.markdown("#### GRADE Certainty of Evidence")
        st.write(f"**Outcomes Rated:** {len(grade_outcomes)}")

        # Show first few outcomes
        for grade in grade_outcomes[:3]:
            outcome_id = grade.get("outcome_id", "Unknown")
            certainty = grade.get("certainty", "—")
            downgrades = grade.get("downgrades", {})

            # Build list of non-zero downgrades with their levels
            downgrade_items = []
            if downgrades:
                downgrade_labels = {
                    "risk_of_bias": "RoB",
                    "inconsistency": "Incons",
                    "indirectness": "Indir",
                    "imprecision": "Imprec",
                    "publication_bias": "PubBias",
                }
                for key, label in downgrade_labels.items():
                    level = downgrades.get(key)
                    if level and level > 0:
                        downgrade_items.append(f"{label}(-{level})")

            downgrade_summary = ", ".join(downgrade_items) if downgrade_items else "None"
            st.write(f"  - {outcome_id}: **{certainty}** (downgrades: {downgrade_summary})")

        if len(grade_outcomes) > 3:
            st.caption(f"_...and {len(grade_outcomes) - 3} more outcomes_")

    # Display Applicability
    applicability = best_appraisal.get("applicability", {})
    if applicability:
        st.markdown("#### Applicability")
        population_match = applicability.get("population_match", {}).get("rating", "—")
        st.write(f"**Population Match:** {population_match}")

    # Display iteration history table
    if iterations:
        st.markdown("#### Iteration History")

        # Build table data
        table_data = []
        for iter_data in iterations:
            metrics = iter_data.get("metrics", {})
            is_best = iter_data.get("iteration_num") == best_iteration

            table_data.append(
                {
                    "Iteration": iter_data.get("iteration_num", 0),
                    "Logical": f"{metrics.get('logical_consistency_score', 0):.1%}",
                    "Complete": f"{metrics.get('completeness_score', 0):.1%}",
                    "Evidence": f"{metrics.get('evidence_support_score', 0):.1%}",
                    "Schema": f"{metrics.get('schema_compliance_score', 0):.1%}",
                    "Critical": metrics.get("critical_issues", 0),
                    "Quality": f"{metrics.get('quality_score', 0):.1%}",
                    "Status": "BEST" if is_best else "",
                }
            )

        # Display as DataFrame
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Show metrics from best iteration
    if iterations and best_iteration < len(iterations):
        best_iter_data = iterations[best_iteration]
        best_metrics = best_iter_data.get("metrics", {})

        st.markdown("#### Best Iteration Metrics")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            logical = best_metrics.get("logical_consistency_score", 0)
            st.metric("Logical", f"{logical:.1%}")

        with col2:
            comp = best_metrics.get("completeness_score", 0)
            st.metric("Complete", f"{comp:.1%}")

        with col3:
            evidence = best_metrics.get("evidence_support_score", 0)
            st.metric("Evidence", f"{evidence:.1%}")

        with col4:
            schema = best_metrics.get("schema_compliance_score", 0)
            st.metric("Schema", f"{schema:.1%}")

    # Bottom line for podcast
    bottom_line = best_appraisal.get("bottom_line", {})
    if bottom_line:
        st.markdown("#### Bottom Line (for Podcast)")
        for_podcast = bottom_line.get("for_podcast", "—")
        st.info(for_podcast)

    execution_status = st.session_state.execution.get("status", "idle")
    if execution_status in {"completed", "failed"}:
        if st.button("Re-run appraisal", key="rerun_appraisal"):
            trigger_appraisal_rerun()


def display_report_result(result: dict):
    """
    Render a brief summary for the report step (best iteration, quality, outputs).
    """
    if not result:
        st.write("Report generation completed.")
        return

    final_status = result.get("final_status", result.get("_pipeline_metadata", {}).get("status"))
    best_iter = result.get("best_iteration")
    best_validation = result.get("best_validation") or {}
    quality = best_validation.get("validation_summary", {}).get("quality_score")
    warnings = result.get("_pipeline_metadata", {}).get("warnings")

    if best_iter is not None:
        st.write(f"**Best iteration:** {best_iter}")
    if quality is not None:
        st.write(f"**Quality score:** {quality:.2f}")
    if final_status:
        st.write(f"**Final status:** {final_status}")
    if warnings:
        st.warning(f"{warnings}")

    # Show validation status if available
    best_val_status = best_validation.get("validation_summary", {}).get("overall_status")
    if best_val_status:
        st.write(f"**Validation:** {best_val_status}")

    # Get iterations for history table
    iterations = result.get("iterations", [])
    best_iteration = result.get("best_iteration", 0)

    # Display iteration history table
    if iterations:
        st.markdown("#### Iteration History")

        # Build table data
        table_data = []
        for iter_data in iterations:
            metrics = iter_data.get("metrics", {})
            is_best = iter_data.get("iteration_num") == best_iteration

            table_data.append(
                {
                    "Iteration": iter_data.get("iteration_num", 0),
                    "Complete": f"{metrics.get('completeness_score', 0):.1%}",
                    "Accuracy": f"{metrics.get('accuracy_score', 0):.1%}",
                    "XRef": f"{metrics.get('cross_reference_consistency_score', 0):.1%}",
                    "Data": f"{metrics.get('data_consistency_score', 0):.1%}",
                    "Schema": f"{metrics.get('schema_compliance_score', 0):.1%}",
                    "Critical": metrics.get("critical_issues", 0),
                    "Quality": f"{metrics.get('quality_score', 0):.1%}",
                    "Status": "BEST" if is_best else "",
                }
            )

        # Display as DataFrame
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Show metrics from best iteration
    if iterations and best_iteration < len(iterations):
        best_iter_data = iterations[best_iteration]
        best_metrics = best_iter_data.get("metrics", {})

        st.markdown("#### Best Iteration Metrics")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            completeness = best_metrics.get("completeness_score", 0)
            st.metric("Completeness", f"{completeness:.1%}")

        with col2:
            accuracy = best_metrics.get("accuracy_score", 0)
            st.metric("Accuracy", f"{accuracy:.1%}")

        with col3:
            xref = best_metrics.get("cross_reference_consistency_score", 0)
            st.metric("XRef Consistency", f"{xref:.1%}")

        with col4:
            data_cons = best_metrics.get("data_consistency_score", 0)
            st.metric("Data Consistency", f"{data_cons:.1%}")

    # Re-run button
    execution_status = st.session_state.execution.get("status", "idle")
    if execution_status in {"completed", "failed"}:
        if st.button("Re-run report generation", key="rerun_report"):
            trigger_report_rerun()


def trigger_appraisal_rerun():
    """Reset state so appraisal step reruns from the execution screen."""
    exec_state = st.session_state.execution
    exec_state["status"] = "running"
    exec_state["error"] = None
    exec_state["redirect_countdown"] = None
    exec_state["redirect_cancelled"] = False
    exec_state["end_time"] = None
    exec_state["results"].pop(STEP_APPRAISAL, None)

    # Reset appraisal step status
    st.session_state.step_status[STEP_APPRAISAL] = {
        "status": "pending",
        "start_time": None,
        "end_time": None,
        "result": None,
        "error": None,
        "elapsed_seconds": None,
        "verbose_data": {},
        "file_path": None,
    }

    exec_state["current_step_index"] = ALL_PIPELINE_STEPS.index(STEP_APPRAISAL)
    st.rerun()


def trigger_report_rerun():
    """Reset state so report generation step reruns from the execution screen."""
    exec_state = st.session_state.execution
    exec_state["status"] = "running"
    exec_state["error"] = None
    exec_state["redirect_countdown"] = None
    exec_state["redirect_cancelled"] = False
    exec_state["end_time"] = None
    exec_state["results"].pop(STEP_REPORT_GENERATION, None)

    # Reset report generation step status
    st.session_state.step_status[STEP_REPORT_GENERATION] = {
        "status": "pending",
        "start_time": None,
        "end_time": None,
        "result": None,
        "error": None,
        "elapsed_seconds": None,
        "verbose_data": {},
        "file_path": None,
    }

    exec_state["current_step_index"] = ALL_PIPELINE_STEPS.index(STEP_REPORT_GENERATION)
    st.rerun()
