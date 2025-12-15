# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
UI display functions for pipeline execution screen.

This module provides all result display and UI rendering functions for the
Streamlit pipeline interface, extracted from execution.py for modularity.

Public API:
    - display_step_status(): Render step progress UI
    - display_report_artifacts(): Show report download buttons
    - display_podcast_artifacts(): Show podcast download buttons
    - display_verbose_info(): Show verbose logging details
    - display_error_with_guidance(): Show error with troubleshooting
    - Various _display_*_result() functions for step-specific rendering
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from src.pipeline.file_manager import PipelineFileManager
from src.pipeline.orchestrator import (
    ALL_PIPELINE_STEPS,
    STEP_APPRAISAL,
    STEP_CLASSIFICATION,
    STEP_CORRECTION,
    STEP_EXTRACTION,
    STEP_REPORT_GENERATION,
    STEP_VALIDATION,
    STEP_VALIDATION_CORRECTION,
)

from .execution_callbacks import (
    classify_error_type,
    extract_token_usage,
    get_error_guidance,
)


def display_verbose_info(step_name: str, verbose_data: dict, result: dict | None):
    """
    Display verbose logging information for a pipeline step.

    Shows detailed information when verbose logging is enabled, including:
    - Starting data (PDF path, publication type, etc.)
    - Completion data (file path, token usage)
    - Timing details

    Args:
        step_name: Step identifier ("classification", "extraction", "validation", "correction")
        verbose_data: Dict of callback data by status {starting: {...}, completed: {...}}
        result: Step result dictionary (may contain token usage)

    Example:
        >>> display_verbose_info("classification", {...}, {...})
        # Renders verbose details in Streamlit UI
    """
    st.markdown("#### Verbose Details")

    # Display starting data
    starting_data = verbose_data.get("starting", {})
    if starting_data:
        st.markdown("**Starting parameters:**")

        if step_name == STEP_CLASSIFICATION:
            if "pdf_path" in starting_data:
                st.write(f"- PDF: `{starting_data['pdf_path']}`")
            if "max_pages" in starting_data:
                max_pages = starting_data["max_pages"] or "All"
                st.write(f"- Max pages: {max_pages}")

        elif step_name == STEP_EXTRACTION:
            if "publication_type" in starting_data:
                st.write(f"- Publication type: `{starting_data['publication_type']}`")

        elif step_name == STEP_CORRECTION:
            if "validation_status" in starting_data:
                st.write(f"- Validation status: {starting_data['validation_status']}")

    # Display token usage if available
    if result:
        token_usage = extract_token_usage(result)
        if token_usage:
            st.markdown("**Token usage:**")
            if "input" in token_usage:
                st.write(f"- Input tokens: {token_usage['input']:,}")
            if "output" in token_usage:
                st.write(f"- Output tokens: {token_usage['output']:,}")
            if "total" in token_usage:
                st.write(f"- Total tokens: {token_usage['total']:,}")

        # Display cached tokens if available (cost optimization)
        usage = result.get("usage", {})
        cached_tokens = usage.get("cached_tokens")
        if cached_tokens:
            st.markdown("**Cache efficiency:**")
            input_tokens = usage.get("input_tokens", 0)
            if input_tokens > 0:
                cache_hit_pct = (cached_tokens / input_tokens) * 100
                st.write(f"- Cached tokens: {cached_tokens:,} ({cache_hit_pct:.1f}% cache hit)")
            else:
                st.write(f"- Cached tokens: {cached_tokens:,}")

        # Display reasoning tokens if significant
        reasoning_tokens = usage.get("reasoning_tokens")
        if reasoning_tokens:
            st.markdown("**Reasoning tokens:**")
            output_tokens = usage.get("output_tokens", 0)
            if output_tokens > 0:
                reasoning_pct = (reasoning_tokens / output_tokens) * 100
                st.write(f"- Reasoning: {reasoning_tokens:,} ({reasoning_pct:.1f}% of output)")
            else:
                st.write(f"- Reasoning: {reasoning_tokens:,}")

        # Display response metadata
        metadata = result.get("_metadata", {})
        if metadata:
            st.markdown("**Response metadata:**")
            if "model" in metadata:
                st.write(f"- Model: `{metadata['model']}`")
            if "response_id" in metadata:
                st.write(f"- Response ID: `{metadata['response_id']}`")
            if "status" in metadata:
                st.write(f"- Status: {metadata['status']}")
            if "stop_reason" in metadata:
                st.write(f"- Stop reason: {metadata['stop_reason']}")

            # Expandable reasoning summary for GPT-5/o-series
            reasoning = metadata.get("reasoning", {})
            if reasoning and "summary" in reasoning:
                with st.expander("Reasoning Summary"):
                    st.write(reasoning["summary"])
                    if "effort" in reasoning:
                        st.caption(f"Effort level: {reasoning['effort']}")

    # Display completion data
    completed_data = verbose_data.get("completed", {})
    if completed_data:
        # File path is already shown in main display, but can show size here
        if "file_path" in completed_data:
            file_path = completed_data["file_path"]
            st.caption(f"Output: `{file_path}`")


