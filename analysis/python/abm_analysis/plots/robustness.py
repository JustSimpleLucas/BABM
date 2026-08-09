"""Seed-robustness figures: per-seed metric spread, convergence, and tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .common import (
    COLOUR_SEQUENCE,
    PLOT_TEMPLATE,
    REPORT_COLOURS,
    _empty_figure,
)


# Metric labels shared by the per-seed distribution and convergence figures.
_METRIC_TITLES = {
    "mean_log_return": "Mean Log Return",
    "log_return_std_dev": "Return Std. Dev.",
    "excess_kurtosis": "Excess Kurtosis",
    "max_drawdown": "Max Drawdown",
    "total_traded_volume": "Total Traded Volume",
}

DEFAULT_DISTRIBUTION_METRICS = (
    "mean_log_return",
    "log_return_std_dev",
    "excess_kurtosis",
    "max_drawdown",
)


def make_seed_metric_distribution_figure(
    per_seed_metrics: pd.DataFrame,
    *,
    metrics: tuple[str, ...] = DEFAULT_DISTRIBUTION_METRICS,
) -> go.Figure:
    """Show each metric's full cross-seed distribution as box plus points.

    The condition-level summary reports means and intervals; this figure keeps
    every seed visible so single influential draws (for example one seed with
    extreme kurtosis) can be spotted instead of being absorbed into an
    average. Expects one row per run with a ``seed`` column and metric
    columns.
    """

    if per_seed_metrics.empty or "seed" not in per_seed_metrics.columns:
        return _empty_figure("No per-seed metrics are available.")
    available_metrics = [
        metric for metric in metrics if metric in per_seed_metrics.columns
    ]
    if not available_metrics:
        return _empty_figure("No per-seed metric columns are available.")

    figure = make_subplots(
        rows=1,
        cols=len(available_metrics),
        subplot_titles=[_METRIC_TITLES.get(metric, metric) for metric in available_metrics],
        horizontal_spacing=0.06,
    )
    seeds = per_seed_metrics["seed"].astype(str)
    for column_index, metric in enumerate(available_metrics, start=1):
        values = pd.to_numeric(per_seed_metrics[metric], errors="coerce")
        colour = COLOUR_SEQUENCE[(column_index - 1) % len(COLOUR_SEQUENCE)]
        figure.add_trace(
            go.Box(
                y=values,
                name=_METRIC_TITLES.get(metric, metric),
                boxpoints="all",
                jitter=0.45,
                pointpos=0,
                marker=dict(color=colour, size=6),
                line=dict(color=colour),
                fillcolor="rgba(0,0,0,0)",
                text=[f"Seed {seed}" for seed in seeds],
                hovertemplate="%{text}<br>value = %{y:.5g}<extra></extra>",
                showlegend=False,
            ),
            row=1,
            col=column_index,
        )
        figure.update_xaxes(showticklabels=False, row=1, col=column_index)
    figure.update_layout(
        title="Per-Seed Metric Distributions",
        template=PLOT_TEMPLATE,
        height=460,
    )
    return figure


def make_seed_convergence_figure(convergence_table: pd.DataFrame) -> go.Figure:
    """Plot running ensemble means with 95% CI bands as seeds accumulate.

    The flattening of each band justifies the replication count: once the
    interval stops narrowing meaningfully, additional seeds no longer change
    the headline metrics (Law 2015, ch. 9).
    """

    if convergence_table.empty or "metric" not in convergence_table.columns:
        return _empty_figure("No seed-convergence results are available.")

    metrics = list(dict.fromkeys(convergence_table["metric"].astype(str)))
    figure = make_subplots(
        rows=len(metrics),
        cols=1,
        shared_xaxes=True,
        subplot_titles=[_METRIC_TITLES.get(metric, metric) for metric in metrics],
        vertical_spacing=0.36 / max(1, len(metrics)),
    )
    for row_index, metric in enumerate(metrics, start=1):
        group = convergence_table[convergence_table["metric"] == metric].sort_values(
            "seed_count"
        )
        seed_counts = pd.to_numeric(group["seed_count"], errors="coerce")
        means = pd.to_numeric(group["running_mean"], errors="coerce")
        half_widths = pd.to_numeric(group["ci95_half_width"], errors="coerce").fillna(0.0)
        colour = COLOUR_SEQUENCE[(row_index - 1) % len(COLOUR_SEQUENCE)]
        figure.add_trace(
            go.Scatter(
                x=pd.concat([seed_counts, seed_counts[::-1]]),
                y=pd.concat([means + half_widths, (means - half_widths)[::-1]]),
                fill="toself",
                fillcolor=_transparent(colour),
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
            ),
            row=row_index,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=seed_counts,
                y=means,
                mode="lines+markers",
                name=_METRIC_TITLES.get(metric, metric),
                line=dict(color=colour, width=1.8),
                marker=dict(size=5),
                showlegend=False,
                hovertemplate=(
                    "seeds = %{x}<br>running mean = %{y:.5g}<extra></extra>"
                ),
            ),
            row=row_index,
            col=1,
        )
    figure.update_layout(
        title="Ensemble-Mean Convergence Across Seeds (mean with 95% CI band)",
        template=PLOT_TEMPLATE,
        height=max(480, 240 * len(metrics)),
    )
    figure.update_xaxes(title_text="Number of accumulated seeds", row=len(metrics), col=1)
    figure.update_yaxes(title_text="Running mean")
    return figure


def make_adf_pvalue_figure(
    adf_table: pd.DataFrame,
    *,
    significance_level: float = 0.05,
) -> go.Figure:
    """Plot per-seed ADF p-values against the significance threshold.

    Points below the reference line reject the unit-root null; stationary log
    returns should place (nearly) every seed below it.
    """

    if adf_table.empty or "adf_p_value" not in adf_table.columns:
        return _empty_figure("No ADF stationarity results are available.")
    completed = adf_table[adf_table.get("status", "") == "completed"].copy()
    if completed.empty:
        return _empty_figure("No completed ADF tests are available.")

    completed["seed_label"] = [
        f"Seed {seed}" if not pd.isna(seed) else str(run_id)
        for seed, run_id in zip(completed.get("seed"), completed["run_id"], strict=True)
    ]
    p_values = pd.to_numeric(completed["adf_p_value"], errors="coerce")
    rejected = p_values < significance_level
    figure = go.Figure(
        go.Bar(
            x=completed["seed_label"],
            y=p_values,
            marker_color=[
                REPORT_COLOURS["teal"] if reject else REPORT_COLOURS["amber"]
                for reject in rejected
            ],
            hovertemplate="%{x}<br>ADF p-value = %{y:.4g}<extra></extra>",
        )
    )
    figure.add_hline(
        y=significance_level,
        line_dash="dash",
        line_color=REPORT_COLOURS["red"],
        annotation_text=f"significance level = {significance_level:g}",
        annotation_position="top right",
    )
    figure.update_layout(
        title="ADF Unit-Root p-Values by Seed",
        template=PLOT_TEMPLATE,
        height=460,
        xaxis_title="Seed",
        yaxis_title="ADF p-value",
    )
    return figure


def make_stylised_fact_success_figure(
    seed_summary: pd.DataFrame,
    *,
    pass_threshold: float = 0.80,
) -> go.Figure:
    """Plot the share of seeds reproducing each stylised fact.

    The dashed line marks the pass threshold used by the verdict table, so
    the figure and the verdicts stay visibly consistent.
    """

    success_columns = [
        ("fat_tail_success_rate", "Fat tails"),
        ("volatility_clustering_success_rate", "Volatility clustering"),
        ("weak_autocorrelation_success_rate", "Weak autocorrelation"),
    ]
    if seed_summary.empty:
        return _empty_figure("No seed-robustness summary is available.")
    available = [
        (column, label)
        for column, label in success_columns
        if column in seed_summary.columns
    ]
    if not available:
        return _empty_figure("No stylised-fact success rates are available.")

    figure = go.Figure()
    multiple_conditions = len(seed_summary) > 1
    for row_number, (_, summary_row) in enumerate(seed_summary.iterrows(), start=1):
        rates = [
            pd.to_numeric(pd.Series([summary_row.get(column)]), errors="coerce").iloc[0]
            for column, _ in available
        ]
        figure.add_trace(
            go.Bar(
                x=[label for _, label in available],
                y=rates,
                name=f"Condition {row_number}" if multiple_conditions else "Success rate",
                marker_color=COLOUR_SEQUENCE[(row_number - 1) % len(COLOUR_SEQUENCE)],
                hovertemplate="%{x}<br>success rate = %{y:.0%}<extra></extra>",
                showlegend=multiple_conditions,
            )
        )
    figure.add_hline(
        y=pass_threshold,
        line_dash="dash",
        line_color=REPORT_COLOURS["red"],
        annotation_text=f"pass threshold = {pass_threshold:.0%}",
        annotation_position="top right",
    )
    figure.update_layout(
        title="Stylised-Fact Reproducibility Across Seeds",
        template=PLOT_TEMPLATE,
        height=460,
        yaxis=dict(title="Share of seeds", range=[0, 1.05], tickformat=".0%"),
        barmode="group",
    )
    return figure


def _transparent(hex_colour: str) -> str:
    """Convert a #rrggbb colour to a low-alpha rgba string for CI bands."""

    stripped = hex_colour.lstrip("#")
    red, green, blue = (int(stripped[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({red},{green},{blue},0.16)"
