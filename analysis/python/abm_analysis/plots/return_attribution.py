"""Agent-strategy attribution helpers for return-distribution plots."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from abm_analysis.data import load_step_timeseries, read_csv_if_exists, resolve_artifact_path

from .common import (
    COLOUR_SEQUENCE,
    PLOT_TEMPLATE,
    _agent_strategy_column,
    _analysis_phase,
    _empty_figure,
    _run_label,
)


def _long_returns_by_agent_strategy(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
    *,
    phase: str,
    price_column: str,
) -> pd.DataFrame:
    """Return step-level log returns weighted by trading strategy participation."""

    frames = []
    for run_id in run_ids:
        run_dir = experiment_dir / run_id
        try:
            time_series = load_step_timeseries(run_dir, price_column=price_column)
        except (FileNotFoundError, KeyError, NotADirectoryError):
            continue

        time_series = _analysis_phase(time_series, phase)
        if "computed_log_return" not in time_series.columns:
            continue

        step_column = _return_step_column(time_series)
        returns = pd.DataFrame(
            {
                "run_id": str(run_id),
                "simulation_label": _run_label(run_id, run_labels),
                "simulation_step": step_column,
                "log_return": pd.to_numeric(
                    time_series["computed_log_return"],
                    errors="coerce",
                ),
            }
        )
        returns = returns[np.isfinite(returns["log_return"])]
        if returns.empty:
            continue

        participation = _agent_strategy_participation_by_step(run_dir)
        if participation.empty:
            continue

        attributed = returns.merge(participation, on="simulation_step", how="left")
        attributed["agent_strategy"] = attributed["agent_strategy"].fillna("unattributed")
        attributed["agent_weight"] = pd.to_numeric(
            attributed["agent_weight"],
            errors="coerce",
        ).fillna(1.0)
        frames.append(attributed)

    if not frames:
        return pd.DataFrame(
            columns=[
                "run_id",
                "simulation_label",
                "simulation_step",
                "log_return",
                "agent_strategy",
                "agent_weight",
            ]
        )
    return pd.concat(frames, ignore_index=True)


def _agent_strategy_participation_by_step(run_dir: Path) -> pd.DataFrame:
    """Estimate strategy participation shares from trade counterparties."""

    agents = read_csv_if_exists(resolve_artifact_path(run_dir, "agents_final.csv"))
    trades = read_csv_if_exists(resolve_artifact_path(run_dir, "trade_ledger.csv"))
    required_trade_columns = {"time", "agent_id", "counterparty_agent_id", "qty"}
    if agents.empty or trades.empty or not required_trade_columns.issubset(trades.columns):
        return pd.DataFrame(columns=["simulation_step", "agent_strategy", "agent_weight"])

    strategy_column = _agent_strategy_column(agents)
    if strategy_column is None or "agent_id" not in agents.columns:
        return pd.DataFrame(columns=["simulation_step", "agent_strategy", "agent_weight"])

    strategy_by_agent = (
        agents.assign(agent_id=agents["agent_id"].astype(str))
        .set_index("agent_id")[strategy_column]
        .fillna("unknown")
        .astype(str)
    )

    participant_frames = []
    for participant_column in ("agent_id", "counterparty_agent_id"):
        participant_frame = pd.DataFrame(
            {
                "simulation_step": pd.to_numeric(trades["time"], errors="coerce"),
                "agent_id": trades[participant_column].astype(str),
                "participant_volume": pd.to_numeric(trades["qty"], errors="coerce").abs(),
            }
        )
        participant_frame["agent_strategy"] = (
            participant_frame["agent_id"].map(strategy_by_agent).fillna("unknown")
        )
        participant_frames.append(participant_frame)

    participation = pd.concat(participant_frames, ignore_index=True)
    participation = participation[
        np.isfinite(participation["simulation_step"])
        & np.isfinite(participation["participant_volume"])
        & (participation["participant_volume"] > 0.0)
    ]
    if participation.empty:
        return pd.DataFrame(columns=["simulation_step", "agent_strategy", "agent_weight"])

    participation["simulation_step"] = participation["simulation_step"].astype(float)
    grouped = (
        participation.groupby(["simulation_step", "agent_strategy"], dropna=False)[
            "participant_volume"
        ]
        .sum()
        .reset_index()
    )
    total_by_step = grouped.groupby("simulation_step")["participant_volume"].transform("sum")
    grouped["agent_weight"] = grouped["participant_volume"] / total_by_step
    return grouped[["simulation_step", "agent_strategy", "agent_weight"]]


def _return_step_column(time_series: pd.DataFrame) -> pd.Series:
    if "simulation_step" in time_series.columns:
        simulation_step = pd.to_numeric(time_series["simulation_step"], errors="coerce")
        if simulation_step.notna().any():
            return simulation_step.astype(float)
    if "row_index" in time_series.columns:
        return pd.to_numeric(time_series["row_index"], errors="coerce").astype(float)
    return pd.Series(range(len(time_series)), dtype=float)


def _make_agent_stacked_return_histogram(agent_returns: pd.DataFrame) -> go.Figure:
    values = pd.to_numeric(agent_returns["log_return"], errors="coerce")
    weights = pd.to_numeric(agent_returns["agent_weight"], errors="coerce")
    finite = agent_returns[
        np.isfinite(values)
        & np.isfinite(weights)
        & (weights > 0.0)
    ].copy()
    if finite.empty:
        return _empty_figure("No return observations are available.")

    values = pd.to_numeric(finite["log_return"], errors="coerce").to_numpy(dtype=float)
    weights = pd.to_numeric(finite["agent_weight"], errors="coerce").to_numpy(dtype=float)
    bin_edges = _histogram_bin_edges(values, bin_count=80)
    bin_widths = np.diff(bin_edges)
    bin_centres = bin_edges[:-1] + bin_widths / 2.0
    total_weight = weights.sum()
    if total_weight <= 0.0:
        return _empty_figure("No weighted return observations are available.")

    figure = go.Figure()
    strategy_order = sorted(finite["agent_strategy"].astype(str).unique())
    for strategy_index, strategy in enumerate(strategy_order):
        subset = finite[finite["agent_strategy"].astype(str) == strategy]
        strategy_values = pd.to_numeric(
            subset["log_return"],
            errors="coerce",
        ).to_numpy(dtype=float)
        strategy_weights = pd.to_numeric(
            subset["agent_weight"],
            errors="coerce",
        ).to_numpy(dtype=float)
        weighted_counts, _ = np.histogram(
            strategy_values,
            bins=bin_edges,
            weights=strategy_weights,
        )
        density = weighted_counts / (total_weight * bin_widths)
        figure.add_trace(
            go.Bar(
                x=bin_centres,
                y=density,
                width=bin_widths,
                name=strategy,
                marker_color=COLOUR_SEQUENCE[strategy_index % len(COLOUR_SEQUENCE)],
                marker_line_width=0,
                opacity=0.78,
                hovertemplate=(
                    "Log-return bin centre=%{x:.5f}<br>"
                    f"Agent type={strategy}<br>"
                    "Density contribution=%{y:.5f}<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        title="Log-Return Distribution by Agent Type",
        template=PLOT_TEMPLATE,
        height=500,
        barmode="stack",
        bargap=0.0,
        legend_title="Agent type",
        xaxis_title="Log Return",
        yaxis_title="Density",
    )
    return figure


def _histogram_bin_edges(values: np.ndarray, *, bin_count: int) -> np.ndarray:
    if len(values) == 0:
        return np.array([0.0, 1.0])
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    if np.isclose(minimum, maximum):
        padding = max(abs(minimum) * 0.05, 1.0e-6)
        minimum -= padding
        maximum += padding
    return np.linspace(minimum, maximum, bin_count + 1)
