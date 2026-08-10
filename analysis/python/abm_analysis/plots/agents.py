"""Agent-level wealth, portfolio, behaviour, and trading figures."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from abm_analysis.archive.data import load_step_timeseries, read_csv_if_exists, resolve_artifact_path

from .common import (
    AGENT_SUMMARY_METRICS,
    COLOUR_SEQUENCE,
    PLOT_TEMPLATE,
    _agent_strategy_column,
    _empty_figure,
    _run_label,
    _simulation_phase,
    _time_axis,
)


def make_wealth_gini_timeseries_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot whole-population non-negative wealth Gini coefficients over time."""

    figure = go.Figure()
    for run_index, run_id in enumerate(run_ids):
        time_series = _simulation_phase(load_step_timeseries(experiment_dir / run_id))
        if time_series.empty or "wealth_gini_coefficient" not in time_series.columns:
            continue
        values = pd.to_numeric(time_series["wealth_gini_coefficient"], errors="coerce")
        finite_rows = values.notna() & np.isfinite(values)
        if not finite_rows.any():
            continue
        figure.add_trace(
            go.Scatter(
                x=_time_axis(time_series.loc[finite_rows]),
                y=values.loc[finite_rows],
                mode="lines",
                name=_run_label(run_id, run_labels),
                line=dict(color=COLOUR_SEQUENCE[run_index % len(COLOUR_SEQUENCE)], width=2),
            )
        )

    if not figure.data:
        return _empty_figure("No wealth Gini coefficient diagnostics are available.")
    figure.update_layout(
        title="Agent Wealth Gini Coefficient Over Time",
        template=PLOT_TEMPLATE,
        height=520,
        xaxis_title="Simulation Step",
        yaxis_title="Gini Coefficient",
    )
    figure.update_yaxes(range=[0, 1])
    return figure

def make_agent_behavioural_outcome_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Link CPT/reference diagnostics with agent wealth and trading outcomes."""

    agents = _load_agent_snapshots(experiment_dir, run_ids, run_labels)
    required_columns = {"last_prospect_reference_point", "final_wealth", "number_of_trades"}
    if agents.empty or not required_columns.issubset(agents.columns):
        return _empty_figure("No agent behavioural outcome diagnostics are available.")
    strategy_column = _agent_strategy_column(agents)
    agents["last_prospect_reference_point"] = pd.to_numeric(
        agents["last_prospect_reference_point"],
        errors="coerce",
    )
    agents["final_wealth"] = pd.to_numeric(agents["final_wealth"], errors="coerce")
    agents["number_of_trades"] = pd.to_numeric(agents["number_of_trades"], errors="coerce").fillna(0)
    scatter_kwargs: dict[str, object] = {
        "data_frame": agents,
        "x": "last_prospect_reference_point",
        "y": "final_wealth",
        "size": "number_of_trades",
        "hover_data": ["simulation_label", "agent_id"]
        if "agent_id" in agents.columns
        else ["simulation_label"],
        "template": PLOT_TEMPLATE,
        "color_discrete_sequence": COLOUR_SEQUENCE,
        "title": "Agent Reference Points, Wealth, and Trading Activity",
    }
    if strategy_column is not None:
        scatter_kwargs["color"] = strategy_column
    figure = px.scatter(**scatter_kwargs)
    figure.update_layout(
        height=560,
        xaxis_title="Last CPT Reference Point",
        yaxis_title="Final Wealth",
        legend_title="Strategy",
    )
    return figure

def make_agent_wealth_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Compare final agent wealth distributions when agent snapshots exist."""

    frames = []
    for run_id in run_ids:
        agents = read_csv_if_exists(resolve_artifact_path(experiment_dir / run_id, "agents_final.csv"))
        if agents.empty or "final_wealth" not in agents.columns:
            continue
        agents["run_id"] = run_id
        agents["simulation_label"] = _run_label(run_id, run_labels)
        if "initial_wealth" in agents.columns:
            agents["wealth_change"] = agents["final_wealth"] - agents["initial_wealth"]
        else:
            agents["wealth_change"] = np.nan
        frames.append(agents)

    if not frames:
        return _empty_figure("No agent final-wealth data are available.")
    data = pd.concat(frames, ignore_index=True)
    color_column = "current_strategy_type" if "current_strategy_type" in data.columns else None
    figure = px.box(
        data,
        x="simulation_label",
        y="final_wealth",
        color=color_column,
        points=False,
        template=PLOT_TEMPLATE,
        color_discrete_sequence=COLOUR_SEQUENCE,
        title="Agent Final-Wealth Distribution",
    )
    figure.update_layout(height=520, xaxis_title="Simulation", yaxis_title="Final Wealth")
    figure.update_xaxes(tickangle=45)
    return figure

