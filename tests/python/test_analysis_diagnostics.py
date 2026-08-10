from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from abm_analysis.archive.data import discover_run_directories
from abm_analysis.statistics.diagnostics import (
    build_pairwise_ks_table,
    build_return_series_by_run,
    run_stylised_fact_diagnostics,
)
from abm_analysis.statistics.robustness import build_seed_robustness_summary
from abm_analysis.statistics.stress import annotate_stress_regimes

from abm_test_helpers import make_synthetic_experiment


def test_stylised_fact_diagnostics_emit_required_columns(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dir = discover_run_directories(experiment_dir)[0]

    diagnostics = run_stylised_fact_diagnostics(run_dir)

    required_columns = {
        "run_id",
        "observation_count",
        "jarque_bera_p_value",
        "minimum_ljung_box_p_value",
        "minimum_arch_lm_p_value",
        "garch_available",
        "autocorrelation_conclusion",
        "fat_tail_conclusion",
        "volatility_clustering_conclusion",
    }
    assert required_columns.issubset(diagnostics)
    assert diagnostics["diagnostic_status"] == "completed"
    assert np.isfinite(diagnostics["jarque_bera_p_value"])
    assert np.isfinite(diagnostics["minimum_ljung_box_p_value"])
    assert np.isfinite(diagnostics["minimum_arch_lm_p_value"])


def test_pairwise_ks_table_compares_return_distributions(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dirs = discover_run_directories(experiment_dir)
    returns_by_run = build_return_series_by_run(run_dirs)

    pairwise = build_pairwise_ks_table(returns_by_run)

    assert len(pairwise) == 1
    assert pairwise.iloc[0]["status"] == "completed"
    assert 0 <= pairwise.iloc[0]["ks_statistic"] <= 1
    assert 0 <= pairwise.iloc[0]["ks_p_value"] <= 1


def test_stress_regime_detection_flags_volatility_spikes_and_drawdowns() -> None:
    low_volatility = np.full(45, 0.001)
    stress_shocks = np.array([0.06, -0.08, 0.07, -0.12, 0.03, -0.06, 0.04, -0.05, 0.02, -0.04])
    recovery = np.full(45, 0.001)
    returns = np.r_[low_volatility, stress_shocks, recovery]
    prices = 100.0 * np.exp(np.cumsum(returns))
    data = pd.DataFrame({"market_price": prices})

    annotated = annotate_stress_regimes(data, price_column="market_price")

    assert "rolling_volatility" in annotated.columns
    assert "drawdown" in annotated.columns
    assert annotated["stress_regime"].any()
    assert annotated.loc[45:55, "stress_regime"].mean() > 0


def test_seed_robustness_groups_replicates_by_condition_not_seed() -> None:
    runs_index = pd.DataFrame(
        [
            {
                "run_id": "run_seed_1",
                "seed": 1,
                "time_steps": 100,
                "num_fundamentalists": 20,
                "num_chartists": 30,
                "num_noise_traders": 5,
                "num_buy_and_hold_agents": 2,
                "buy_hold_target_risky_weight": 0.60,
                "control_prospect_theory_enabled": 1,
                "control_prospect_heterogeneity_enabled": 1,
                "social_enabled": 1,
                "short_selling_enabled": 1,
                "max_drawdown": 0.10,
            },
            {
                "run_id": "run_seed_2",
                "seed": 2,
                "time_steps": 100,
                "num_fundamentalists": 20,
                "num_chartists": 30,
                "num_noise_traders": 5,
                "num_buy_and_hold_agents": 2,
                "buy_hold_target_risky_weight": 0.60,
                "control_prospect_theory_enabled": 1,
                "control_prospect_heterogeneity_enabled": 1,
                "social_enabled": 1,
                "short_selling_enabled": 1,
                "max_drawdown": 0.20,
            },
        ]
    )
    diagnostics = pd.DataFrame(
        [
            {
                "run_id": "run_seed_1",
                "log_return_std_dev": 0.01,
                "excess_kurtosis": 1.0,
                "fat_tail_conclusion": "Consistent with fat-tailed returns",
                "volatility_clustering_conclusion": "Consistent with volatility clustering",
                "autocorrelation_conclusion": "Consistent with absence of autocorrelation",
            },
            {
                "run_id": "run_seed_2",
                "log_return_std_dev": 0.03,
                "excess_kurtosis": 3.0,
                "fat_tail_conclusion": "Consistent with fat-tailed returns",
                "volatility_clustering_conclusion": "Consistent with volatility clustering",
                "autocorrelation_conclusion": "Evidence of return autocorrelation",
            },
        ]
    )

    summary = build_seed_robustness_summary(runs_index, diagnostics)

    assert len(summary) == 1
    assert summary.iloc[0]["run_count"] == 2
    assert summary.iloc[0]["seed_count"] == 2
    # Tables and chart axes use the short identifier; the full key=value
    # listing survives in condition_description for CSV reproducibility.
    assert summary.iloc[0]["condition_id"] == "condition_1"
    assert "num_fundamentalists=20" in summary.iloc[0]["condition_description"]
    assert summary.iloc[0]["log_return_std_dev_mean"] == pytest.approx(0.02)
    assert summary.iloc[0]["fat_tail_success_rate"] == pytest.approx(1.0)
    assert summary.iloc[0]["weak_autocorrelation_success_rate"] == pytest.approx(0.5)
