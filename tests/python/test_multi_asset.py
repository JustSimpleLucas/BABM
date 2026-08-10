"""Tests for per-asset and cross-asset analytics and the multi-asset report panels.

The backward-compatibility tests here are the guard on the project's promise
that enabling the two-asset extension changes nothing for single-asset runs:
with one asset the report must contain exactly the figures and sections it
contained before the extension.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from abm_analysis.statistics.multi_asset import (
    compute_portfolio_composition,
    compute_price_ratio,
    compute_realised_volatility,
    compute_rolling_correlation,
    list_assets,
    load_asset_panel,
    load_multi_asset_configuration,
)
from abm_analysis.plots.multi_asset import (
    build_asset_configuration_table,
    make_asset_allocative_efficiency_figure,
    make_asset_microstructure_liquidity_figure,
    make_asset_microstructure_quotes_figure,
    make_asset_order_flow_figure,
    make_asset_price_fundamental_figure,
    make_asset_return_path_figure,
    make_cross_asset_figure,
    make_portfolio_composition_figure,
)
from abm_analysis.statistics.diagnostics import run_asset_stylised_fact_diagnostics
from abm_analysis.report import build_run_report
from abm_analysis.report.figures import multi_asset_figures, per_asset_core_figures
from abm_analysis.statistics.robustness import merge_run_and_diagnostic_metrics

from abm_test_helpers import make_synthetic_experiment, write_synthetic_asset_timeseries

# Figures that exist only once a second risky asset trades. These are the joint
# quantities; the per-asset panels reuse the core figure names instead.
CROSS_ASSET_FIGURE_NAMES = {
    "cross_asset_dependence",
    "portfolio_composition",
}

# Core figures that a multi-asset run rebuilds per asset under the same name.
PER_ASSET_CORE_FIGURE_NAMES = {
    "price_timeseries",
    "market_fundamental_log_returns",
    "trade_volume",
    "microstructure_quotes",
    "microstructure_liquidity",
    "order_flow_microstructure",
    "allocative_efficiency_timeseries",
}


def _single_asset_run(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    experiment_dir = make_synthetic_experiment(tmp_path)
    return sorted(experiment_dir.iterdir())[0]


def _two_asset_run(tmp_path: Path, **kwargs) -> Path:
    run_dir = _single_asset_run(tmp_path)
    write_synthetic_asset_timeseries(run_dir, ["alpha", "beta"], **kwargs)
    return run_dir


def test_list_assets_preserves_declared_order(tmp_path: Path) -> None:
    run_dir = _two_asset_run(tmp_path)

    # Declared order, not alphabetical order, keeps Asset A ahead of Asset B.
    assert list_assets(run_dir) == ["alpha", "beta"]


def test_single_asset_run_reports_no_assets(tmp_path: Path) -> None:
    run_dir = _single_asset_run(tmp_path)

    assert list_assets(run_dir) == []
    assert load_asset_panel(run_dir, "market_price").empty


def test_asset_panel_pivots_long_format_to_wide(tmp_path: Path) -> None:
    run_dir = _two_asset_run(tmp_path)

    prices = load_asset_panel(run_dir, "market_price")

    assert list(prices.columns) == ["alpha", "beta"]
    assert prices.index.name == "simulation_step"
    assert not prices.empty


def test_portfolio_composition_sums_to_one(tmp_path: Path) -> None:
    run_dir = _two_asset_run(tmp_path)

    composition = compute_portfolio_composition(run_dir)

    assert list(composition.columns) == ["alpha", "beta", "cash"]
    # Cash is derived as the residual, so the rows must sum to one exactly.
    assert np.allclose(composition.sum(axis=1), 1.0)


def test_rolling_correlation_and_price_ratio_are_derived(tmp_path: Path) -> None:
    run_dir = _two_asset_run(tmp_path)

    correlation = compute_rolling_correlation(run_dir, window=20)
    ratio = compute_price_ratio(run_dir)

    assert not correlation.empty
    finite_correlation = correlation.dropna()
    assert not finite_correlation.empty
    assert finite_correlation.between(-1.0, 1.0).all()
    assert not ratio.empty
    assert (ratio.dropna() > 0).all()


def test_realised_volatility_is_non_negative_per_asset(tmp_path: Path) -> None:
    run_dir = _two_asset_run(tmp_path)

    volatility = compute_realised_volatility(run_dir, window=20)

    assert list(volatility.columns) == ["alpha", "beta"]
    assert (volatility.dropna() >= 0).all().all()


def test_cross_asset_metrics_are_empty_for_one_asset(tmp_path: Path) -> None:
    run_dir = _single_asset_run(tmp_path)
    write_synthetic_asset_timeseries(run_dir, ["alpha"])

    assert compute_rolling_correlation(run_dir).empty
    assert compute_price_ratio(run_dir).empty


def test_configuration_records_process_units_and_disabled_assets(tmp_path: Path) -> None:
    run_dir = _single_asset_run(tmp_path)
    write_synthetic_asset_timeseries(
        run_dir,
        ["alpha"],
        disabled_assets=["beta"],
        processes={"beta": "gbm"},
    )

    configuration = load_multi_asset_configuration(run_dir)

    assert [asset.name for asset in configuration.assets] == ["alpha"]
    assert [asset.name for asset in configuration.disabled_assets] == ["beta"]
    assert configuration.is_multi_asset is False

    table = build_asset_configuration_table(run_dir)
    beta_row = table[table["Asset"] == "beta"].iloc[0]
    assert beta_row["Enabled"] == "no"
    assert beta_row["Fundamental process"] == "Geometric Brownian motion"
    # The units differ between processes and are the most likely source of a
    # configuration error, so the table must state them.
    assert beta_row["Drift & shock units"] == "per-step log return"


def test_multi_asset_figures_are_built_only_for_multiple_assets(tmp_path: Path) -> None:
    two_asset_dir = _two_asset_run(tmp_path)
    assert set(multi_asset_figures(two_asset_dir, phase="simulation")) == (
        CROSS_ASSET_FIGURE_NAMES
    )
    assert set(per_asset_core_figures(two_asset_dir, phase="simulation")) == (
        PER_ASSET_CORE_FIGURE_NAMES
    )

    single_asset_dir = _single_asset_run(tmp_path / "single")
    assert multi_asset_figures(single_asset_dir, phase="simulation") == {}
    assert per_asset_core_figures(single_asset_dir, phase="simulation") == {}


def test_disabled_asset_b_leaves_pre_existing_report_unchanged(tmp_path: Path) -> None:
    """A run with Asset B disabled must reproduce the single-asset report.

    The archive still declares Asset B and still carries a per-asset time
    series, but only Asset A traded. No multi-asset figure may be produced and
    no multi-asset section may appear, so the report is identical in structure
    to one from a run that never declared a second asset.
    """

    baseline_run = _single_asset_run(tmp_path / "baseline")
    baseline = build_run_report(
        baseline_run,
        output_dir=tmp_path / "baseline_report",
        source="files",
    )
    baseline_figures = pd.read_csv(baseline.figure_index_csv_path)["figure_name"].tolist()

    disabled_run = _single_asset_run(tmp_path / "disabled")
    write_synthetic_asset_timeseries(
        disabled_run,
        ["alpha"],
        disabled_assets=["beta"],
    )
    disabled = build_run_report(
        disabled_run,
        output_dir=tmp_path / "disabled_report",
        source="files",
    )
    disabled_figures = pd.read_csv(disabled.figure_index_csv_path)["figure_name"].tolist()

    assert disabled_figures == baseline_figures
    assert not CROSS_ASSET_FIGURE_NAMES.intersection(disabled_figures)

    disabled_html = disabled.report_path.read_text(encoding="utf-8")
    assert "multi-asset-dynamics" not in disabled_html
    assert "Cross-Asset Dynamics" not in disabled_html


def test_enabled_asset_b_adds_the_cross_asset_section(tmp_path: Path) -> None:
    run_dir = _two_asset_run(tmp_path)

    result = build_run_report(
        run_dir,
        output_dir=tmp_path / "two_asset_report",
        source="files",
    )

    figures = pd.read_csv(result.figure_index_csv_path)["figure_name"].tolist()
    assert CROSS_ASSET_FIGURE_NAMES.issubset(figures)
    # The core figure names survive: they are rebuilt per asset rather than
    # duplicated under new names, so section layout and exports are unchanged.
    assert PER_ASSET_CORE_FIGURE_NAMES.issubset(figures)

    html = result.report_path.read_text(encoding="utf-8")
    assert "Cross-Asset Dynamics" in html
    assert "Asset Configuration" in html


def test_both_assets_are_screened_and_plotted_on_equal_terms(tmp_path: Path) -> None:
    """Neither asset may be privileged in the report's stylised-fact layer.

    The primary asset is only a projection convenience for legacy tooling. Both
    markets must appear in the diagnostics table, in the exported returns, and
    in the evidence cards, each with its own verdict.
    """

    run_dir = _two_asset_run(tmp_path)

    result = build_run_report(
        run_dir,
        output_dir=tmp_path / "equal_terms_report",
        source="files",
    )

    diagnostics = pd.read_csv(result.diagnostics_csv_path)
    assert sorted(diagnostics["asset"].astype(str)) == ["alpha", "beta"]
    # Each row is screened on its own observations, not a shared aggregate.
    assert diagnostics["observation_count"].gt(0).all()

    returns = pd.read_csv(result.returns_csv_path)
    assert sorted(returns["asset"].astype(str).unique()) == ["alpha", "beta"]

    html = result.report_path.read_text(encoding="utf-8")
    for asset in ("alpha", "beta"):
        assert f"Fat-tailed returns — {asset}" in html
        assert f"Volatility clustering — {asset}" in html
        assert f"Weak raw-return autocorrelation — {asset}" in html


def test_per_asset_metrics_are_not_shadowed_by_run_level_columns(tmp_path: Path) -> None:
    """Run-level summary metrics must not overwrite per-asset diagnostics.

    ``summary_metrics.csv`` records kurtosis, drawdown, and volume for the
    primary asset only. The robustness merge previously preferred those columns
    whenever a name collided, which silently reported alpha's path statistics on
    beta's row — the exact asymmetry per-asset diagnostics exist to remove.
    """

    run_dir = _two_asset_run(tmp_path)
    diagnostics = pd.DataFrame(run_asset_stylised_fact_diagnostics(run_dir))
    runs_index = pd.DataFrame(
        [
            {
                "run_id": run_dir.name,
                "seed": 55,
                "excess_kurtosis": 999.0,
                "max_drawdown": 999.0,
                "total_traded_volume": 999.0,
            }
        ]
    )

    merged = merge_run_and_diagnostic_metrics(runs_index, diagnostics)

    assert sorted(merged["asset"].astype(str)) == ["alpha", "beta"]
    for column in ("excess_kurtosis", "max_drawdown", "total_traded_volume"):
        assert (merged[column] != 999.0).all(), f"{column} came from the run-level row"
        # Two independent markets: identical values would mean one was copied.
        assert merged[column].nunique() == 2


@pytest.mark.parametrize(
    "figure_builder",
    [
        make_asset_price_fundamental_figure,
        make_asset_return_path_figure,
        make_asset_microstructure_quotes_figure,
        make_asset_microstructure_liquidity_figure,
        make_asset_order_flow_figure,
        make_asset_allocative_efficiency_figure,
        make_cross_asset_figure,
        make_portfolio_composition_figure,
    ],
)
def test_figures_degrade_gracefully_without_asset_data(tmp_path: Path, figure_builder) -> None:
    """Figure builders must return a placeholder rather than raise.

    Reports are generated for archives of every vintage, so a builder that
    raised on a pre-extension run would break report generation entirely.
    """

    run_dir = _single_asset_run(tmp_path)

    figure = figure_builder(run_dir)

    assert figure is not None
    assert figure.layout.annotations  # placeholder message is present
