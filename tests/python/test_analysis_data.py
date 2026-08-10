from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from abm_analysis.archive.data import (
    build_run_archive,
    build_runs_index,
    compute_log_returns,
    discover_run_directories,
    ensure_valid_run_archive,
    normalise_manifest_schema,
    parse_run_id,
    prepare_return_series,
    validate_run_archive,
)

from abm_test_helpers import make_synthetic_experiment, write_synthetic_run


def test_parse_run_id_uses_project_numeric_schema() -> None:
    parsed = parse_run_id("20260427143012_1_1_0_1_100_1500_25_10_1000_66")

    assert parsed["run_id_schema_valid"] is True
    assert parsed["run_id_created_at_local"] == "2026-04-27T14:30:12"
    assert parsed["run_id_prospect_theory_enabled"] == 1
    assert parsed["run_id_prospect_heterogeneity_enabled"] == 1
    assert parsed["run_id_social_enabled"] == 0
    assert parsed["run_id_short_selling_enabled"] == 1
    assert parsed["run_id_num_fundamentalists"] == 100
    assert parsed["run_id_num_chartists"] == 1500
    assert parsed["run_id_num_noise_traders"] == 25
    assert parsed["run_id_num_buy_and_hold_agents"] == 10
    assert parsed["run_id_time_steps"] == 1000
    assert parsed["run_id_seed"] == 66


def test_parse_run_id_keeps_pre_buy_hold_schema_parseable() -> None:
    parsed = parse_run_id("20260427143012_1_1_0_1_100_1500_25_1000_66")

    assert parsed["run_id_schema_valid"] is True
    assert parsed["run_id_num_noise_traders"] == 25
    assert parsed["run_id_num_buy_and_hold_agents"] == 0
    assert parsed["run_id_time_steps"] == 1000
    assert parsed["run_id_seed"] == 66


def test_parse_run_id_keeps_legacy_schema_parseable() -> None:
    parsed = parse_run_id("20260427143012_1_1_0_1_100_1500_1000_66")

    assert parsed["run_id_schema_valid"] is True
    assert parsed["run_id_num_noise_traders"] == 0
    assert parsed["run_id_num_buy_and_hold_agents"] == 0
    assert parsed["run_id_time_steps"] == 1000
    assert parsed["run_id_seed"] == 66


def test_discovery_and_runs_index_normalise_summary_schema(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)

    run_dirs = discover_run_directories(experiment_dir)
    runs_index = build_runs_index(experiment_dir)
    first_timeseries = pd.read_csv(run_dirs[0] / "step_timeseries.csv")

    assert len(run_dirs) == 2
    assert set(runs_index["run_id"]) == {path.name for path in run_dirs}
    assert "control_prospect_theory_enabled" in runs_index.columns
    assert "num_noise_traders" in runs_index.columns
    assert "num_buy_and_hold_agents" in runs_index.columns
    assert "run_directory" in runs_index.columns
    assert "final_wealth_gini_coefficient" in runs_index.columns
    assert runs_index["final_wealth_gini_coefficient"].between(0.0, 1.0).all()
    assert "mean_allocative_efficiency" in runs_index.columns
    assert runs_index["mean_allocative_efficiency"].between(0.0, 1.0).all()
    assert "wealth_gini_coefficient" in first_timeseries.columns
    assert first_timeseries["wealth_gini_coefficient"].between(0.0, 1.0).all()
    assert "allocative_efficiency" in first_timeseries.columns
    assert first_timeseries["allocative_efficiency"].between(0.0, 1.0).all()


def test_manifest_normalisation_keeps_complete_integer_summary_rows() -> None:
    summary = pd.DataFrame(
        [
            {
                "run_id": pd.NA,
                "prospect_theory_enabled": 0,
                "prospect_heterogeneity_enabled": 1,
                "social_enabled": 1,
                "short_selling_enabled": 1,
                "num_noise_traders": 1000,
                "num_buy_and_hold_agents": 100,
            }
        ]
    )

    normalised = normalise_manifest_schema(summary)

    assert normalised.loc[0, "control_prospect_theory_enabled"] == 0
    assert normalised.loc[0, "control_prospect_heterogeneity_enabled"] == 1
    assert normalised.loc[0, "num_noise_traders"] == 1000
    assert normalised.loc[0, "num_buy_and_hold_agents"] == 100


def test_runs_index_uses_directory_name_when_summary_run_id_is_blank(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "latest_experiment"
    experiment_dir.mkdir()
    write_synthetic_run(experiment_dir / "latest", "", 333, 0.0)

    runs_index = build_runs_index(experiment_dir)

    assert runs_index.loc[0, "run_id"] == "latest"
    assert runs_index.loc[0, "run_directory"] == "latest"
    assert pd.notna(runs_index.loc[0, "final_market_price"])


def test_run_archive_validation_accepts_missing_optional_trade_ledger(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dir = discover_run_directories(experiment_dir)[0]
    (run_dir / "trade_ledger.csv").unlink()

    validation = validate_run_archive(run_dir)
    archive = build_run_archive(run_dir)
    enforced_archive = ensure_valid_run_archive(run_dir)

    assert validation.is_valid
    assert validation.errors == ()
    assert archive.trade_ledger_csv is None
    assert enforced_archive.trade_ledger_csv is None


def test_run_archive_validation_reports_required_step_schema_errors(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dir = discover_run_directories(experiment_dir)[0]
    step_timeseries = pd.read_csv(run_dir / "step_timeseries.csv")
    step_timeseries.drop(columns=["market_price"]).to_csv(
        run_dir / "step_timeseries.csv",
        index=False,
    )

    validation = validate_run_archive(run_dir)

    assert not validation.is_valid
    assert any(
        "step_timeseries.csv is missing required columns" in error
        for error in validation.errors
    )
    with pytest.raises(ValueError, match="step_timeseries.csv"):
        ensure_valid_run_archive(run_dir)


def test_run_archive_validation_keeps_legacy_ids_loadable(tmp_path: Path) -> None:
    legacy_run_dir = tmp_path / "20260427143012_1_1_0_1_20_30_180_66"
    write_synthetic_run(legacy_run_dir, legacy_run_dir.name, 66, 0.0)

    validation = validate_run_archive(legacy_run_dir)

    assert validation.is_valid
    assert any("legacy run-id schema" in warning for warning in validation.warnings)


def test_log_return_calculation_keeps_initial_invalid_observation_visible(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dir = discover_run_directories(experiment_dir)[0]

    returns = prepare_return_series(run_dir, phase="simulation")
    direct_returns = compute_log_returns(pd.Series([100.0, 105.0, 0.0, 106.0]))

    assert len(returns) >= 100
    assert np.isfinite(returns).all()
    assert pd.isna(direct_returns.iloc[0])
    assert pd.isna(direct_returns.iloc[2])
    assert pd.isna(direct_returns.iloc[3])
