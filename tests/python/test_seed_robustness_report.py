from __future__ import annotations

from pathlib import Path

import pandas as pd

from abm_analysis.cli import main as cli_main
from abm_analysis.report import SeedRobustnessReportResult, build_seed_robustness_report

from abm_test_helpers import write_synthetic_run


def _make_replicated_experiment(tmp_path: Path) -> Path:
    """Create three synthetic runs that differ only in the random seed."""

    experiment_dir = tmp_path / "seed_replicates"
    experiment_dir.mkdir()
    for index, seed in enumerate((55, 66, 77), start=1):
        run_id = f"2026063012010{index}_1_1_0_0_20_30_5_2_180_{seed}"
        write_synthetic_run(experiment_dir / run_id, run_id, seed, 0.0)
    return experiment_dir


def test_seed_robustness_report_writes_html_and_csv_outputs(tmp_path: Path) -> None:
    experiment_dir = _make_replicated_experiment(tmp_path)

    result = build_seed_robustness_report(experiment_dir, output_dir=tmp_path / "report")

    assert result.report_path.is_file()
    for csv_path in (
        result.runs_index_csv_path,
        result.diagnostics_csv_path,
        result.pairwise_ks_csv_path,
        result.seed_robustness_csv_path,
        result.distribution_tests_csv_path,
        result.adf_stationarity_csv_path,
        result.seed_convergence_csv_path,
        result.verdicts_csv_path,
        result.figure_index_csv_path,
    ):
        assert csv_path.is_file()

    html = result.report_path.read_text(encoding="utf-8")
    assert "Seed Robustness Report: seed_replicates" in html
    assert "Seed-Robustness Verdicts" in html
    assert "Seed 55" in html
    assert "Seed-Count Convergence" in html
    assert "Log-Return Stationarity by Seed" in html

    verdicts = pd.read_csv(result.verdicts_csv_path)
    assert {"criterion", "category", "verdict", "interpretation"}.issubset(verdicts.columns)
    # Three seeds sit below the verdict minimum, so criteria must degrade to
    # "not_available" rather than reporting spurious pass/fail decisions.
    assert set(verdicts["verdict"]) == {"not_available"}

    distribution_tests = pd.read_csv(result.distribution_tests_csv_path)
    assert set(distribution_tests["test_name"]) == {
        "anderson_darling_ksample",
        "kruskal_wallis",
        "levene_brown_forsythe",
    }

    adf_table = pd.read_csv(result.adf_stationarity_csv_path)
    assert len(adf_table) == 3
    assert set(adf_table["status"]) == {"completed"}

    convergence = pd.read_csv(result.seed_convergence_csv_path)
    assert list(convergence[convergence["metric"] == "max_drawdown"]["newest_seed"]) == [
        55,
        66,
        77,
    ]


def test_seed_robustness_report_requires_run_directories(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty_experiment"
    empty_dir.mkdir()

    try:
        build_seed_robustness_report(empty_dir)
    except FileNotFoundError as error:
        assert "No run directories" in str(error)
    else:
        raise AssertionError("An empty experiment directory should raise FileNotFoundError.")


def test_robustness_cli_builds_report_without_recomputation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_builder(experiment, **kwargs) -> SeedRobustnessReportResult:
        captured["experiment"] = experiment
        captured["kwargs"] = kwargs
        report_dir = tmp_path / "fake_report"
        return SeedRobustnessReportResult(
            report_path=report_dir / "index.html",
            output_dir=report_dir,
            runs_index_csv_path=report_dir / "runs_index.csv",
            diagnostics_csv_path=report_dir / "stylised_fact_diagnostics.csv",
            pairwise_ks_csv_path=report_dir / "pairwise_ks_log_returns.csv",
            seed_robustness_csv_path=report_dir / "seed_robustness_summary.csv",
            distribution_tests_csv_path=report_dir / "cross_seed_distribution_tests.csv",
            adf_stationarity_csv_path=report_dir / "adf_stationarity_by_seed.csv",
            seed_convergence_csv_path=report_dir / "seed_convergence.csv",
            verdicts_csv_path=report_dir / "robustness_verdicts.csv",
            figure_index_csv_path=report_dir / "figure_index.csv",
        )

    monkeypatch.setattr("abm_analysis.commands.robustness.build_seed_robustness_report", fake_builder)

    exit_code = cli_main(
        [
            "robustness",
            str(tmp_path / "experiments" / "demo"),
            "--phase",
            "all",
            "--price-column",
            "market_price",
            "--max-runs",
            "4",
        ]
    )

    assert exit_code == 0
    assert captured["experiment"] == tmp_path / "experiments" / "demo"
    assert captured["kwargs"]["phase"] == "all"
    assert captured["kwargs"]["price_column"] == "market_price"
    assert captured["kwargs"]["max_runs"] == 4
    assert captured["kwargs"]["export_images"] is True
