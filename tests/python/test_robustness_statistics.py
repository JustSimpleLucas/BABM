from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from abm_analysis.statistics.robustness_tests import (
    build_adf_stationarity_table,
    build_cross_seed_distribution_tests,
    summarise_adf_rejections,
    summarise_pairwise_ks,
)
from abm_analysis.statistics.robustness_verdicts import (
    MINIMUM_SEEDS_FOR_VERDICTS,
    VerdictThresholds,
    build_robustness_verdicts,
    verdict_rows_for_report,
)
from abm_analysis.statistics.seed_convergence import (
    build_seed_convergence_table,
    final_relative_ci_half_widths,
)


def _same_distribution_series(count: int = 3, length: int = 300) -> dict[str, pd.Series]:
    rng = np.random.default_rng(20260708)
    return {
        f"run_{index}": pd.Series(rng.normal(0.0, 0.01, size=length))
        for index in range(count)
    }


def test_cross_seed_distribution_tests_complete_for_same_distribution() -> None:
    tests = build_cross_seed_distribution_tests(_same_distribution_series())

    assert set(tests["test_name"]) == {
        "anderson_darling_ksample",
        "kruskal_wallis",
        "levene_brown_forsythe",
    }
    assert set(tests["status"]) == {"completed"}
    assert tests["statistic"].apply(np.isfinite).all()
    assert tests["p_value"].apply(np.isfinite).all()
    assert (tests["sample_count"] == 3).all()
    # Same-distribution draws with a fixed generator seed must not reject.
    assert not tests["rejects_null"].any()


def test_anderson_darling_capped_p_value_is_displayed_as_bound() -> None:
    tests = build_cross_seed_distribution_tests(_same_distribution_series())
    ad_row = tests[tests["test_name"] == "anderson_darling_ksample"].iloc[0]

    # SciPy caps AD k-sample p-values to [0.001, 0.25]; identically
    # distributed samples land on the upper cap, which must be shown as a
    # bound rather than an exact probability.
    assert bool(ad_row["p_value_is_capped"])
    assert ad_row["p_value_display"] == ">= 0.25"


def test_cross_seed_distribution_tests_flag_degenerate_samples() -> None:
    constant_series = {
        "run_a": pd.Series(np.zeros(120)),
        "run_b": pd.Series(np.zeros(120)),
    }

    tests = build_cross_seed_distribution_tests(constant_series)

    assert set(tests["status"]) == {"degenerate_samples"}
    assert tests["p_value"].isna().all()


def test_cross_seed_distribution_tests_require_two_usable_series() -> None:
    rng = np.random.default_rng(1)
    single = {"run_a": pd.Series(rng.normal(size=200))}
    short_pair = {
        "run_a": pd.Series(rng.normal(size=200)),
        "run_b": pd.Series(rng.normal(size=10)),
    }

    assert build_cross_seed_distribution_tests(single).empty
    assert build_cross_seed_distribution_tests(short_pair).empty


def test_summarise_pairwise_ks_computes_share_and_means() -> None:
    pairwise = pd.DataFrame(
        {
            "ks_statistic": [0.1, 0.2, 0.3],
            "ks_p_value": [0.50, 0.01, 0.20],
        }
    )

    summary = summarise_pairwise_ks(pairwise)

    assert summary["pair_count"] == 3
    assert summary["mean_ks_statistic"] == pytest.approx(0.2)
    assert summary["median_ks_statistic"] == pytest.approx(0.2)
    assert summary["insignificant_share"] == pytest.approx(2.0 / 3.0)


def test_summarise_pairwise_ks_handles_missing_results() -> None:
    summary = summarise_pairwise_ks(pd.DataFrame())

    assert summary["pair_count"] == 0
    assert np.isnan(summary["insignificant_share"])


def test_adf_rejects_unit_root_for_stationary_noise() -> None:
    rng = np.random.default_rng(20260708)
    series_by_run = {
        "run_a": pd.Series(rng.normal(0.0, 0.01, size=400)),
        "run_b": pd.Series(rng.normal(0.0, 0.01, size=400)),
    }

    adf_table = build_adf_stationarity_table(
        series_by_run,
        {"run_a": 55, "run_b": 66},
    )
    summary = summarise_adf_rejections(adf_table)

    assert set(adf_table["status"]) == {"completed"}
    assert adf_table["rejects_unit_root"].all()
    assert list(adf_table["seed"]) == [55, 66]
    assert summary["tested_seed_count"] == 2
    assert summary["rejection_rate"] == pytest.approx(1.0)


