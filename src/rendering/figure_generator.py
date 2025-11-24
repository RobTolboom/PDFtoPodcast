"""
Figure generation utilities for report rendering (Phase 5).

Current support:
- rob_traffic_light: Risk of Bias traffic light visualization
- forest: Basic forest plot with confidence intervals
- prisma: PRISMA 2020 flow diagram for systematic reviews
- consort: CONSORT flow diagram for clinical trials

Figures are saved as PNG (dpi=300) using matplotlib (Agg backend).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class FigureGenerationError(RuntimeError):
    """Raised when a figure cannot be generated."""


def _import_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError as e:
        raise FigureGenerationError(
            "matplotlib is required for figure generation (install matplotlib)"
        ) from e
    except Exception as e:
        raise FigureGenerationError(f"Failed to import matplotlib: {e}") from e
    return plt


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _generate_rob_traffic_light(data: dict[str, Any], path: Path) -> None:
    plt = _import_matplotlib()
    fig, ax = plt.subplots(figsize=(4.5, 2.2))
    domains = data.get("domains", [])
    judgments = data.get("judgements", [])

    # Normalize inputs (allow dict entries or raw strings)
    if domains and not judgments and isinstance(domains[0], dict):
        judgments = [d.get("judgement", "") for d in domains]
        domains = [d.get("domain", "") for d in domains]

    if not domains:
        domains = ["Bias domain 1", "Bias domain 2"]
    if not judgments:
        judgments = ["Low risk"] * len(domains)

    color_map = {
        "low": "green",
        "low risk": "green",
        "some concerns": "orange",
        "high": "red",
        "high risk": "red",
    }
    pretty_domain = {
        "randomization_process": "Randomization process",
        "deviations_from_intended_interventions": "Deviations from intended interventions",
        "missing_outcome_data": "Missing outcome data",
        "measurement_of_outcome": "Measurement of outcome",
        "selection_of_reported_result": "Selection of reported result",
    }

    def _clean_domain(name: str) -> str:
        return pretty_domain.get(name, name.replace("_", " ").strip().capitalize())

    domains = [_clean_domain(d) for d in domains]
    y = range(len(domains))
    colors = [color_map.get(j.lower(), "grey") if isinstance(j, str) else "grey" for j in judgments]
    ax.barh(y, [1] * len(domains), color=colors)
    ax.set_yticks(y)
    ax.set_yticklabels(domains)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("Risk of Bias (RoB 2)", fontsize=10, pad=8)
    fig.tight_layout()
    ax.set_title("Risk of Bias (RoB 2)", fontsize=10, pad=8)
    fig.tight_layout()
    try:
        fig.savefig(path, dpi=300)
    finally:
        plt.close(fig)


def _generate_forest_basic(data: dict[str, Any], path: Path) -> None:
    plt = _import_matplotlib()
    outcomes = data.get("outcomes", [{"name": "Outcome 1", "effect": -0.5, "ci": (-1.0, 0.0)}])
    fig, ax = plt.subplots(figsize=(4, 3))
    y = range(len(outcomes))
    effects = [o.get("effect", 0) for o in outcomes]
    cis = [o.get("ci", (e, e)) for e, o in zip(effects, outcomes, strict=True)]
    ax.errorbar(
        effects,
        y,
        xerr=[
            [e - ci[0] for e, ci in zip(effects, cis, strict=True)],
            [ci[1] - e for e, ci in zip(effects, cis, strict=True)],
        ],
        fmt="o",
        color="black",
    )
    ax.axvline(0, color="grey", linestyle="--", linewidth=1)
    ax.set_yticks(list(y))
    ax.set_yticklabels([o.get("name", "") for o in outcomes])
    ax.set_xlabel("Effect size")
    ax.set_title("Forest plot (placeholder)")
    fig.tight_layout()
    ax.set_title("Forest plot (placeholder)")
    fig.tight_layout()
    try:
        fig.savefig(path, dpi=300)
    finally:
        plt.close(fig)


def _draw_flow_box(ax, x: float, y: float, width: float, height: float, text: str) -> None:
    """Draw a rounded box with centered text for flow diagrams."""
    from matplotlib.patches import FancyBboxPatch

    box = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.1",
        facecolor="white",
        edgecolor="black",
        linewidth=1.5,
    )
    ax.add_patch(box)
    ax.text(x, y, text, ha="center", va="center", fontsize=8, wrap=True)


def _draw_flow_arrow(ax, start: tuple, end: tuple) -> None:
    """Draw an arrow between two points for flow diagrams."""
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={"arrowstyle": "->", "color": "black", "lw": 1.2},
    )


def _generate_prisma_flow(data: dict[str, Any], path: Path) -> None:
    """Generate PRISMA 2020 flow diagram for systematic reviews."""
    plt = _import_matplotlib()

    # Extract data with defaults
    records_identified = data.get("records_identified", 0)
    records_after_duplicates = data.get("records_after_duplicates", records_identified)
    records_screened = data.get("records_screened", records_after_duplicates)
    records_excluded = data.get("records_excluded", 0)
    full_text_assessed = data.get("full_text_assessed", records_screened - records_excluded)
    full_text_excluded = data.get("full_text_excluded", 0)
    studies_included = data.get("studies_included", full_text_assessed - full_text_excluded)
    reasons_excluded = data.get("reasons_excluded", [])

    # Create figure with appropriate size
    fig, ax = plt.subplots(figsize=(8, 10))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")
    ax.set_aspect("equal")

    # Box dimensions
    box_w, box_h = 3.5, 1.0

    # Phase 1: Identification
    _draw_flow_box(ax, 5, 11, box_w, box_h, f"Records identified\n(n = {records_identified})")

    # Arrow to screening
    _draw_flow_arrow(ax, (5, 10.5), (5, 9.5))

    # Phase 2: Screening - duplicates removed
    duplicates_removed = records_identified - records_after_duplicates
    _draw_flow_box(
        ax, 5, 9, box_w, box_h, f"After duplicates removed\n(n = {records_after_duplicates})"
    )

    # Side box for duplicates (if any)
    if duplicates_removed > 0:
        _draw_flow_box(ax, 8.5, 9, 2.5, 0.8, f"Duplicates\n(n = {duplicates_removed})")
        _draw_flow_arrow(ax, (6.75, 9), (7.25, 9))

    # Arrow to screening
    _draw_flow_arrow(ax, (5, 8.5), (5, 7.5))

    # Phase 2: Screening - records screened
    _draw_flow_box(ax, 5, 7, box_w, box_h, f"Records screened\n(n = {records_screened})")

    # Side box for excluded
    _draw_flow_box(ax, 8.5, 7, 2.5, 0.8, f"Excluded\n(n = {records_excluded})")
    _draw_flow_arrow(ax, (6.75, 7), (7.25, 7))

    # Arrow to eligibility
    _draw_flow_arrow(ax, (5, 6.5), (5, 5.5))

    # Phase 3: Eligibility
    _draw_flow_box(ax, 5, 5, box_w, box_h, f"Full-text assessed\n(n = {full_text_assessed})")

    # Side box for full-text excluded with reasons
    reasons_text = f"Excluded (n = {full_text_excluded})"
    if reasons_excluded:
        reasons_str = "\n".join(reasons_excluded[:3])  # Limit to 3 reasons
        if len(reasons_excluded) > 3:
            reasons_str += f"\n... +{len(reasons_excluded) - 3} more"
        reasons_text = f"Excluded (n = {full_text_excluded}):\n{reasons_str}"

    _draw_flow_box(ax, 8.5, 5, 2.8, 1.5, reasons_text)
    _draw_flow_arrow(ax, (6.75, 5), (7.1, 5))

    # Arrow to included
    _draw_flow_arrow(ax, (5, 4.5), (5, 3.5))

    # Phase 4: Included
    _draw_flow_box(ax, 5, 3, box_w, box_h, f"Studies included\n(n = {studies_included})")

    # Title
    ax.text(
        5, 11.8, "PRISMA Flow Diagram", ha="center", va="center", fontsize=12, fontweight="bold"
    )

    fig.tight_layout()
    fig.tight_layout()
    try:
        fig.savefig(path, dpi=300, bbox_inches="tight")
    finally:
        plt.close(fig)


def _generate_consort_flow(data: dict[str, Any], path: Path) -> None:
    """Generate CONSORT flow diagram for clinical trials."""
    plt = _import_matplotlib()

    # Extract data with defaults
    n_screened = data.get("n_screened", 0)
    n_excluded_screening = data.get("n_excluded_screening", 0)
    n_randomised = data.get("n_randomised", n_screened - n_excluded_screening)
    exclusion_reasons = data.get("exclusion_reasons", [])

    # Arms data (default to 2 arms if not provided)
    arms = data.get(
        "arms",
        [
            {
                "label": "Intervention",
                "n_assigned": n_randomised // 2,
                "n_analysed": n_randomised // 2,
            },
            {"label": "Control", "n_assigned": n_randomised // 2, "n_analysed": n_randomised // 2},
        ],
    )
    n_arms = len(arms)

    # Create figure
    fig_width = max(10, 4 * n_arms)
    fig, ax = plt.subplots(figsize=(fig_width, 12))
    ax.set_xlim(0, fig_width)
    ax.set_ylim(0, 14)
    ax.axis("off")

    center_x = fig_width / 2
    box_w, box_h = 3.0, 1.0

    # Phase 1: Enrollment - Assessed for eligibility
    _draw_flow_box(ax, center_x, 13, box_w, box_h, f"Assessed for eligibility\n(n = {n_screened})")

    # Side box for excluded at screening
    if n_excluded_screening > 0 or exclusion_reasons:
        excl_text = f"Excluded (n = {n_excluded_screening})"
        if exclusion_reasons:
            reasons_str = "\n".join(exclusion_reasons[:2])
            excl_text = f"Excluded (n = {n_excluded_screening}):\n{reasons_str}"
        _draw_flow_box(ax, center_x + 3.5, 13, 2.8, 1.2, excl_text)
        _draw_flow_arrow(ax, (center_x + 1.5, 13), (center_x + 2.1, 13))

    # Arrow to randomization
    _draw_flow_arrow(ax, (center_x, 12.5), (center_x, 11.5))

    # Phase 2: Allocation - Randomized
    _draw_flow_box(ax, center_x, 11, box_w, box_h, f"Randomised\n(n = {n_randomised})")

    # Calculate arm positions
    arm_spacing = fig_width / (n_arms + 1)
    arm_positions = [(i + 1) * arm_spacing for i in range(n_arms)]

    # Draw branching arrows to arms
    for arm_x in arm_positions:
        _draw_flow_arrow(ax, (center_x, 10.5), (arm_x, 9.5))

    # Phase 2: Allocation per arm
    for i, (arm, arm_x) in enumerate(zip(arms, arm_positions, strict=True)):
        label = arm.get("label", f"Arm {i + 1}")
        n_assigned = arm.get("n_assigned", 0)
        _draw_flow_box(ax, arm_x, 9, box_w, box_h, f"Allocated to {label}\n(n = {n_assigned})")

        # Arrow to follow-up
        _draw_flow_arrow(ax, (arm_x, 8.5), (arm_x, 7.5))

        # Phase 3: Follow-up
        lost = arm.get("lost_to_followup", 0)
        discontinued = arm.get("discontinued", 0)
        followup_text = f"Follow-up\nLost: {lost}, Discontinued: {discontinued}"
        _draw_flow_box(ax, arm_x, 7, box_w, box_h, followup_text)

        # Arrow to analysis
        _draw_flow_arrow(ax, (arm_x, 6.5), (arm_x, 5.5))

        # Phase 4: Analysis
        n_analysed = arm.get("n_analysed", n_assigned - lost - discontinued)
        _draw_flow_box(ax, arm_x, 5, box_w, box_h, f"Analysed\n(n = {n_analysed})")

    # Phase labels on left side
    ax.text(
        0.3, 13, "Enrollment", ha="left", va="center", fontsize=10, fontweight="bold", rotation=90
    )
    ax.text(
        0.3, 11, "Allocation", ha="left", va="center", fontsize=10, fontweight="bold", rotation=90
    )
    ax.text(
        0.3, 7, "Follow-up", ha="left", va="center", fontsize=10, fontweight="bold", rotation=90
    )
    ax.text(0.3, 5, "Analysis", ha="left", va="center", fontsize=10, fontweight="bold", rotation=90)

    # Title
    ax.text(
        center_x,
        13.8,
        "CONSORT Flow Diagram",
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
    )

    fig.tight_layout()
    fig.tight_layout()
    try:
        fig.savefig(path, dpi=300, bbox_inches="tight")
    finally:
        plt.close(fig)


def generate_figure(block: dict[str, Any], output_dir: Path) -> Path:
    """
    Generate a figure for a figure block. Returns the path to the PNG.
    """
    figure_kind = block.get("figure_kind")
    _ensure_dir(output_dir)
    filename = f"{block.get('label', 'figure')}.png"
    fig_path = output_dir / filename

    if figure_kind == "rob_traffic_light":
        _generate_rob_traffic_light(block.get("data", {}), fig_path)
    elif figure_kind == "forest":
        _generate_forest_basic(block.get("data", {}), fig_path)
    elif figure_kind == "prisma":
        _generate_prisma_flow(block.get("data", {}), fig_path)
    elif figure_kind == "consort":
        _generate_consort_flow(block.get("data", {}), fig_path)
    else:
        raise FigureGenerationError(f"Unsupported figure_kind: {figure_kind}")

    return fig_path