def make_agent_return_lorenz_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot cumulative agents against cumulative non-negative return earned.

    Agents are ordered from the lowest to highest realised wealth return. Losses
    contribute zero earned return so the curve remains a bounded concentration
    diagnostic consistent with the non-negative Gini policy used for wealth.
    """

    agents = _load_agent_snapshots(experiment_dir, run_ids, run_labels)
    required_columns = {"initial_wealth", "final_wealth", "run_id", "simulation_label"}
    if agents.empty or not required_columns.issubset(agents.columns):
        return _empty_figure("No agent return data are available for a cumulative-share chart.")

    figure = go.Figure()
    for run_index, run_id in enumerate(run_ids):
        subset = agents.loc[agents["run_id"] == run_id].copy()
        if subset.empty:
            continue
        initial_wealth = pd.to_numeric(subset["initial_wealth"], errors="coerce")
        final_wealth = pd.to_numeric(subset["final_wealth"], errors="coerce")
        finite_rows = (
            np.isfinite(initial_wealth)
            & np.isfinite(final_wealth)
            & (initial_wealth > 0.0)
        )
        subset = subset.loc[finite_rows].copy()
        if subset.empty:
            continue

        subset["wealth_change"] = final_wealth.loc[finite_rows] - initial_wealth.loc[finite_rows]
        subset["realised_return"] = subset["wealth_change"] / initial_wealth.loc[finite_rows]
        subset["return_earned"] = subset["wealth_change"].clip(lower=0.0)
        subset = subset.sort_values(
            ["realised_return", "return_earned"],
            ascending=[True, True],
            kind="mergesort",
        )
        total_return_earned = float(subset["return_earned"].sum())
        if total_return_earned <= 1e-12:
            continue

        cumulative_agents = np.concatenate(
            ([0.0], np.arange(1, len(subset) + 1, dtype=float) / float(len(subset)))
        )
        cumulative_return = np.concatenate(
            ([0.0], subset["return_earned"].cumsum().to_numpy(dtype=float) / total_return_earned)
        )
        figure.add_trace(
            go.Scatter(
                x=cumulative_agents,
                y=cumulative_return,
                mode="lines",
                name=_run_label(run_id, run_labels),
                line=dict(color=COLOUR_SEQUENCE[run_index % len(COLOUR_SEQUENCE)], width=2),
                hovertemplate=(
                    "Cumulative agent share=%{x:.1%}<br>"
                    "Cumulative return earned=%{y:.1%}<extra>%{fullData.name}</extra>"
                ),
            )
        )

    if not figure.data:
        return _empty_figure("No positive agent return earned data are available.")
    figure.add_trace(
        go.Scatter(
            x=[0.0, 1.0],
            y=[0.0, 1.0],
            mode="lines",
            name="Equal return share",
            line=dict(color="#7f8a99", width=1.5, dash="dash"),
            hoverinfo="skip",
        )
    )
    figure.update_layout(
        title="Cumulative Agent Return Share",
        template=PLOT_TEMPLATE,
        height=540,
        xaxis_title="Cumulative Share of Agents (Lowest to Highest Return)",
        yaxis_title="Cumulative Share of Return Earned",
    )
    figure.update_xaxes(range=[0, 1], tickformat=".0%")
    figure.update_yaxes(range=[0, 1], tickformat=".0%")
    return figure

def build_agent_summary_statistics(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Aggregate agent-level diagnostics by run and behavioural strategy."""

    agents = _load_agent_snapshots(experiment_dir, run_ids, run_labels)
    if agents.empty:
        return pd.DataFrame()

    strategy_column = _agent_strategy_column(agents)
    group_columns = ["simulation_label", "run_id"]
    if strategy_column is not None:
        group_columns.append(strategy_column)

    available_metrics = [column for column in AGENT_SUMMARY_METRICS if column in agents.columns]
    for column in available_metrics:
        agents[column] = pd.to_numeric(agents[column], errors="coerce")

    rows: list[dict[str, float | int | str]] = []
    for group_key, group in agents.groupby(group_columns, dropna=False):
        group_values = group_key if isinstance(group_key, tuple) else (group_key,)
        row: dict[str, float | int | str] = {"agent_count": int(len(group))}
        for column, value in zip(group_columns, group_values, strict=True):
            row[column] = value

        for metric in available_metrics:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            if values.empty:
                continue
            row[f"{metric}_mean"] = float(values.mean())
            row[f"{metric}_median"] = float(values.median())
            row[f"{metric}_std"] = float(values.std(ddof=1)) if len(values) > 1 else 0.0
            row[f"{metric}_min"] = float(values.min())
            row[f"{metric}_max"] = float(values.max())

        rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(group_columns).reset_index(drop=True)

