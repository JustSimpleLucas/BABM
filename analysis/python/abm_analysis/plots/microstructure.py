"""Limit-order-book and order-flow microstructure figures."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from abm_analysis.archive.data import load_step_timeseries

from .common import (
    COLOUR_SEQUENCE,
    PLOT_TEMPLATE,
    REPORT_COLOURS,
    _empty_figure,
    _run_label,
    _simulation_phase,
    _time_axis,
)

def make_microstructure_quotes_figure(
    experiment_dir: Path,
    run_ids: list[str],
    *,
    run_labels: dict[str, str] | None = None,
    max_runs: int = 3,
) -> go.Figure:
    """Plot best quotes, midquote, market price, and last trade price.

    The figure is intentionally limited to a small number of runs because bid,
    ask, midquote, and last-trade series are dense microstructure objects. For
    a single-run report this gives a direct visual audit of how the persistent
    book forms the official transaction-price path.
    """

    selected_run_ids = run_ids[:max_runs]
    rows: list[tuple[str, pd.DataFrame]] = []
    for run_id in selected_run_ids:
        time_series = _simulation_phase(load_step_timeseries(experiment_dir / run_id))
        required_columns = {
            "market_price",
            "best_bid",
            "best_ask",
            "mid_quote",
            "last_trade_price",
        }
        if required_columns.issubset(time_series.columns):
            rows.append((run_id, time_series))

    if not rows:
        return _empty_figure("No LOB quote diagnostics are available.")

    figure = make_subplots(
        rows=len(rows),
        cols=1,
        shared_xaxes=True,
        subplot_titles=[_run_label(run_id, run_labels) for run_id, _ in rows],
        vertical_spacing=0.08,
    )
    quote_styles = [
        ("market_price", "Market price", REPORT_COLOURS["graphite"], "solid", "lines"),
        ("best_bid", "Best bid", REPORT_COLOURS["green"], "solid", "lines"),
        ("best_ask", "Best ask", REPORT_COLOURS["red"], "solid", "lines"),
        ("mid_quote", "Midquote", REPORT_COLOURS["blue"], "dash", "lines"),
        ("last_trade_price", "Last trade", REPORT_COLOURS["amber"], "dot", "markers"),
    ]
    for row_index, (run_id, time_series) in enumerate(rows, start=1):
        x_values = _time_axis(time_series)
        for column, label, colour, dash, mode in quote_styles:
            values = pd.to_numeric(time_series[column], errors="coerce")
            visible_values = values.where(values > 0)
            if visible_values.notna().sum() == 0:
                continue
            figure.add_trace(
                go.Scatter(
                    x=x_values,
                    y=visible_values,
                    mode=mode,
                    name=label,
                    legendgroup=label,
                    showlegend=row_index == 1,
                    line=dict(color=colour, width=1.4, dash=dash),
                    marker=dict(color=colour, size=4),
                ),
                row=row_index,
                col=1,
            )

    figure.update_layout(
        title="Limit Order Book Quotes and Transaction Prices",
        template=PLOT_TEMPLATE,
        height=max(420, 330 * len(rows)),
        legend_title="Series",
    )
    figure.update_xaxes(title_text="Simulation Step", row=len(rows), col=1)
    figure.update_yaxes(title_text="Price")
    return figure

def make_microstructure_liquidity_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot spread, visible depth, and depth imbalance across selected runs."""

    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        subplot_titles=[
            "Bid-Ask Spread",
            "Visible Book Depth",
            "Depth Imbalance",
        ],
        vertical_spacing=0.08,
    )
    for index, run_id in enumerate(run_ids):
        time_series = _simulation_phase(load_step_timeseries(experiment_dir / run_id))
        required_columns = {"bid_ask_spread", "bid_depth", "ask_depth"}
        if not required_columns.issubset(time_series.columns):
            continue

        colour = COLOUR_SEQUENCE[index % len(COLOUR_SEQUENCE)]
        x_values = _time_axis(time_series)
        display_label = _run_label(run_id, run_labels)
        bid_depth = pd.to_numeric(time_series["bid_depth"], errors="coerce").fillna(0.0)
        ask_depth = pd.to_numeric(time_series["ask_depth"], errors="coerce").fillna(0.0)
        total_depth = bid_depth + ask_depth
        depth_imbalance = (bid_depth - ask_depth) / total_depth.replace(0.0, np.nan)

        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=pd.to_numeric(time_series["bid_ask_spread"], errors="coerce"),
                mode="lines",
                name=display_label,
                legendgroup=display_label,
                line=dict(color=colour, width=1.4),
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=total_depth,
                mode="lines",
                name=display_label,
                legendgroup=display_label,
                showlegend=False,
                line=dict(color=colour, width=1.4),
            ),
            row=2,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=depth_imbalance,
                mode="lines",
                name=display_label,
                legendgroup=display_label,
                showlegend=False,
                line=dict(color=colour, width=1.4),
            ),
            row=3,
            col=1,
        )

    if not figure.data:
        return _empty_figure("No LOB liquidity diagnostics are available.")
    figure.update_layout(
        title="Limit Order Book Liquidity",
        template=PLOT_TEMPLATE,
        height=780,
        legend_title="Run",
    )
    figure.update_xaxes(title_text="Simulation Step", row=3, col=1)
    figure.update_yaxes(title_text="Spread", row=1, col=1)
    figure.update_yaxes(title_text="Depth", row=2, col=1)
    figure.update_yaxes(title_text="(Bid - Ask) / Total", row=3, col=1)
    return figure

