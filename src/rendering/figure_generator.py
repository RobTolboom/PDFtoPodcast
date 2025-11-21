"""
Figure generation utilities for report rendering (Phase 5).

Current support: rob_traffic_light (basic placeholder), forest_basic (minimal).
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
    except Exception as e:
        raise FigureGenerationError(
            "matplotlib is required for figure generation (install matplotlib)"
        ) from e
    return plt


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _generate_rob_traffic_light(data: dict[str, Any], path: Path) -> None:
    plt = _import_matplotlib()
    fig, ax = plt.subplots(figsize=(4, 2))
    domains = data.get("domains", ["bias_domain_1", "bias_domain_2"])
    judgments = data.get("judgements", ["Low", "Some concerns"])
    colors = {"Low": "green", "Some concerns": "orange", "High": "red"}
    y = range(len(domains))
    ax.barh(y, [1] * len(domains), color=[colors.get(j, "grey") for j in judgments])
    ax.set_yticks(y)
    ax.set_yticklabels(domains)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("Risk of Bias (placeholder)")
    fig.tight_layout()
    fig.savefig(path, dpi=300)
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
    fig.savefig(path, dpi=300)
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
    else:
        raise FigureGenerationError(f"Unsupported figure_kind: {figure_kind}")

    return fig_path
