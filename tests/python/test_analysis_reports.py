from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from abm_analysis.archive.data import discover_run_directories
from abm_analysis.report import build_comparison_report, build_run_report
from abm_analysis.report.evidence import (
    build_comparison_evidence_assessment,
    build_run_evidence_assessment,
)

from abm_test_helpers import make_synthetic_benchmark_dir, make_synthetic_experiment


def test_report_generation_works_on_existing_demo_data(tmp_path: Path) -> None:
    demo_dir = Path("data/experiments/demo")
    if not demo_dir.is_dir():
        pytest.skip("Local demo experiment data are not available.")

    demo_runs = discover_run_directories(demo_dir)
    if len(demo_runs) < 2:
        pytest.skip("At least two demo runs are required for comparison report coverage.")

    demo_subset = tmp_path / "demo_subset"
    demo_subset.mkdir()
    for run_dir in demo_runs[:2]:
        os.symlink(run_dir.resolve(), demo_subset / run_dir.name)

    result = build_comparison_report(
        demo_subset,
        output_dir=tmp_path / "comparison_report",
        max_runs=2,
    )

    assert result.report_path.is_file()
    assert result.runs_index_csv_path.is_file()
    assert result.diagnostics_csv_path.is_file()
    assert result.pairwise_ks_csv_path.is_file()
    assert result.agent_summary_csv_path is not None
    assert result.agent_summary_csv_path.is_file()
    report_html = result.report_path.read_text(encoding="utf-8")
    assert "ABM Experiment Comparison" in report_html
    assert "Data Label Notes" in report_html
    assert "Data 1" in report_html
    assert "Data 2" in report_html
    for run_dir in demo_runs[:2]:
        assert run_dir.name in report_html
    assert "Limit Order Book Liquidity" in report_html
    assert "Order Flow and Book Lifecycle" in report_html
    assert "Market and Fundamental Log Returns" in report_html
    assert "Agent Portfolio Distributions" in report_html
    assert "Agent Trading Activity" in report_html
    assert "Agent Summary Statistics" in report_html
    assert "Mean Allocative Efficiency" in report_html
    assert "Market Dynamics" in report_html
    assert "Agent Outcomes" in report_html
    assert "Visual Diagnostics" not in report_html
    assert report_html.index("Data Label Notes") > report_html.index("Agent Outcomes")


def test_benchmark_enabled_report_keeps_validation_csvs_outside_web_output(
    tmp_path: Path,
) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    benchmark_dir = make_synthetic_benchmark_dir(tmp_path)

    result = build_comparison_report(
        experiment_dir,
        output_dir=tmp_path / "comparison_report",
        benchmark_dir=benchmark_dir,
        benchmark_series="SPX,NAQ",
        max_runs=2,
    )

    assert result.benchmark_diagnostics_csv_path is not None
    assert result.simulation_vs_benchmark_csv_path is not None
    assert result.seed_robustness_csv_path is not None
    assert result.stress_regime_csv_path is not None
    assert result.figure_index_csv_path is not None
    assert result.benchmark_diagnostics_csv_path.is_file()
    assert result.simulation_vs_benchmark_csv_path.is_file()
    assert result.seed_robustness_csv_path.is_file()
    assert result.stress_regime_csv_path.is_file()
    assert result.figure_index_csv_path.is_file()

    benchmark_diagnostics = pd.read_csv(result.benchmark_diagnostics_csv_path)
    simulation_vs_benchmark = pd.read_csv(result.simulation_vs_benchmark_csv_path)
    stress_diagnostics = pd.read_csv(result.stress_regime_csv_path)
    figure_index = pd.read_csv(result.figure_index_csv_path)
    report_html = result.report_path.read_text(encoding="utf-8")

    assert set(benchmark_diagnostics["benchmark_id"]) == {"SPX", "NAQ"}
    assert {"ks_statistic", "wasserstein_distance", "q01_absolute_error"}.issubset(
        simulation_vs_benchmark.columns
    )
    assert {"normal", "stress"}.issubset(set(stress_diagnostics["regime"]))
    assert "Empirical Benchmark Scorecard" in report_html
    assert "Simulation-vs-Market Distribution Comparison" in report_html
    assert "Agent Wealth Gini Coefficient Over Time" in report_html
    assert "Double-Auction Allocative Efficiency" in report_html
    assert "Cumulative Agent Return Share" in report_html
    assert "wealth_gini_timeseries" in set(figure_index["figure_name"])
    assert "allocative_efficiency_timeseries" in set(figure_index["figure_name"])
    assert "agent_return_lorenz" in set(figure_index["figure_name"])
    assert "Seed Robustness by Experimental Condition" in report_html
    assert "Benchmark Comparison" in report_html
    assert "seed_robustness" in set(figure_index["figure_name"])
    assert "stress_regime_summary" not in set(figure_index["figure_name"])
    assert "stress_period_panels" not in set(figure_index["figure_name"])
    assert "Stress-Regime Comparison" not in report_html
    assert "Stress-Period Panels" not in report_html
    assert "Thesis Figure Exports" not in report_html
    assert "stress_regime_diagnostics.csv" not in report_html
    assert "figure_index.csv" not in report_html
    assert "Mean Allocative Efficiency" in report_html
    assert "Double-Auction Allocative Efficiency" in report_html