def make_order_flow_microstructure_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot order-style composition, order lifecycle events, and executions."""

    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        subplot_titles=[
            "Market-Order Share",
            "Cancelled and Expired Resting Orders",
            "Executed Trades",
        ],
        vertical_spacing=0.08,
    )
    for index, run_id in enumerate(run_ids):
        time_series = _simulation_phase(load_step_timeseries(experiment_dir / run_id))
        required_columns = {
            "submitted_limit_orders",
            "submitted_market_orders",
            "cancelled_orders",
            "expired_orders",
            "executed_trades",
        }
        if not required_columns.issubset(time_series.columns):
            continue

        colour = COLOUR_SEQUENCE[index % len(COLOUR_SEQUENCE)]
        x_values = _time_axis(time_series)
        display_label = _run_label(run_id, run_labels)
        limit_orders = pd.to_numeric(
            time_series["submitted_limit_orders"],
            errors="coerce",
        ).fillna(0.0)
        market_orders = pd.to_numeric(
            time_series["submitted_market_orders"],
            errors="coerce",
        ).fillna(0.0)
        submitted_total = (limit_orders + market_orders).replace(0.0, np.nan)
        market_order_share = market_orders / submitted_total
        cancelled_orders = pd.to_numeric(
            time_series["cancelled_orders"],
            errors="coerce",
        ).fillna(0.0)
        expired_orders = pd.to_numeric(
            time_series["expired_orders"],
            errors="coerce",
        ).fillna(0.0)
        lifecycle_events = cancelled_orders + expired_orders

        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=market_order_share,
                mode="lines",
                name=display_label,
                legendgroup=display_label,
                line=dict(color=colour, width=1.4),
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=lifecycle_events,
                mode="lines",
                name=display_label,
                legendgroup=display_label,
                showlegend=False,
                line=dict(color=colour, width=1.4),
            ),
            row=2,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=pd.to_numeric(time_series["executed_trades"], errors="coerce").fillna(0.0),
                mode="lines",
                name=display_label,
                legendgroup=display_label,
                showlegend=False,
                line=dict(color=colour, width=1.4),
            ),
            row=3,
            col=1,
        )

    if not figure.data:
        return _empty_figure("No LOB order-flow diagnostics are available.")
    figure.update_layout(
        title="Order Flow and Book Lifecycle",
        template=PLOT_TEMPLATE,
        height=780,
        legend_title="Run",
    )
    figure.update_xaxes(title_text="Simulation Step", row=3, col=1)
    figure.update_yaxes(title_text="Share", range=[0, 1], row=1, col=1)
    figure.update_yaxes(title_text="Orders", row=2, col=1)
    figure.update_yaxes(title_text="Trades", row=3, col=1)
    return figure

def make_allocative_efficiency_timeseries_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot gross CDA allocative efficiency and positive-surplus opportunities.

    The C++ simulator exports zero efficiency when no positive-surplus match is
    available. The report masks those no-opportunity rows when
    ``maximum_allocative_surplus`` is available, matching the run-level mean
    convention and avoiding visual confusion between no opportunity and an
    inefficient allocation.
    """

    plot_rows: list[tuple[str, pd.DataFrame, pd.Series, pd.Series | None, pd.Series | None]] = []
    has_surplus_schedule = False
    for run_id in run_ids:
        time_series = _simulation_phase(load_step_timeseries(experiment_dir / run_id))
        if "allocative_efficiency" not in time_series.columns:
            continue

        efficiency = pd.to_numeric(time_series["allocative_efficiency"], errors="coerce")
        maximum_surplus: pd.Series | None = None
        realized_surplus: pd.Series | None = None
        if "maximum_allocative_surplus" in time_series.columns:
            maximum_surplus = pd.to_numeric(
                time_series["maximum_allocative_surplus"],
                errors="coerce",
            )
            if maximum_surplus.notna().any():
                positive_opportunity = maximum_surplus > 0.0
                efficiency = efficiency.where(positive_opportunity)
                has_surplus_schedule = True
        if "realized_allocative_surplus" in time_series.columns:
            realized_surplus = pd.to_numeric(
                time_series["realized_allocative_surplus"],
                errors="coerce",
            )

        if efficiency.notna().any() or (
            maximum_surplus is not None and maximum_surplus.notna().any()
        ):
            plot_rows.append((run_id, time_series, efficiency, maximum_surplus, realized_surplus))

    if not plot_rows:
        return _empty_figure("No allocative-efficiency diagnostics are available.")

    row_count = 2 if has_surplus_schedule else 1
    subplot_titles = ["Allocative Efficiency"]
    if has_surplus_schedule:
        subplot_titles.append("Gross Allocative Surplus")
    figure = make_subplots(
        rows=row_count,
        cols=1,
        shared_xaxes=True,
        subplot_titles=subplot_titles,
        vertical_spacing=0.10,
    )

    for index, (run_id, time_series, efficiency, maximum_surplus, realized_surplus) in enumerate(
        plot_rows
    ):
        colour = COLOUR_SEQUENCE[index % len(COLOUR_SEQUENCE)]
        x_values = _time_axis(time_series)
        display_label = _run_label(run_id, run_labels)
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=efficiency,
                mode="lines",
                name=display_label,
                legendgroup=display_label,
                line=dict(color=colour, width=1.5),
                hovertemplate=(
                    "Step=%{x}<br>Allocative efficiency=%{y:.4f}<extra>"
                    f"{display_label}</extra>"
                ),
            ),
            row=1,
            col=1,
        )

        if has_surplus_schedule and maximum_surplus is not None:
            figure.add_trace(
                go.Scatter(
                    x=x_values,
                    y=maximum_surplus,
                    mode="lines",
                    name=f"{display_label} maximum surplus",
                    legendgroup=display_label,
                    showlegend=False,
                    line=dict(color=colour, width=1.2),
                ),
                row=2,
                col=1,
            )
            if realized_surplus is not None and realized_surplus.notna().any():
                figure.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=realized_surplus,
                        mode="lines",
                        name=f"{display_label} realized surplus",
                        legendgroup=display_label,
                        showlegend=False,
                        line=dict(color=colour, width=1.1, dash="dash"),
                    ),
                    row=2,
                    col=1,
                )

    figure.update_layout(
        title="Double-Auction Allocative Efficiency",
        template=PLOT_TEMPLATE,
        height=680 if row_count == 2 else 420,
        legend_title="Run",
    )
    figure.update_xaxes(title_text="Simulation Step", row=row_count, col=1)
    figure.update_yaxes(title_text="Efficiency", range=[0, 1], row=1, col=1)
    if has_surplus_schedule:
        figure.update_yaxes(title_text="Gross Surplus", row=2, col=1)
    return figure
