"""Tests for per-asset and cross-asset analytics.

The backward-compatibility tests here are the guard on the project's promise
that enabling the two-asset extension changes nothing for single-asset runs: a
run that declares a second asset but never trades it must be screened exactly
as a run from before the extension.
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
from abm_analysis.statistics.diagnostics import (
    build_return_series_by_asset,
    run_asset_stylised_fact_diagnostics,
)
from abm_analysis.statistics.robustness import merge_run_and_diagnostic_metrics

from abm_test_helpers import make_synthetic_experiment, write_synthetic_asset_timeseries

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

    beta = configuration.disabled_assets[0]
    assert beta.enabled is False
    assert beta.process_label == "Geometric Brownian motion"
    # The units differ between processes and are the most likely source of a
    # configuration error, so the resolved configuration must state them.
    assert beta.parameter_units == "per-step log return"


def test_disabled_asset_b_is_screened_as_a_single_asset_run(tmp_path: Path) -> None:
    """A run with Asset B disabled must be screened exactly as a one-asset run.

    The archive still declares Asset B and still carries a per-asset time
    series, but only Asset A traded. The gate is therefore the count of
    *recorded* assets, not the mere presence of the per-asset artefact: a
    declared-but-idle market must not open a cross-asset dimension.
    """

    disabled_run = _single_asset_run(tmp_path)
    write_synthetic_asset_timeseries(
        disabled_run,
        ["alpha"],
        disabled_assets=["beta"],
    )

    assert list_assets(disabled_run) == ["alpha"]
    assert load_multi_asset_configuration(disabled_run).is_multi_asset is False

    diagnostics = pd.DataFrame(run_asset_stylised_fact_diagnostics(disabled_run))
    assert diagnostics["asset"].astype(str).tolist() == ["alpha"]

    # The cross-asset dimension stays closed: a single recorded market has
    # nothing to correlate against and no ratio to take, even though the
    # per-asset artefact is present and names beta.
    assert compute_rolling_correlation(disabled_run).empty
    assert compute_price_ratio(disabled_run).empty


def test_both_assets_are_screened_on_equal_terms(tmp_path: Path) -> None:
    """Neither asset may be privileged in the stylised-fact layer.

    The primary asset is only a projection convenience for legacy tooling. Both
    markets must appear in the diagnostics table and in the return series, each
    screened on its own observations.
    """

    run_dir = _two_asset_run(tmp_path)

    diagnostics = pd.DataFrame(run_asset_stylised_fact_diagnostics(run_dir))
    assert sorted(diagnostics["asset"].astype(str)) == ["alpha", "beta"]
    # Each row is screened on its own observations, not a shared aggregate.
    assert diagnostics["observation_count"].gt(0).all()

    return_series = build_return_series_by_asset([run_dir])
    assert sorted(key.rsplit(" · ", 1)[-1] for key in return_series) == ["alpha", "beta"]
    for series in return_series.values():
        assert not series.empty


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