def display_error_with_guidance(error_msg: str, step_name: str, step: dict):
    """
    Display error with actionable guidance and troubleshooting steps.

    Shows:
    - Error title and user-friendly message
    - Numbered action steps
    - Expandable technical details section

    Args:
        error_msg: Error message from exception
        step_name: Step where error occurred
        step: Step status dict (may contain additional error info)

    Example:
        >>> display_error_with_guidance("401 Unauthorized", "classification", {...})
        # Renders error with guidance in Streamlit UI
    """
    # Classify error and get guidance
    error_type = classify_error_type(error_msg, step_name)
    guidance = get_error_guidance(error_type, error_msg)

    # Display error title and message
    st.error(f"**{guidance['title']}**")
    st.markdown(guidance["message"])

    # Display action steps
    st.markdown("**Troubleshooting steps:**")
    for i, action in enumerate(guidance["actions"], 1):
        st.markdown(f"{i}. {action}")

    # Expandable technical details
    with st.expander("Technical Details"):
        st.code(guidance["technical_details"], language="text")

        # Show additional context if available
        if "error_type" in step.get("verbose_data", {}).get("failed", {}):
            error_type_name = step["verbose_data"]["failed"]["error_type"]
            st.caption(f"**Exception type:** `{error_type_name}`")


def check_validation_warnings(validation_result: dict) -> list[str]:
    """
    Check validation result for non-critical warnings.

    Args:
        validation_result: Validation result dictionary

    Returns:
        List of warning messages (empty if no warnings)

    Example:
        >>> result = {"is_valid": True, "quality_score": 6}
        >>> check_validation_warnings(result)
        ['Quality score is 6/10 (below recommended 8)']
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
    warnings = check_validation_warnings(result)
    if warnings:
        for warning in warnings:
            st.warning(f"{warning}")


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

    best_appraisal = result.get("best_appraisal", {})
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
    quality = result.get("best_validation", {}).get("validation_summary", {}).get("quality_score")
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
    best_val_status = (
        result.get("best_validation", {}).get("validation_summary", {}).get("overall_status")
    )
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


def display_step_status(step_name: str, step_label: str, step_number: int):
    """
    Display status UI for a single pipeline step.

    Renders a Streamlit status container with:
    - Status icon (Pending / Running / Success / Failed / Skipped)
    - Elapsed time (for running/completed steps)
    - Error message (for failed steps)
    - Result summary (for successful steps)
    - Expandable details section (collapsed by default for success)

    Args:
        step_name: Step identifier ("classification", "extraction", "validation", "correction")
        step_label: Human-readable label ("Classification", "Extraction", etc.)
        step_number: Step number (1-6) for display

    Status Icons:
        - pending: (not yet started)
        - running: (currently executing)
        - success: (completed successfully)
        - failed: (critical error, pipeline stopped)
        - skipped: (step not selected or not needed)

    Container Expansion:
        - pending/skipped: Not expandable
        - running/failed: Auto-expanded to show progress/error
        - success: Collapsed by default, user can expand for details

    Example:
        >>> display_step_status("classification", "Classification", 1)
        # Renders: "Step 1: Classification  Completed in 8.3s"
        # Expandable content shows: Publication Type, DOI

    Note:
        Reads step status from st.session_state.step_status[step_name].
        Must call init_execution_state() before using this function.
    """
    step = st.session_state.step_status[step_name]
    status = step["status"]

    # Status icon mapping (emoji icons work in all contexts)
    icons = {
        "pending": "⏳",
        "running": "🔄",
        "success": "✅",
        "failed": "❌",
        "skipped": "⏭️",
    }

    icon = icons.get(status, "❓")
    label = f"Step {step_number}: {step_label}"

    # Calculate elapsed time (only for completed/failed steps)
    elapsed_text = ""
    if step["elapsed_seconds"] is not None:
        elapsed = step["elapsed_seconds"]
        elapsed_text = f" - {elapsed:.1f}s"

    # Status container configuration
    if status == "pending":
        # Not expandable for pending
        st.markdown(f"{icon} **{label}** - Not yet started")

    elif status == "running":
        # Auto-expanded for running (no elapsed time - it's static during execution)
        with st.status(f"{icon} {label} - Running", expanded=True):
            st.write(f"**Started:** {step['start_time'].strftime('%H:%M:%S')}")
            st.write("Executing pipeline step...")

    elif status == "success":
        # Collapsed by default for success, with result summary
        with st.status(f"{icon} {label} - Completed{elapsed_text}", expanded=False):
            # Show timing
            st.write(f"**Completed:** {step['end_time'].strftime('%H:%M:%S')}")

            # Show step-specific result summary
            result = step.get("result")
            if result:
                st.markdown("---")
                if step_name == STEP_CLASSIFICATION:
                    display_classification_result(result)
                elif step_name == STEP_EXTRACTION:
                    display_extraction_result(result)
                elif step_name == STEP_VALIDATION:
                    display_validation_result(result)
                elif step_name == STEP_CORRECTION:
                    display_correction_result(result)
                elif step_name == STEP_VALIDATION_CORRECTION:
                    display_validation_correction_result(result)
                elif step_name == STEP_APPRAISAL:
                    display_appraisal_result(result)
                elif step_name == STEP_REPORT_GENERATION:
                    display_report_result(result)

            # Show file path if available (non-verbose always shows this)
            file_path = step.get("file_path")
            if file_path:
                st.caption(f"**Saved:** `{file_path}`")

            # Show verbose logging details if enabled
            verbose_enabled = st.session_state.settings.get("verbose_logging", False)
            if verbose_enabled:
                verbose_data = step.get("verbose_data", {})
                if verbose_data or result:
                    st.markdown("---")
                    display_verbose_info(step_name, verbose_data, result)

    elif status == "failed":
        # Auto-expanded for errors with actionable guidance
        with st.status(f"{icon} {label} - Failed{elapsed_text}", expanded=True, state="error"):
            # Display error with guidance and troubleshooting steps
            display_error_with_guidance(step["error"], step_name, step)

            # Show timing
            st.markdown("---")
            if step["start_time"]:
                st.write(f"**Started:** {step['start_time'].strftime('%H:%M:%S')}")
            if step["end_time"]:
                st.write(f"**Failed:** {step['end_time'].strftime('%H:%M:%S')}")

    elif status == "skipped":
        # Simple text for skipped
        st.markdown(f"{icon} **{label}** - Skipped")


def display_report_artifacts():
    """
    Show download buttons for report artifacts (.tex/.pdf) if available.
    """
    if not st.session_state.pdf_path:
        return
    fm = PipelineFileManager(Path(st.session_state.pdf_path))
    render_dir = fm.tmp_dir / "render"
    tex_file = render_dir / "report.tex"
    pdf_file = render_dir / "report.pdf"
    md_file = render_dir / "report.md"
    root_md = fm.tmp_dir / f"{fm.identifier}-report.md"

    st.markdown("### Report Artifacts")
    has_any = False
    if tex_file.exists():
        has_any = True
        with open(tex_file, "rb") as f:
            st.download_button("Download LaTeX (.tex)", f, file_name=tex_file.name)
    if pdf_file.exists():
        has_any = True
        with open(pdf_file, "rb") as f:
            st.download_button("Download PDF", f, file_name=pdf_file.name)
    if root_md.exists():
        has_any = True
        with open(root_md, "rb") as f:
            st.download_button("Download Markdown (.md)", f, file_name=root_md.name)
    elif md_file.exists():
        has_any = True
        with open(md_file, "rb") as f:
            st.download_button("Download Markdown (.md)", f, file_name=md_file.name)
    if not has_any:
        st.info("No report artifacts available yet. Run report generation to produce .tex/.pdf.")


def display_podcast_artifacts():
    """
    Show download buttons for podcast artifacts (.json/.md) if available.
    """
    if not st.session_state.pdf_path:
        return
    fm = PipelineFileManager(Path(st.session_state.pdf_path))
    podcast_json = fm.tmp_dir / f"{fm.identifier}-podcast.json"
    podcast_md = fm.tmp_dir / f"{fm.identifier}-podcast.md"

    st.markdown("### Podcast Artifacts")
    has_any = False

    if podcast_json.exists():
        has_any = True
        with open(podcast_json, "rb") as f:
            st.download_button("Download Podcast JSON", f, file_name=podcast_json.name)

    if podcast_md.exists():
        has_any = True
        with open(podcast_md, "rb") as f:
            st.download_button("Download Podcast Script (.md)", f, file_name=podcast_md.name)

        # Also show transcript preview
        with open(podcast_md) as f:
            content = f.read()
        with st.expander("Preview Transcript"):
            st.markdown(content)

    # Copy transcript button (load from JSON for clean transcript only)
    if podcast_json.exists():
        import json

        with open(podcast_json) as f:
            podcast_data = json.load(f)
        transcript = podcast_data.get("transcript", "")
        if transcript:
            st.text_area(
                "Copy Transcript (for TTS)",
                transcript,
                height=150,
                key="podcast_transcript_copy",
            )

    if not has_any:
        st.info("No podcast artifacts available yet. Run podcast generation to produce script.")
