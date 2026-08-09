"""Simulation-vs-benchmark return comparison figures."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .common import (
    COLOUR_SEQUENCE,
    PLOT_TEMPLATE,
    REPORT_COLOURS,
    _empty_figure,
    _finite_array,
    _run_label,
)


def make_simulation_benchmark_ecdf_figure(
    simulation_returns: dict[str, pd.Series],
    benchmark_returns: dict[str, pd.Series],
    run_ids: list[str],
    *,
    benchmark_ids: list[str] | None = None,
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Overlay simulated and empirical return ECDFs."""

    figure = go.Figure()
    for index, run_id in enumerate(run_ids):
        values = simulation_returns.get(run_id, pd.Series(dtype=float)).dropna().sort_values()
        if values.empty:
            continue
        y_values = np.arange(1, len(values) + 1) / len(values)
        figure.add_trace(
            go.Scatter(
                x=values,
                y=y_values,
                mode="lines",
                name=f"{_run_label(run_id, run_labels)} simulation",
                line=dict(color=COLOUR_SEQUENCE[index % len(COLOUR_SEQUENCE)], width=1.5),
            )
        )

    selected_benchmarks = benchmark_ids or sorted(benchmark_returns)
    for index, benchmark_id in enumerate(selected_benchmarks):
        values = benchmark_returns.get(benchmark_id, pd.Series(dtype=float)).dropna().sort_values()
        if values.empty:
            continue
        y_values = np.arange(1, len(values) + 1) / len(values)
        figure.add_trace(
            go.Scatter(
                x=values,
                y=y_values,
                mode="lines",
                name=f"{benchmark_id} benchmark",
                line=dict(
                    color=COLOUR_SEQUENCE[(index + len(run_ids)) % len(COLOUR_SEQUENCE)],
                    width=2.0,
                    dash="dash",
                ),
            )
        )

    if not figure.data:
        return _empty_figure("No simulated or empirical returns are available.")
    figure.update_layout(
        title="Simulation and Empirical Return ECDFs",
        template=PLOT_TEMPLATE,
        height=560,
        xaxis_title="Log Return",
        yaxis_title="ECDF",
        legend_title="Series",
    )
    return figure


def make_simulation_benchmark_qq_figure(
    simulation_returns: dict[str, pd.Series],
    benchmark_returns: dict[str, pd.Series],
    run_ids: list[str],
    *,
    benchmark_ids: list[str] | None = None,
    run_labels: dict[str, str] | None = None,
    quantile_count: int = 99,
) -> go.Figure:
    """Plot Q-Q comparisons of simulated returns against empirical benchmarks."""

    selected_benchmarks = benchmark_ids or sorted(benchmark_returns)
    if not run_ids or not selected_benchmarks:
        return _empty_figure("At least one simulation and benchmark are required for Q-Q plots.")

    figure = go.Figure()
    probabilities = np.linspace(0.01, 0.99, quantile_count)
    combined_values: list[float] = []
    trace_index = 0
    for run_id in run_ids:
        sim_values = _finite_array(simulation_returns.get(run_id, pd.Series(dtype=float)))
        if len(sim_values) == 0:
            continue
        sim_quantiles = np.quantile(sim_values, probabilities)
        for benchmark_id in selected_benchmarks:
            benchmark_values = _finite_array(benchmark_returns.get(benchmark_id, pd.Series(dtype=float)))
            if len(benchmark_values) == 0:
                continue
            benchmark_quantiles = np.quantile(benchmark_values, probabilities)
            combined_values.extend(sim_quantiles.tolist())
            combined_values.extend(benchmark_quantiles.tolist())
            figure.add_trace(
                go.Scatter(
                    x=benchmark_quantiles,
                    y=sim_quantiles,
                    mode="markers",
                    name=f"{_run_label(run_id, run_labels)} vs {benchmark_id}",
                    marker=dict(
                        color=COLOUR_SEQUENCE[trace_index % len(COLOUR_SEQUENCE)],
                        size=6,
                        opacity=0.72,
                    ),
                )
            )
            trace_index += 1

    if not figure.data:
        return _empty_figure("No finite return quantiles are available.")
    min_value = min(combined_values)
    max_value = max(combined_values)
    figure.add_trace(
        go.Scatter(
            x=[min_value, max_value],
            y=[min_value, max_value],
            mode="lines",
            name="45-degree reference",
            line=dict(color=REPORT_COLOURS["graphite"], dash="dot", width=1.2),
        )
    )
    figure.update_layout(
        title="Simulation vs Empirical Return Q-Q Comparison",
        template=PLOT_TEMPLATE,
        height=560,
        xaxis_title="Empirical Benchmark Quantile",
        yaxis_title="Simulation Quantile",
        legend_title="Pair",
    )
    return figure


def make_return_tail_figure(
    simulation_returns: dict[str, pd.Series],
    benchmark_returns: dict[str, pd.Series],
    run_ids: list[str],
    *,
    benchmark_ids: list[str] | None = None,
    run_labels: dict[str, str] | None = None,
) -> go.Figure:
    """Show lower and upper tail quantiles for simulations and benchmarks."""

    rows: list[dict[str, object]] = []
    quantiles = [0.01, 0.05, 0.95, 0.99]
    for run_id in run_ids:
        values = _finite_array(simulation_returns.get(run_id, pd.Series(dtype=float)))
        if len(values) == 0:
            continue
        for quantile in quantiles:
            rows.append(
                {
                    "series": _run_label(run_id, run_labels),
                    "source_type": "simulation",
                    "tail_quantile": f"{int(quantile * 100)}%",
                    "log_return": float(np.quantile(values, quantile)),
                }
            )
    for benchmark_id in benchmark_ids or sorted(benchmark_returns):
        values = _finite_array(benchmark_returns.get(benchmark_id, pd.Series(dtype=float)))
        if len(values) == 0:
            continue
        for quantile in quantiles:
            rows.append(
                {
                    "series": benchmark_id,
                    "source_type": "benchmark",
                    "tail_quantile": f"{int(quantile * 100)}%",
                    "log_return": float(np.quantile(values, quantile)),
                }
            )

    data = pd.DataFrame(rows)
    if data.empty:
        return _empty_figure("No tail quantiles are available.")
    figure = px.bar(
        data,
        x="series",
        y="log_return",
        color="tail_quantile",
        facet_row="source_type",
        barmode="group",
        template=PLOT_TEMPLATE,
        color_discrete_sequence=COLOUR_SEQUENCE,
        title="Return Tail Quantiles",
    )
    figure.update_layout(height=620, xaxis_title="Series", yaxis_title="Log Return")
    figure.update_xaxes(tickangle=35)
    return figure
