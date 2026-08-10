"""Market-level price, volume, and return-path figures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from abm_analysis.archive.data import load_step_timeseries

from .common import (
    COLOUR_SEQUENCE,
    PLOT_TEMPLATE,
    REPORT_COLOURS,
    _analysis_phase,
    _empty_figure,
    _run_label,
    _time_axis,
)

def make_metric_comparison_figure(
    runs_index: pd.DataFrame,
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Compare key experiment-level metrics across runs."""

    metrics = [
        ("max_drawdown", "Max Drawdown"),
        ("mean_allocative_efficiency", "Mean Allocative Efficiency"),
        ("excess_kurtosis", "Excess Kurtosis"),
        ("log_return_std_dev", "Return Std. Dev."),
        ("total_traded_volume", "Total Traded Volume"),
    ]
    available_metrics = [
        (column, title)
        for column, title in metrics
        if column in runs_index.columns
    ]
    if not available_metrics:
        return _empty_figure("No summary metrics are available.")

    column_count = 2
    row_count = (len(available_metrics) + column_count - 1) // column_count
    figure = make_subplots(
        rows=row_count,
        cols=2,
        subplot_titles=[title for _, title in available_metrics],
    )
    run_ids = runs_index["run_id"].astype(str)
    display_labels = [_run_label(run_id, run_labels) for run_id in run_ids]
    for index, (column, title) in enumerate(available_metrics, start=1):
        row = ((index - 1) // column_count) + 1
        col = ((index - 1) % column_count) + 1
        figure.add_trace(
            go.Bar(
                x=display_labels,
                y=pd.to_numeric(runs_index[column], errors="coerce"),
                name=title,
                marker_color=COLOUR_SEQUENCE[(index - 1) % len(COLOUR_SEQUENCE)],
                showlegend=False,
            ),
            row=row,
            col=col,
        )
        if column == "mean_allocative_efficiency":
            figure.update_yaxes(range=[0, 1], row=row, col=col)
    figure.update_layout(
        title="Run Metric Comparison",
        template=PLOT_TEMPLATE,
        height=max(520, 330 * row_count),
        margin=dict(l=40, r=20, t=70, b=120),
    )
    figure.update_xaxes(tickangle=45)
    return figure

def make_price_timeseries_figure(
    experiment_dir: Path,
    run_ids: list[str],
    *,
    price_column: str = "market_price",
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot market and fundamental prices for selected runs."""

    figure = go.Figure()
    for index, run_id in enumerate(run_ids):
        run_dir = experiment_dir / run_id
        time_series = load_step_timeseries(run_dir, price_column=price_column)
        x_values = _time_axis(time_series)
        colour = COLOUR_SEQUENCE[index % len(COLOUR_SEQUENCE)]
        display_label = _run_label(run_id, run_labels)
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=time_series[price_column],
                mode="lines",
                name=f"{display_label} market",
                line=dict(color=colour, width=1.6),
            )
        )
        if index == 0 and "fundamental_price" in time_series.columns:
            figure.add_trace(
                go.Scatter(
                    x=x_values,
                    y=time_series["fundamental_price"],
                    mode="lines",
                    name=f"{display_label} fundamental",
                    line=dict(color=REPORT_COLOURS["graphite"], width=1.3, dash="dash"),
                )
            )

    if not figure.data:
        return _empty_figure("No price time-series data are available.")
    figure.update_layout(
        title="Market Price Paths",
        template=PLOT_TEMPLATE,
        height=520,
        xaxis_title="Simulation Row",
        yaxis_title="Price",
        legend_title="Run",
    )
    return figure

def make_trade_volume_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot traded volume over time for selected runs."""

    figure = go.Figure()
    for index, run_id in enumerate(run_ids):
        time_series = load_step_timeseries(experiment_dir / run_id)
        if "traded_volume" not in time_series.columns:
            continue
        figure.add_trace(
            go.Scatter(
                x=_time_axis(time_series),
                y=pd.to_numeric(time_series["traded_volume"], errors="coerce").fillna(0),
                mode="lines",
                name=_run_label(run_id, run_labels),
                line=dict(color=COLOUR_SEQUENCE[index % len(COLOUR_SEQUENCE)], width=1.2),
            )
        )
    if not figure.data:
        return _empty_figure("No traded-volume series are available.")
    figure.update_layout(
        title="Trading Volume Paths",
        template=PLOT_TEMPLATE,
        height=420,
        xaxis_title="Simulation Row",
        yaxis_title="Traded Volume",
    )
    return figure

def make_market_fundamental_log_return_figure(
    experiment_dir: Path,
    run_ids: list[str],
    *,
    price_column: str = "market_price",
    phase: str = "simulation",
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot market-price and fundamental-value log returns over time.

    The market return is the realised transaction-price movement generated by
    the agents and market-clearing mechanism. The fundamental return is the
    benchmark movement implied by the model's latent fundamental value. Showing
    both series makes crisis-period dislocations visible: large market-return
    shocks relative to the fundamental benchmark indicate endogenous market
    stress rather than a movement in the model's reference value.
    """

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=[
            "Market Log Returns",
            "Fundamental-Value Log Returns",
        ],
        vertical_spacing=0.09,
    )
    for index, run_id in enumerate(run_ids):
        time_series = load_step_timeseries(experiment_dir / run_id, price_column=price_column)
        time_series = _analysis_phase(time_series, phase)
        if "computed_log_return" not in time_series.columns:
            continue

        colour = COLOUR_SEQUENCE[index % len(COLOUR_SEQUENCE)]
        x_values = _time_axis(time_series)
        display_label = _run_label(run_id, run_labels)
        market_returns = pd.to_numeric(time_series["computed_log_return"], errors="coerce")
        if not market_returns.dropna().empty:
            figure.add_trace(
                go.Scatter(
                    x=x_values,
                    y=market_returns,
                    mode="lines",
                    name=f"{display_label} market",
                    legendgroup=display_label,
                    line=dict(color=colour, width=1.2),
                ),
                row=1,
                col=1,
            ),

        if "computed_fundamental_log_return" not in time_series.columns:
            continue
        fundamental_returns = pd.to_numeric(
            time_series["computed_fundamental_log_return"],
            errors="coerce",
        )
        if fundamental_returns.dropna().empty:
            continue
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=fundamental_returns,
                mode="lines",
                name=f"{display_label} fundamental",
                legendgroup=display_label,
                showlegend=True,
                line=dict(color=colour, width=1.1, dash="dash"),
            ),
            row=2,
            col=1,
        )

    if not figure.data:
        return _empty_figure("No market or fundamental log-return series are available.")
    figure.update_layout(
        title="Market and Fundamental Log Returns",
        template=PLOT_TEMPLATE,
        height=620,
        legend_title="Run",
    )
    figure.update_xaxes(title_text="Simulation Step", row=2, col=1)
    figure.update_yaxes(title_text="Log Return", zeroline=True)
    return figure