def test_adf_reports_insufficient_observations_for_short_series() -> None:
    adf_table = build_adf_stationarity_table({"run_a": pd.Series(np.random.default_rng(2).normal(size=20))})

    assert adf_table.iloc[0]["status"] == "insufficient_observations"
    assert np.isnan(adf_table.iloc[0]["adf_p_value"])
    assert np.isnan(summarise_adf_rejections(adf_table)["rejection_rate"])


def test_seed_convergence_matches_manual_running_statistics() -> None:
    runs_index = pd.DataFrame(
        {
            "run_id": ["run_b", "run_a", "run_c"],
            "seed": [66, 55, 77],
            "max_drawdown": [0.2, 0.1, 0.3],
        }
    )

    table = build_seed_convergence_table(runs_index, pd.DataFrame(), metrics=("max_drawdown",))

    # Rows must accumulate in ascending seed order (55, 66, 77), not in the
    # frame's original order.
    assert list(table["newest_seed"]) == [55, 66, 77]
    assert list(table["seed_count"]) == [1, 2, 3]
    assert table.iloc[0]["running_mean"] == pytest.approx(0.1)
    assert np.isnan(table.iloc[0]["running_std"])
    assert np.isnan(table.iloc[0]["ci95_half_width"])
    assert table.iloc[1]["running_mean"] == pytest.approx(0.15)
    assert table.iloc[1]["running_std"] == pytest.approx(np.std([0.1, 0.2], ddof=1))
    assert table.iloc[2]["running_mean"] == pytest.approx(0.2)
    expected_half_width = 1.96 * np.std([0.1, 0.2, 0.3], ddof=1) / np.sqrt(3)
    assert table.iloc[2]["ci95_half_width"] == pytest.approx(expected_half_width)
    assert table.iloc[2]["relative_ci95_half_width"] == pytest.approx(expected_half_width / 0.2)

    final_widths = final_relative_ci_half_widths(table)
    assert final_widths["max_drawdown"] == pytest.approx(expected_half_width / 0.2)


def test_seed_convergence_requires_seed_column() -> None:
    runs_index = pd.DataFrame({"run_id": ["run_a"], "max_drawdown": [0.1]})

    assert build_seed_convergence_table(runs_index, pd.DataFrame()).empty


def _verdict_inputs(
    *,
    cov_value: float,
    success_rate: float,
    insignificant_share: float,
    rejection_rate: float,
) -> dict[str, object]:
    seed_summary = pd.DataFrame(
        [
            {
                "condition_id": "all_runs",
                "log_return_std_dev_coefficient_of_variation": cov_value,
                "excess_kurtosis_coefficient_of_variation": cov_value,
                "max_drawdown_coefficient_of_variation": cov_value,
                "total_traded_volume_coefficient_of_variation": cov_value,
                "fat_tail_success_rate": success_rate,
                "volatility_clustering_success_rate": success_rate,
                "weak_autocorrelation_success_rate": success_rate,
            }
        ]
    )
    distribution_tests = pd.DataFrame(
        [
            {
                "test_name": "kruskal_wallis",
                "null_hypothesis": "equal locations",
                "statistic": 1.0,
                "p_value": 0.60,
                "p_value_display": "0.6000",
                "status": "completed",
            }
        ]
    )
    ks_summary = {"pair_count": 10, "insignificant_share": insignificant_share}
    adf_summary = {"tested_seed_count": 10, "rejection_rate": rejection_rate}
    convergence = pd.DataFrame(
        {
            "metric": ["log_return_std_dev", "excess_kurtosis", "max_drawdown"],
            "seed_count": [10, 10, 10],
            "relative_ci95_half_width": [0.05, 0.05, 0.05],
        }
    )
    return {
        "seed_summary": seed_summary,
        "distribution_tests": distribution_tests,
        "ks_summary": ks_summary,
        "adf_summary": adf_summary,
        "convergence_table": convergence,
    }