def test_run_report_writes_new_validation_outputs_without_benchmarks(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dir = discover_run_directories(experiment_dir)[0]

    result = build_run_report(run_dir, output_dir=tmp_path / "run_report")

    assert result.benchmark_diagnostics_csv_path is not None
    assert result.simulation_vs_benchmark_csv_path is not None
    assert result.seed_robustness_csv_path is not None
    assert result.stress_regime_csv_path is not None
    assert result.figure_index_csv_path is not None
    assert result.benchmark_diagnostics_csv_path.is_file()
    assert result.simulation_vs_benchmark_csv_path.is_file()
    assert result.seed_robustness_csv_path.is_file()
    assert result.stress_regime_csv_path.is_file()
    assert result.figure_index_csv_path.is_file()

    report_html = result.report_path.read_text(encoding="utf-8")
    figure_index = pd.read_csv(result.figure_index_csv_path)
    assert "Stress-Regime Comparison" not in report_html
    assert "Stress-Period Panels" not in report_html
    assert "Thesis Figure Exports" not in report_html
    assert "stress_regime_diagnostics.csv" not in report_html
    assert "figure_index.csv" not in report_html
    assert "Seed Robustness by Experimental Condition" not in report_html
    assert "Data Label Notes" not in report_html
    assert "seed_robustness" not in set(figure_index["figure_name"])
    assert "stress_regime_summary" not in set(figure_index["figure_name"])
    assert "stress_period_panels" not in set(figure_index["figure_name"])


def test_comparison_report_includes_executive_summary(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)

    result = build_comparison_report(
        experiment_dir,
        output_dir=tmp_path / "comparison_report",
        max_runs=2,
    )

    report_html = result.report_path.read_text(encoding="utf-8")
    assert 'id="summary"' in report_html
    assert report_html.index('id="summary"') < report_html.index('id="data-availability"')
    assert "Runs Analysed" in report_html
    assert "Observation Count" in report_html
    assert "Mean Allocative Efficiency" in report_html
    assert "Fat-Tail Evidence" in report_html
    assert "Volatility Clustering" in report_html
    assert "Raw-Return Autocorrelation" in report_html
    assert "evidence consistent with stylised facts" in report_html
    _assert_evidence_section_terms(report_html)


def test_comparison_report_marks_missing_summary_metrics_as_unavailable(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    for run_dir in discover_run_directories(experiment_dir):
        summary_path = run_dir / "summary_metrics.csv"
        summary = pd.read_csv(summary_path)
        summary = summary.drop(columns=["max_drawdown"], errors="ignore")
        summary.to_csv(summary_path, index=False)

    result = build_comparison_report(
        experiment_dir,
        output_dir=tmp_path / "comparison_report",
        max_runs=2,
    )

    report_html = result.report_path.read_text(encoding="utf-8")
    assert "Max Drawdown" in report_html
    assert "Not available" in report_html


def test_run_report_includes_direct_executive_summary(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dir = discover_run_directories(experiment_dir)[0]

    result = build_run_report(run_dir, output_dir=tmp_path / "run_report")

    report_html = result.report_path.read_text(encoding="utf-8")
    assert 'id="summary"' in report_html
    assert "Runs Analysed" in report_html
    assert "1" in report_html
    assert "Observation Count" in report_html
    assert "Mean Allocative Efficiency" in report_html
    assert "Fat-Tail Evidence" in report_html
    assert "Volatility Clustering" in report_html
    assert "Raw-Return Autocorrelation" in report_html
    _assert_evidence_section_terms(report_html)


def test_run_evidence_assessment_explains_evidence_and_mixed_cases() -> None:
    evidence_diagnostics = pd.DataFrame(
        [
            {
                "minimum_ljung_box_p_value": 0.20,
                "excess_kurtosis": 1.25,
                "jarque_bera_p_value": 0.01,
                "minimum_arch_lm_p_value": 0.02,
                "garch_alpha1": 0.08,
                "garch_beta1": 0.86,
                "garch_persistence": 0.94,
            }
        ]
    )

    evidence_cards = {
        card["fact"]: card for card in build_run_evidence_assessment(evidence_diagnostics)
    }

    assert evidence_cards["Weak raw-return autocorrelation"]["verdict"] == "Evidence"
    assert evidence_cards["Fat-tailed returns"]["verdict"] == "Evidence"
    assert evidence_cards["Volatility clustering"]["verdict"] == "Evidence"
    assert "Ljung-Box p-value = 0.2000" in evidence_cards[
        "Weak raw-return autocorrelation"
    ]["quantitative_evidence"]
    assert "Jarque-Bera p-value = 0.0100" in evidence_cards[
        "Fat-tailed returns"
    ]["quantitative_evidence"]
    assert "ARCH LM p-value = 0.0200" in evidence_cards[
        "Volatility clustering"
    ]["quantitative_evidence"]

    mixed_diagnostics = pd.DataFrame(
        [
            {
                "minimum_ljung_box_p_value": 0.01,
                "excess_kurtosis": 0.75,
                "jarque_bera_p_value": 0.60,
                "minimum_arch_lm_p_value": 0.40,
                "garch_alpha1": 0.07,
                "garch_beta1": 0.82,
                "garch_persistence": 0.89,
            }
        ]
    )

    mixed_cards = {
        card["fact"]: card for card in build_run_evidence_assessment(mixed_diagnostics)
    }

    assert (
        mixed_cards["Weak raw-return autocorrelation"]["verdict"]
        == "Not evidence / mixed evidence"
    )
    assert mixed_cards["Fat-tailed returns"]["verdict"] == "Not evidence / mixed evidence"
    assert mixed_cards["Volatility clustering"]["verdict"] == "Not evidence / mixed evidence"
    assert "rejects the no-autocorrelation null" in mixed_cards[
        "Weak raw-return autocorrelation"
    ]["interpretation"]
    assert "Mixed evidence" in mixed_cards["Fat-tailed returns"]["interpretation"]
    assert "Mixed evidence" in mixed_cards["Volatility clustering"]["interpretation"]


def test_run_evidence_assessment_marks_unavailable_statistics() -> None:
    cards = build_run_evidence_assessment(pd.DataFrame([{}]))

    assert {card["verdict"] for card in cards} == {"Not available"}
    assert {card["tone"] for card in cards} == {"neutral"}


def test_comparison_evidence_assessment_summarises_support_rates() -> None:
    diagnostics = pd.DataFrame(
        [
            {
                "minimum_ljung_box_p_value": 0.20,
                "excess_kurtosis": 1.25,
                "jarque_bera_p_value": 0.01,
                "minimum_arch_lm_p_value": 0.02,
                "garch_alpha1": 0.08,
                "garch_beta1": 0.86,
                "garch_persistence": 0.94,
            },
            {
                "minimum_ljung_box_p_value": 0.01,
                "excess_kurtosis": -0.20,
                "jarque_bera_p_value": 0.50,
                "minimum_arch_lm_p_value": 0.40,
                "garch_alpha1": 0.07,
                "garch_beta1": 0.82,
                "garch_persistence": 0.89,
            },
        ]
    )

    cards = {
        card["fact"]: card for card in build_comparison_evidence_assessment(diagnostics)
    }

    assert cards["Weak raw-return autocorrelation"]["verdict"] == "Mixed evidence"
    assert cards["Fat-tailed returns"]["verdict"] == "Mixed evidence"
    assert cards["Volatility clustering"]["verdict"] == "Mixed evidence"
    for card in cards.values():
        assert "1/2 runs (50.0%)" in card["quantitative_evidence"]
        assert "median" in card["quantitative_evidence"]


def _assert_evidence_section_terms(report_html: str) -> None:
    assert "Stylised-Fact Evidence" in report_html
    assert "Weak raw-return autocorrelation" in report_html
    assert "Fat-tailed returns" in report_html
    assert "Volatility clustering" in report_html
    assert "Ljung-Box" in report_html
    assert "Jarque-Bera" in report_html
    assert "ARCH LM" in report_html
    assert "p-value" in report_html
    assert "0.05" in report_html
