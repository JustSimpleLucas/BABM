"""Return-distribution figures for ABM simulation diagnostics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from statsmodels.tsa.stattools import acf

from .common import (
    COLOUR_SEQUENCE,
    HEATMAP_COLOUR_SCALE,
    PLOT_TEMPLATE,
    _empty_figure,
    _run_label,
)
from .return_attribution import (
    _long_returns_by_agent_strategy,
    _make_agent_stacked_return_histogram,
)


def make_return_histogram_figure(
    return_series_by_run: dict[str, pd.Series],
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
    *,
    experiment_dir: Path | None = None,
    phase: str = "simulation",
    price_column: str = "market_price",
    agent_run_ids: list[str] | None = None,
) -> go.Figure:
    """Compare empirical return densities for the selected return series.

    ``run_ids`` selects entries from ``return_series_by_run`` and may name
    per-asset series rather than runs. The agent-strategy attribution variant
    reads run directories from disk, so it takes ``agent_run_ids``, which must
    be actual run ids; it defaults to ``run_ids`` for run-keyed callers.
    """

    if experiment_dir is not None:
        agent_returns = _long_returns_by_agent_strategy(
            experiment_dir,
            run_ids if agent_run_ids is None else agent_run_ids,
            run_labels,
            phase=phase,
            price_column=price_column,
        )
        if not agent_returns.empty:
            return _make_agent_stacked_return_histogram(agent_returns)

    long_returns = _long_returns(return_series_by_run, run_ids, run_labels)
    if long_returns.empty:
        return _empty_figure("No return observations are available.")
    figure = px.histogram(
        long_returns,
        x="log_return",
        color="simulation_label",
        histnorm="probability density",
        nbins=80,
        opacity=0.58,
        barmode="overlay",
        color_discrete_sequence=COLOUR_SEQUENCE,
        template=PLOT_TEMPLATE,
        title="Log-Return Distribution",
    )
    figure.update_layout(height=500, xaxis_title="Log Return", yaxis_title="Density")
    return figure


def make_return_ecdf_figure(
    return_series_by_run: dict[str, pd.Series],
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Plot empirical CDFs used to interpret K-S distribution distances."""

    figure = go.Figure()
    for index, run_id in enumerate(run_ids):
        values = return_series_by_run.get(run_id, pd.Series(dtype=float)).dropna().sort_values()
        if values.empty:
            continue
        y_values = np.arange(1, len(values) + 1) / len(values)
        figure.add_trace(
            go.Scatter(
                x=values,
                y=y_values,
                mode="lines",
                name=_run_label(run_id, run_labels),
                line=dict(color=COLOUR_SEQUENCE[index % len(COLOUR_SEQUENCE)], width=1.6),
            )
        )
    if not figure.data:
        return _empty_figure("No return observations are available.")
    figure.update_layout(
        title="Empirical CDF of Log Returns",
        template=PLOT_TEMPLATE,
        height=500,
        xaxis_title="Log Return",
        yaxis_title="ECDF",
    )
    return figure


def make_ks_heatmap_figure(
    pairwise_ks: pd.DataFrame,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Display pairwise K-S distances as a heatmap."""

    if pairwise_ks.empty or not run_ids:
        return _empty_figure("At least two runs are required for pairwise K-S comparison.")
    matrix = pd.DataFrame(0.0, index=run_ids, columns=run_ids)
    for _, row in pairwise_ks.iterrows():
        run_a = row["run_id_a"]
        run_b = row["run_id_b"]
        if run_a in matrix.index and run_b in matrix.columns:
            matrix.loc[run_a, run_b] = row["ks_statistic"]
            matrix.loc[run_b, run_a] = row["ks_statistic"]
    matrix.index = [_run_label(run_id, run_labels) for run_id in matrix.index]
    matrix.columns = [_run_label(run_id, run_labels) for run_id in matrix.columns]
    figure = px.imshow(
        matrix,
        color_continuous_scale=HEATMAP_COLOUR_SCALE,
        aspect="auto",
        template=PLOT_TEMPLATE,
        title="Pairwise K-S Distance Between Return Distributions",
        labels=dict(color="K-S statistic"),
    )
    figure.update_layout(height=620, xaxis_title="Run", yaxis_title="Run")
    return figure


def make_acf_figure(
    return_series_by_run: dict[str, pd.Series],
    run_ids: list[str],
    *,
    run_labels: dict[str, str] | None = None,
    max_lag: int = 60,
) -> go.Figure:
    """Plot ACFs for raw, absolute, and squared returns."""

    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        subplot_titles=[
            "ACF of Log Returns",
            "ACF of Absolute Log Returns",
            "ACF of Squared Log Returns",
        ],
    )
    transforms = [
        ("raw", lambda values: values),
        ("absolute", np.abs),
        ("squared", lambda values: values**2),
    ]
    for run_index, run_id in enumerate(run_ids):
        values = return_series_by_run.get(run_id, pd.Series(dtype=float)).dropna().to_numpy(dtype=float)
        if len(values) < 5:
            continue
        lag_count = min(max_lag, max(1, len(values) // 4))
        colour = COLOUR_SEQUENCE[run_index % len(COLOUR_SEQUENCE)]
        display_label = _run_label(run_id, run_labels)
        for row_index, (_, transform) in enumerate(transforms, start=1):
            transformed_values = transform(values)
            if not np.isfinite(transformed_values).all() or np.std(transformed_values) <= 0:
                continue
            acf_values = acf(transformed_values, nlags=lag_count, fft=True)
            figure.add_trace(
                go.Scatter(
                    x=list(range(len(acf_values))),
                    y=acf_values,
                    mode="lines",
                    name=display_label if row_index == 1 else None,
                    legendgroup=display_label,
                    showlegend=row_index == 1,
                    line=dict(color=colour, width=1.4),
                ),
                row=row_index,
                col=1,
            )
    if not figure.data:
        return _empty_figure("No return ACFs are available.")
    figure.update_layout(
        title="Autocorrelation Diagnostics",
        template=PLOT_TEMPLATE,
        height=820,
        xaxis3_title="Lag",
    )
    figure.update_yaxes(title_text="ACF")
    return figure


def _long_returns(
    return_series_by_run: dict[str, pd.Series],
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> pd.DataFrame:
    frames = []
    for run_id in run_ids:
        values = return_series_by_run.get(run_id, pd.Series(dtype=float)).dropna()
        if values.empty:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "run_id": run_id,
                    "simulation_label": _run_label(run_id, run_labels),
                    "log_return": values,
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=["run_id", "simulation_label", "log_return"])
    return pd.concat(frames, ignore_index=True)
