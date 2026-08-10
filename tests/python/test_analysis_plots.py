from __future__ import annotations

from pathlib import Path

import pandas as pd

from abm_analysis.archive.data import discover_run_directories
from abm_analysis.statistics.diagnostics import build_return_series_by_run
from abm_analysis.plots import (
    build_agent_summary_statistics,
    build_simulation_labels,
    make_allocative_efficiency_timeseries_figure,
    make_agent_portfolio_distribution_figure,
    make_agent_reference_point_figure,
    make_agent_return_lorenz_figure,
    make_agent_trading_activity_figure,
    make_market_fundamental_log_return_figure,
    make_microstructure_liquidity_figure,
    make_microstructure_quotes_figure,
    make_order_flow_microstructure_figure,
    make_return_histogram_figure,
    make_wealth_gini_timeseries_figure,
)

from abm_test_helpers import make_synthetic_experiment


def test_simulation_labels_hide_long_archive_names_in_report_display() -> None:
    run_ids = [
        "20260427143012_1_1_0_1_20_30_5_2_180_66",
        "20260427143112_0_1_1_1_20_30_5_2_180_67",
    ]

    labels = build_simulation_labels(run_ids)

    assert labels[run_ids[0]] == "Data 1"
    assert labels[run_ids[1]] == "Data 2"


def test_microstructure_figures_use_lob_diagnostics(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_ids = [path.name for path in discover_run_directories(experiment_dir)]

    quotes = make_microstructure_quotes_figure(experiment_dir, run_ids[:1])
    liquidity = make_microstructure_liquidity_figure(experiment_dir, run_ids)
    order_flow = make_order_flow_microstructure_figure(experiment_dir, run_ids)
    allocative_efficiency = make_allocative_efficiency_timeseries_figure(experiment_dir, run_ids)

    assert quotes.data
    assert liquidity.data
    assert order_flow.data
    assert allocative_efficiency.data
    assert "Limit Order Book Quotes" in str(quotes.layout.title.text)
    assert "Limit Order Book Liquidity" in str(liquidity.layout.title.text)
    assert "Order Flow" in str(order_flow.layout.title.text)
    assert "Double-Auction Allocative Efficiency" in str(
        allocative_efficiency.layout.title.text
    )


def test_log_return_figure_compares_market_and_fundamental_values(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_ids = [path.name for path in discover_run_directories(experiment_dir)]

    figure = make_market_fundamental_log_return_figure(experiment_dir, run_ids[:1])
    trace_names = {str(trace.name) for trace in figure.data}

    assert figure.data
    assert "Market and Fundamental Log Returns" in str(figure.layout.title.text)
    assert any("market" in trace_name for trace_name in trace_names)
    assert any("fundamental" in trace_name for trace_name in trace_names)


def test_log_return_histogram_stacks_agent_types_when_trade_data_available(
    tmp_path: Path,
) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dirs = discover_run_directories(experiment_dir)
    run_ids = [path.name for path in run_dirs]
    return_series_by_run = build_return_series_by_run(run_dirs)

    figure = make_return_histogram_figure(
        return_series_by_run,
        run_ids[:1],
        experiment_dir=experiment_dir,
    )
    trace_names = {str(trace.name) for trace in figure.data}

    assert figure.data
    assert "Log-Return Distribution by Agent Type" in str(figure.layout.title.text)
    assert figure.layout.barmode == "stack"
    assert {"fundamentalist", "chartist"}.issubset(trace_names)


def test_agent_figures_and_summary_use_final_agent_diagnostics(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_ids = [path.name for path in discover_run_directories(experiment_dir)]

    summary = build_agent_summary_statistics(experiment_dir, run_ids)
    portfolio = make_agent_portfolio_distribution_figure(experiment_dir, run_ids)
    return_lorenz = make_agent_return_lorenz_figure(experiment_dir, run_ids)
    activity = make_agent_trading_activity_figure(experiment_dir, run_ids)
    references = make_agent_reference_point_figure(experiment_dir, run_ids)
    gini = make_wealth_gini_timeseries_figure(experiment_dir, run_ids)

    assert not summary.empty
    assert "final_wealth_mean" in summary.columns
    assert "number_of_trades_mean" in summary.columns
    assert portfolio.data
    assert return_lorenz.data
    assert activity.data
    assert references.data
    assert gini.data
    assert "Agent Portfolio" in str(portfolio.layout.title.text)
    assert "Cumulative Agent Return Share" in str(return_lorenz.layout.title.text)
    assert "Agent Trading Activity" in str(activity.layout.title.text)
    assert "Agent Reference-Point" in str(references.layout.title.text)
    assert "Gini Coefficient" in str(gini.layout.title.text)


def test_agent_return_lorenz_figure_handles_legacy_archives_without_initial_wealth(
    tmp_path: Path,
) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dirs = discover_run_directories(experiment_dir)
    for run_dir in run_dirs:
        agents = pd.read_csv(run_dir / "agents_final.csv")
        agents = agents.drop(columns=["initial_wealth"])
        agents.to_csv(run_dir / "agents_final.csv", index=False)

    figure = make_agent_return_lorenz_figure(
        experiment_dir,
        [path.name for path in run_dirs],
    )

    assert not figure.data
    assert "No agent return data" in str(figure.layout.annotations[0].text)


def test_wealth_gini_figure_handles_legacy_archives_without_gini_column(
    tmp_path: Path,
) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dirs = discover_run_directories(experiment_dir)
    for run_dir in run_dirs:
        time_series = pd.read_csv(run_dir / "step_timeseries.csv")
        time_series = time_series.drop(columns=["wealth_gini_coefficient"])
        time_series.to_csv(run_dir / "step_timeseries.csv", index=False)

    figure = make_wealth_gini_timeseries_figure(
        experiment_dir,
        [path.name for path in run_dirs],
    )

    assert not figure.data
    assert "No wealth Gini" in str(figure.layout.annotations[0].text)


def test_allocative_efficiency_figure_handles_legacy_archives_without_metric_columns(
    tmp_path: Path,
) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dirs = discover_run_directories(experiment_dir)
    for run_dir in run_dirs:
        time_series = pd.read_csv(run_dir / "step_timeseries.csv")
        time_series = time_series.drop(
            columns=[
                "realized_allocative_surplus",
                "maximum_allocative_surplus",
                "allocative_efficiency",
            ]
        )
        time_series.to_csv(run_dir / "step_timeseries.csv", index=False)

    figure = make_allocative_efficiency_timeseries_figure(
        experiment_dir,
        [path.name for path in run_dirs],
    )

    assert not figure.data
    assert "No allocative-efficiency" in str(figure.layout.annotations[0].text)
