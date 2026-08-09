"""Stress-regime and seed-robustness figures."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from abm_analysis.data import load_step_timeseries
from abm_analysis.stress import annotate_stress_regimes

from .common import (
    COLOUR_SEQUENCE,
    PLOT_TEMPLATE,
    REPORT_COLOURS,
    _analysis_phase,
    _condition_labels,
    _empty_figure,
    _run_label,
    _time_axis,
)

def make_seed_robustness_figure(seed_summary: pd.DataFrame) -> go.Figure:
    """Plot condition-level means and confidence intervals across seeds."""

    if seed_summary.empty:
        return _empty_figure("No seed-robustness summary is available.")
    metrics = [
        ("log_return_std_dev", "Return Std. Dev."),
        ("excess_kurtosis", "Excess Kurtosis"),
        ("max_drawdown", "Max Drawdown"),
    ]
    available_metrics = [
        (metric, title)
        for metric, title in metrics
        if f"{metric}_mean" in seed_summary.columns
    ]
    if not available_metrics:
        return _empty_figure("No seed-robustness metrics are available.")

    figure = make_subplots(
        rows=len(available_metrics),
        cols=1,
        shared_xaxes=True,
        subplot_titles=[title for _, title in available_metrics],
        vertical_spacing=0.08,
    )
    labels = _condition_labels(seed_summary)
    for row_index, (metric, title) in enumerate(available_metrics, start=1):
        mean_values = pd.to_numeric(seed_summary[f"{metric}_mean"], errors="coerce")
        lower = pd.to_numeric(seed_summary.get(f"{metric}_ci95_lower"), errors="coerce")
        upper = pd.to_numeric(seed_summary.get(f"{metric}_ci95_upper"), errors="coerce")
        figure.add_trace(
            go.Bar(
                x=labels,
                y=mean_values,
                name=title,
                marker_color=COLOUR_SEQUENCE[(row_index - 1) % len(COLOUR_SEQUENCE)],
                error_y=dict(
                    type="data",
                    array=(upper - mean_values).clip(lower=0),
                    arrayminus=(mean_values - lower).clip(lower=0),
                    visible=True,
                ),
                showlegend=False,
            ),
            row=row_index,
            col=1,
        )
    figure.update_layout(
        title="Seed Robustness by Experimental Condition",
        template=PLOT_TEMPLATE,
        height=max(420, 300 * len(available_metrics)),
    )
    figure.update_xaxes(title_text="Condition", tickangle=35, row=len(available_metrics), col=1)
    figure.update_yaxes(title_text="Mean with 95% CI")
    return figure

def make_stress_regime_summary_figure(stress_diagnostics: pd.DataFrame) -> go.Figure:
    """Compare normal and stress regimes across simulations and benchmarks."""

    if stress_diagnostics.empty:
        return _empty_figure("No stress-regime diagnostics are available.")
    data = stress_diagnostics[stress_diagnostics["regime"].isin(["normal", "stress"])].copy()
    if data.empty:
        return _empty_figure("No normal/stress regime rows are available.")
    data["series_label"] = data["source_type"].astype(str) + ": " + data["series_id"].astype(str)
    metrics = [
        ("log_return_std_dev", "Return Std. Dev."),
        ("max_drawdown", "Max Drawdown"),
        ("mean_rolling_volatility", "Rolling Volatility"),
    ]
    available_metrics = [(column, title) for column, title in metrics if column in data.columns]
    figure = make_subplots(
        rows=len(available_metrics),
        cols=1,
        shared_xaxes=True,
        subplot_titles=[title for _, title in available_metrics],
        vertical_spacing=0.08,
    )
    for row_index, (column, title) in enumerate(available_metrics, start=1):
        for regime_index, (regime, subset) in enumerate(data.groupby("regime")):
            figure.add_trace(
                go.Bar(
                    x=subset["series_label"],
                    y=pd.to_numeric(subset[column], errors="coerce"),
                    name=str(regime),
                    legendgroup=str(regime),
                    marker_color=COLOUR_SEQUENCE[regime_index % len(COLOUR_SEQUENCE)],
                    showlegend=row_index == 1,
                ),
                row=row_index,
                col=1,
            )
    if not figure.data:
        return _empty_figure("No finite stress-regime metrics are available.")
    figure.update_layout(
        title="Stress-Regime Comparison",
        template=PLOT_TEMPLATE,
        height=max(420, 300 * len(available_metrics)),
        barmode="group",
        legend_title="Regime",
    )
    figure.update_xaxes(title_text="Series", tickangle=35, row=len(available_metrics), col=1)
    return figure

def make_stress_indicator_figure(
    experiment_dir: Path,
    run_ids: list[str],
    benchmarks: dict[str, BenchmarkSeries] | None = None,
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot price, drawdown, volatility, and volume with stress markers."""

    series = []
    for run_id in run_ids[:3]:
        time_series = load_step_timeseries(experiment_dir / run_id, price_column=price_column)
        time_series = _analysis_phase(time_series, phase)
        try:
            annotated = annotate_stress_regimes(time_series, price_column=price_column)
        except KeyError:
            continue
        series.append((_run_label(run_id, run_labels), "simulation", annotated, price_column))
    for benchmark_id, benchmark in (benchmarks or {}).items():
        annotated = annotate_stress_regimes(benchmark.data, price_column="market_price")
        series.append((benchmark_id, "benchmark", annotated, "market_price"))

    if not series:
        return _empty_figure("No series are available for stress-period panels.")
    figure = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        subplot_titles=[
            "Price Path",
            "Drawdown",
            "Rolling Volatility",
            "Volume or Traded Volume",
        ],
        vertical_spacing=0.07,
    )
    for index, (label, source_type, data, series_price_column) in enumerate(series):
        colour = COLOUR_SEQUENCE[index % len(COLOUR_SEQUENCE)]
        x_values = _time_axis(data)
        price_values = pd.to_numeric(data[series_price_column], errors="coerce")
        stress_points = data[data["stress_regime"]]
        stress_x = _time_axis(stress_points)
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=price_values,
                mode="lines",
                name=f"{label} {source_type}",
                legendgroup=label,
                line=dict(color=colour, width=1.3),
            ),
            row=1,
            col=1,
        )
        if not stress_points.empty:
            figure.add_trace(
                go.Scatter(
                    x=stress_x,
                    y=pd.to_numeric(stress_points[series_price_column], errors="coerce"),
                    mode="markers",
                    name=f"{label} stress",
                    legendgroup=label,
                    showlegend=False,
                    marker=dict(color=colour, size=5, symbol="x"),
                ),
                row=1,
                col=1,
            )
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=pd.to_numeric(data["drawdown"], errors="coerce"),
                mode="lines",
                name=label,
                legendgroup=label,
                showlegend=False,
                line=dict(color=colour, width=1.2),
            ),
            row=2,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=pd.to_numeric(data["rolling_volatility"], errors="coerce"),
                mode="lines",
                name=label,
                legendgroup=label,
                showlegend=False,
                line=dict(color=colour, width=1.2),
            ),
            row=3,
            col=1,
        )
        volume_column = "traded_volume" if "traded_volume" in data.columns else None
        if volume_column is not None:
            figure.add_trace(
                go.Scatter(
                    x=x_values,
                    y=pd.to_numeric(data[volume_column], errors="coerce"),
                    mode="lines",
                    name=label,
                    legendgroup=label,
                    showlegend=False,
                    line=dict(color=colour, width=1.0),
                ),
                row=4,
                col=1,
            )
    figure.update_layout(
        title="Stress-Period Panels",
        template=PLOT_TEMPLATE,
        height=940,
        legend_title="Series",
    )
    figure.update_xaxes(title_text="Observation", row=4, col=1)
    figure.update_yaxes(title_text="Price", row=1, col=1)
    figure.update_yaxes(title_text="Drawdown", row=2, col=1)
    figure.update_yaxes(title_text="Volatility", row=3, col=1)
    figure.update_yaxes(title_text="Volume", row=4, col=1)
    return figure