def test_verdicts_pass_borderline_and_fail_map_to_thresholds() -> None:
    passing = build_robustness_verdicts(
        **_verdict_inputs(
            cov_value=0.05,
            success_rate=0.9,
            insignificant_share=0.9,
            rejection_rate=1.0,
        ),
        seed_count=10,
    )
    assert set(passing["verdict"]) == {"pass"}

    borderline = build_robustness_verdicts(
        **_verdict_inputs(
            cov_value=0.2,
            success_rate=0.7,
            insignificant_share=0.6,
            rejection_rate=0.8,
        ),
        seed_count=10,
    )
    cov_rows = borderline[borderline["category"] == "metric_stability"]
    assert set(cov_rows["verdict"]) == {"borderline"}

    failing = build_robustness_verdicts(
        **_verdict_inputs(
            cov_value=0.5,
            success_rate=0.3,
            insignificant_share=0.2,
            rejection_rate=0.4,
        ),
        seed_count=10,
    )
    assert set(failing[failing["category"] == "metric_stability"]["verdict"]) == {"fail"}
    assert set(
        failing[failing["category"] == "stylised_fact_reproducibility"]["verdict"]
    ) == {"fail"}


def test_build_robustness_verdicts_accepts_custom_thresholds() -> None:
    inputs = _verdict_inputs(
        cov_value=0.05,
        success_rate=0.9,
        insignificant_share=0.9,
        rejection_rate=1.0,
    )

    default_verdicts = build_robustness_verdicts(**inputs, seed_count=10)
    explicit_default_verdicts = build_robustness_verdicts(
        **inputs,
        seed_count=10,
        thresholds=VerdictThresholds(),
    )
    pd.testing.assert_frame_equal(default_verdicts, explicit_default_verdicts)
    assert set(default_verdicts["verdict"]) == {"pass"}

    strict = build_robustness_verdicts(
        **inputs,
        seed_count=10,
        thresholds=VerdictThresholds(
            cov_pass=0.01,
            cov_borderline=0.02,
            success_rate_pass=0.95,
            success_rate_borderline=0.85,
        ),
    )
    assert set(strict[strict["category"] == "metric_stability"]["verdict"]) == {"fail"}
    assert set(
        strict[strict["category"] == "stylised_fact_reproducibility"]["verdict"]
    ) == {"borderline"}
    # Configured thresholds must self-document in the decision-rule text.
    cov_descriptions = strict[strict["category"] == "metric_stability"][
        "threshold_description"
    ]
    assert all("0.01" in description for description in cov_descriptions)
    # Untouched criteria keep their default verdicts.
    assert set(strict[strict["category"] == "stationarity"]["verdict"]) == {"pass"}

    raised_minimum = build_robustness_verdicts(
        **inputs,
        seed_count=10,
        thresholds=VerdictThresholds(minimum_seeds_for_verdicts=12),
    )
    assert set(raised_minimum["verdict"]) == {"not_available"}


def test_verdicts_are_not_available_below_minimum_seed_count() -> None:
    verdicts = build_robustness_verdicts(
        **_verdict_inputs(
            cov_value=0.05,
            success_rate=0.9,
            insignificant_share=0.9,
            rejection_rate=1.0,
        ),
        seed_count=MINIMUM_SEEDS_FOR_VERDICTS - 1,
    )

    assert set(verdicts["verdict"]) == {"not_available"}


def test_verdicts_tolerate_missing_inputs() -> None:
    verdicts = build_robustness_verdicts(
        pd.DataFrame(),
        pd.DataFrame(),
        {},
        {},
        pd.DataFrame(),
        seed_count=10,
    )

    assert not verdicts.empty
    assert set(verdicts["verdict"]) == {"not_available"}


def test_verdict_rows_for_report_match_evidence_schema() -> None:
    verdicts = build_robustness_verdicts(
        **_verdict_inputs(
            cov_value=0.05,
            success_rate=0.9,
            insignificant_share=0.9,
            rejection_rate=1.0,
        ),
        seed_count=10,
    )

    cards = verdict_rows_for_report(verdicts)

    assert len(cards) == len(verdicts)
    for card in cards:
        assert set(card) == {
            "fact",
            "verdict",
            "tone",
            "hypothesis",
            "quantitative_evidence",
            "interpretation",
        }
        assert card["verdict"] == "Pass"
        assert card["tone"] == "teal"
