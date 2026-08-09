from __future__ import annotations

from pathlib import Path

from abm_analysis.cli import main as cli_main

from abm_test_helpers import make_synthetic_benchmark_dir, make_synthetic_experiment


def test_cli_smoke_supports_benchmark_and_no_benchmark_modes(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    benchmark_dir = make_synthetic_benchmark_dir(tmp_path)

    benchmark_status = cli_main(
        [
            "compare",
            str(experiment_dir),
            "--output-dir",
            str(tmp_path / "cli_benchmark_report"),
            "--benchmark-dir",
            str(benchmark_dir),
            "--benchmark-series",
            "SPX",
            "--max-runs",
            "2",
            "--source",
            "files",
            "--no-export-images",
        ]
    )
    no_benchmark_status = cli_main(
        [
            "compare",
            str(experiment_dir),
            "--output-dir",
            str(tmp_path / "cli_no_benchmark_report"),
            "--no-benchmark",
            "--max-runs",
            "2",
            "--source",
            "files",
            "--no-export-images",
        ]
    )

    assert benchmark_status == 0
    assert no_benchmark_status == 0
    assert (tmp_path / "cli_benchmark_report" / "simulation_vs_benchmark.csv").is_file()
    assert (tmp_path / "cli_no_benchmark_report" / "simulation_vs_benchmark.csv").is_file()