def make_agent_portfolio_distribution_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot cross-sectional portfolio-state distributions for final agents."""

    agents = _load_agent_snapshots(experiment_dir, run_ids, run_labels)
    metrics = [
        ("final_wealth", "Final Wealth"),
        ("wealth_change", "Wealth Change"),
        ("final_cash", "Final Cash"),
        ("final_stock", "Final Stock"),
    ]
    available_metrics = [(column, title) for column, title in metrics if column in agents.columns]
    if agents.empty or not available_metrics:
        return _empty_figure("No agent portfolio-state diagnostics are available.")

    strategy_column = _agent_strategy_column(agents)
    figure = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=[title for _, title in available_metrics],
    )
    for index, (column, title) in enumerate(available_metrics, start=1):
        row = 1 if index <= 2 else 2
        col = index if index <= 2 else index - 2
        if strategy_column is None:
            figure.add_trace(
                go.Box(
                    x=agents["simulation_label"],
                    y=pd.to_numeric(agents[column], errors="coerce"),
                    name=title,
                    marker_color=COLOUR_SEQUENCE[(index - 1) % len(COLOUR_SEQUENCE)],
                    boxpoints=False,
                    showlegend=False,
                ),
                row=row,
                col=col,
            )
            continue

        for strategy_index, (strategy, subset) in enumerate(agents.groupby(strategy_column)):
            figure.add_trace(
                go.Box(
                    x=subset["simulation_label"],
                    y=pd.to_numeric(subset[column], errors="coerce"),
                    name=str(strategy),
                    legendgroup=str(strategy),
                    marker_color=COLOUR_SEQUENCE[strategy_index % len(COLOUR_SEQUENCE)],
                    boxpoints=False,
                    showlegend=index == 1,
                ),
                row=row,
                col=col,
            )

    figure.update_layout(
        title="Agent Portfolio Distributions",
        template=PLOT_TEMPLATE,
        height=780,
        boxmode="group",
        legend_title="Strategy",
    )
    figure.update_xaxes(title_text="Simulation", tickangle=35)
    return figure

def make_agent_trading_activity_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot agent trade counts, traded volume, and activity concentration."""

    agents = _load_agent_snapshots(experiment_dir, run_ids, run_labels)
    required_columns = {"number_of_trades", "traded_volume"}
    if agents.empty or not required_columns.issubset(agents.columns):
        return _empty_figure("No agent trading-activity diagnostics are available.")

    agents["number_of_trades"] = pd.to_numeric(agents["number_of_trades"], errors="coerce").fillna(0)
    agents["traded_volume"] = pd.to_numeric(agents["traded_volume"], errors="coerce").fillna(0.0)
    strategy_column = _agent_strategy_column(agents)
    figure = make_subplots(
        rows=2,
        cols=2,
        specs=[
            [{"type": "xy"}, {"type": "xy"}],
            [{"type": "xy", "colspan": 2}, None],
        ],
        subplot_titles=[
            "Trade Count Distribution",
            "Traded Volume Distribution",
            "Trade Count vs Traded Volume",
        ],
    )

    color_groups = _agent_color_groups(agents, strategy_column)
    for group_index, (label, subset) in enumerate(color_groups):
        colour = COLOUR_SEQUENCE[group_index % len(COLOUR_SEQUENCE)]
        figure.add_trace(
            go.Box(
                x=subset["simulation_label"],
                y=subset["number_of_trades"],
                name=label,
                legendgroup=label,
                marker_color=colour,
                boxpoints=False,
                showlegend=True,
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Box(
                x=subset["simulation_label"],
                y=subset["traded_volume"],
                name=label,
                legendgroup=label,
                marker_color=colour,
                boxpoints=False,
                showlegend=False,
            ),
            row=1,
            col=2,
        )
        figure.add_trace(
            go.Scatter(
                x=subset["number_of_trades"],
                y=subset["traded_volume"],
                mode="markers",
                name=label,
                legendgroup=label,
                marker=dict(color=colour, size=7, opacity=0.65),
                text=subset["simulation_label"],
                showlegend=False,
            ),
            row=2,
            col=1,
        )

    figure.update_layout(
        title="Agent Trading Activity",
        template=PLOT_TEMPLATE,
        height=820,
        boxmode="group",
        legend_title="Strategy",
    )
    figure.update_xaxes(title_text="Simulation", tickangle=35, row=1, col=1)
    figure.update_xaxes(title_text="Simulation", tickangle=35, row=1, col=2)
    figure.update_xaxes(title_text="Number of Trades", row=2, col=1)
    figure.update_yaxes(title_text="Number of Trades", row=1, col=1)
    figure.update_yaxes(title_text="Traded Volume", row=1, col=2)
    figure.update_yaxes(title_text="Traded Volume", row=2, col=1)
    return figure

def make_agent_reference_point_figure(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot agent entry-price, peak-wealth, and CPT reference diagnostics."""

    agents = _load_agent_snapshots(experiment_dir, run_ids, run_labels)
    metrics = [
        ("average_entry_price", "Average Entry Price"),
        ("recent_peak_wealth", "Recent Peak Wealth"),
        ("last_prospect_reference_point", "Last CPT Reference Point"),
    ]
    available_metrics = [(column, title) for column, title in metrics if column in agents.columns]
    if agents.empty or not available_metrics:
        return _empty_figure("No agent reference-point diagnostics are available.")

    strategy_column = _agent_strategy_column(agents)
    figure = make_subplots(
        rows=len(available_metrics),
        cols=1,
        shared_xaxes=True,
        subplot_titles=[title for _, title in available_metrics],
        vertical_spacing=0.08,
    )
    color_groups = _agent_color_groups(agents, strategy_column)
    for row_index, (column, _) in enumerate(available_metrics, start=1):
        for group_index, (label, subset) in enumerate(color_groups):
            values = pd.to_numeric(subset[column], errors="coerce")
            values = values.where(np.isfinite(values) & (values > 0))
            if values.notna().sum() == 0:
                continue
            figure.add_trace(
                go.Box(
                    x=subset["simulation_label"],
                    y=values,
                    name=label,
                    legendgroup=label,
                    marker_color=COLOUR_SEQUENCE[group_index % len(COLOUR_SEQUENCE)],
                    boxpoints=False,
                    showlegend=row_index == 1,
                ),
                row=row_index,
                col=1,
            )

    if not figure.data:
        return _empty_figure("No positive agent reference-point diagnostics are available.")
    figure.update_layout(
        title="Agent Reference-Point Diagnostics",
        template=PLOT_TEMPLATE,
        height=max(420, 280 * len(available_metrics)),
        boxmode="group",
        legend_title="Strategy",
    )
    figure.update_xaxes(title_text="Simulation", tickangle=35, row=len(available_metrics), col=1)
    figure.update_yaxes(title_text="Value")
    return figure

def _load_agent_snapshots(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> pd.DataFrame:
    frames = []
    for run_id in run_ids:
        agents = read_csv_if_exists(resolve_artifact_path(experiment_dir / run_id, "agents_final.csv"))
        if agents.empty:
            continue
        agents["run_id"] = run_id
        agents["simulation_label"] = _run_label(run_id, run_labels)
        if "initial_wealth" in agents.columns and "final_wealth" in agents.columns:
            agents["wealth_change"] = (
                pd.to_numeric(agents["final_wealth"], errors="coerce")
                - pd.to_numeric(agents["initial_wealth"], errors="coerce")
            )
        frames.append(agents)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)

def _agent_color_groups(
    agents: pd.DataFrame,
    strategy_column: str | None,
) -> list[tuple[str, pd.DataFrame]]:
    if strategy_column is None:
        return [("agents", agents)]
    return [(str(label), group) for label, group in agents.groupby(strategy_column, dropna=False)]
