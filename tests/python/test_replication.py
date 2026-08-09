from __future__ import annotations

from pathlib import Path
import subprocess

import pandas as pd
import pytest

from abm_analysis.cli import main as cli_main
from abm_analysis.replication import (
    SeedReplicationOptions,
    SeedReplicationResult,
    parse_seed_spec,
    run_seed_replication,
)
from abm_analysis.robustness import build_seed_robustness_summary

from abm_test_helpers import make_synthetic_benchmark_dir, write_synthetic_run


def test_parse_seed_spec_accepts_ranges_and_lists() -> None:
    assert parse_seed_spec("1:3") == (1, 2, 3)
    assert parse_seed_spec("55,66,77") == (55, 66, 77)
    assert parse_seed_spec(None) == tuple(range(1, 31))


def test_parse_seed_spec_rejects_empty_specs() -> None:
    with pytest.raises(ValueError):
        parse_seed_spec("")
    with pytest.raises(ValueError):
        parse_seed_spec(",,")


def test_replicate_cli_builds_options_without_running_simulator(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, SeedReplicationOptions] = {}

    def fake_run_seed_replication(options: SeedReplicationOptions) -> SeedReplicationResult:
        captured["options"] = options
        return SeedReplicationResult(
            experiment_dir=tmp_path / "experiment",
            replication_runs_csv_path=tmp_path / "experiment" / "replication_runs.csv",
            replication_summary_json_path=tmp_path / "experiment" / "replication_summary.json",
            robustness_report_path=None,
            comparison_report_path=None,
            seed_robustness_csv_path=None,
            completed_count=2,
            failed_count=0,
            records=(),
        )

    monkeypatch.setattr("abm_analysis.cli.run_seed_replication", fake_run_seed_replication)
    benchmark_dir = make_synthetic_benchmark_dir(tmp_path)

    exit_code = cli_main(
        [
            "replicate",
            "--base-config",
            "config/simulation.cfg",
            "--simulator",
            "custom/simulate",
            "--seeds",
            "55,66",
            "--experiment-name",
            "pytest_seed_batch",
            "--experiment-root",
            str(tmp_path / "experiments"),
            "--benchmark-dir",
            str(benchmark_dir),
            "--benchmark-series",
            "SPX",
            "--quiet-simulation-progress",
            "--jobs",
            "3",
        ]
    )

    assert exit_code == 0
    assert captured["options"].base_config == Path("config/simulation.cfg")
    assert captured["options"].simulator == Path("custom/simulate")
    assert captured["options"].seeds == (55, 66)
    assert captured["options"].experiment_name == "pytest_seed_batch"
    assert captured["options"].benchmark_dir == benchmark_dir
    assert captured["options"].benchmark_series == "SPX"
    assert captured["options"].show_simulation_progress is False
    assert captured["options"].generate_comparison_report is False
    assert captured["options"].jobs == 3


def test_replicate_cli_defaults_to_release_simulator_and_auto_jobs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, SeedReplicationOptions] = {}

    def fake_run_seed_replication(options: SeedReplicationOptions) -> SeedReplicationResult:
        captured["options"] = options
        return SeedReplicationResult(
            experiment_dir=tmp_path / "experiment",
            replication_runs_csv_path=tmp_path / "experiment" / "replication_runs.csv",
            replication_summary_json_path=tmp_path / "experiment" / "replication_summary.json",
            robustness_report_path=None,
            comparison_report_path=None,
            seed_robustness_csv_path=None,
            completed_count=2,
            failed_count=0,
            records=(),
        )

    monkeypatch.setattr("abm_analysis.cli.run_seed_replication", fake_run_seed_replication)

    exit_code = cli_main(["replicate", "--seeds", "55,66"])

    assert exit_code == 0
    assert captured["options"].simulator == Path("build/release/simulate")
    assert captured["options"].jobs == 0


def test_run_seed_replication_patches_only_batch_control_settings(tmp_path: Path) -> None:
    base_config = tmp_path / "base.cfg"
    base_config.write_text(
        "\n".join(
            [
                "seed = 99",
                "num_noise_traders = 5",
                "experiment_output_enabled = 0",
                "experiment_root = data/experiments",
                "experiment_name = demo",
                "run_label = base",
                "python_analysis_enabled = 1",
                "python_analysis_generate_comparison = 1",
                "database_output_enabled = 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    simulator = tmp_path / "simulate"
    simulator.write_text("# fake simulator\n", encoding="utf-8")
    captured_configs: list[dict[str, str]] = []

    def fake_runner(
        command: list[str],
        cwd: Path | None,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout_seconds
        values = _read_config_values(Path(command[2]))
        captured_configs.append(values)
        run_id = f"20260630120000_1_1_0_0_20_30_5_0_180_{values['seed']}"
        write_synthetic_run(
            Path(values["experiment_root"]) / values["experiment_name"] / run_id,
            run_id,
            int(values["seed"]),
            0.0,
        )
        return subprocess.CompletedProcess(command, 0, "ok", "")

    run_seed_replication(
        SeedReplicationOptions(
            base_config=base_config,
            simulator=simulator,
            seeds=(123,),
            experiment_name="pytest_replication",
            experiment_root=tmp_path / "experiments",
            show_simulation_progress=False,
        ),
        runner=fake_runner,
    )

    generated = captured_configs[0]
    assert generated["seed"] == "123"
    assert generated["num_noise_traders"] == "5"
    assert generated["experiment_output_enabled"] == "1"
    assert generated["experiment_name"] == "pytest_replication"
    assert generated["run_label"] == "seed_123"
    assert generated["python_analysis_enabled"] == "0"
    assert generated["python_analysis_generate_comparison"] == "0"
    assert generated["database_output_enabled"] == "0"


def test_run_seed_replication_creates_run_records_and_robustness_report(tmp_path: Path) -> None:
    base_config = _write_minimal_base_config(tmp_path)
    simulator = tmp_path / "simulate"
    simulator.write_text("# fake simulator\n", encoding="utf-8")

    result = run_seed_replication(
        SeedReplicationOptions(
            base_config=base_config,
            simulator=simulator,
            seeds=(55, 66),
            experiment_name="pytest_seed_robustness",
            experiment_root=tmp_path / "experiments",
            show_simulation_progress=False,
        ),
        runner=_synthetic_run_writer(),
    )

    assert result.completed_count == 2
    assert result.failed_count == 0
    assert result.replication_runs_csv_path.is_file()
    assert result.replication_summary_json_path.is_file()
    assert result.robustness_report_path is not None
    assert result.robustness_report_path.is_file()
    assert "robustness_reports" in str(result.robustness_report_path)
    # The broad comparison report is opt-in for replication batches because
    # their runs differ only in the random seed.
    assert result.comparison_report_path is None
    assert result.seed_robustness_csv_path is not None
    assert result.seed_robustness_csv_path.is_file()
    run_records = pd.read_csv(result.replication_runs_csv_path)
    assert set(run_records["seed"]) == {55, 66}
    assert set(run_records["status"]) == {"completed"}


def test_run_seed_replication_optionally_builds_comparison_report(tmp_path: Path) -> None:
    base_config = _write_minimal_base_config(tmp_path)
    simulator = tmp_path / "simulate"
    simulator.write_text("# fake simulator\n", encoding="utf-8")

    result = run_seed_replication(
        SeedReplicationOptions(
            base_config=base_config,
            simulator=simulator,
            seeds=(55, 66),
            experiment_name="pytest_seed_robustness_full",
            experiment_root=tmp_path / "experiments",
            show_simulation_progress=False,
            generate_comparison_report=True,
        ),
        runner=_synthetic_run_writer(),
    )

    assert result.robustness_report_path is not None
    assert result.robustness_report_path.is_file()
    assert result.comparison_report_path is not None
    assert result.comparison_report_path.is_file()
    assert "comparison_reports" in str(result.comparison_report_path)


def test_run_seed_replication_records_failed_seed(tmp_path: Path) -> None:
    base_config = _write_minimal_base_config(tmp_path)
    simulator = tmp_path / "simulate"
    simulator.write_text("# fake simulator\n", encoding="utf-8")

    def failing_runner(
        command: list[str],
        cwd: Path | None,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout_seconds
        return subprocess.CompletedProcess(command, 2, "", "configuration error")

    result = run_seed_replication(
        SeedReplicationOptions(
            base_config=base_config,
            simulator=simulator,
            seeds=(55,),
            experiment_name="pytest_failed_seed",
            experiment_root=tmp_path / "experiments",
            show_simulation_progress=False,
        ),
        runner=failing_runner,
    )

    assert result.completed_count == 0
    assert result.failed_count == 1
    assert result.robustness_report_path is None
    assert result.comparison_report_path is None
    run_records = pd.read_csv(result.replication_runs_csv_path)
    assert run_records.iloc[0]["seed"] == 55
    assert run_records.iloc[0]["status"] == "failed"
    assert "configuration error" in run_records.iloc[0]["stderr_excerpt"]


def test_run_seed_replication_parallel_batch_preserves_seed_order(tmp_path: Path) -> None:
    base_config = _write_minimal_base_config(tmp_path)
    simulator = tmp_path / "simulate"
    simulator.write_text("# fake simulator\n", encoding="utf-8")

    def parallel_safe_runner(
        command: list[str],
        cwd: Path | None,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout_seconds
        values = _read_config_values(Path(command[2]))
        seed = int(values["seed"])
        run_id = f"20260630120000_1_1_0_0_20_30_5_2_180_{seed}"
        run_dir = Path(values["experiment_root"]) / values["experiment_name"] / run_id
        write_synthetic_run(run_dir, run_id, seed, 0.0)
        return subprocess.CompletedProcess(
            command, 0, f"Experiment run directory: {run_dir}\n", ""
        )

    result = run_seed_replication(
        SeedReplicationOptions(
            base_config=base_config,
            simulator=simulator,
            seeds=(55, 66, 77),
            experiment_name="pytest_parallel_batch",
            experiment_root=tmp_path / "experiments",
            show_simulation_progress=False,
            jobs=2,
        ),
        runner=parallel_safe_runner,
    )

    assert result.completed_count == 3
    assert result.failed_count == 0
    assert [record["seed"] for record in result.records] == [55, 66, 77]
    run_records = pd.read_csv(result.replication_runs_csv_path)
    assert list(run_records["seed"]) == [55, 66, 77]
    assert set(run_records["status"]) == {"completed"}
    for record in result.records:
        assert str(record["run_id"]).rsplit("_", 1)[-1] == str(record["seed"])


def test_run_seed_replication_prefers_stdout_run_dir_over_diff(tmp_path: Path) -> None:
    base_config = _write_minimal_base_config(tmp_path)
    simulator = tmp_path / "simulate"
    simulator.write_text("# fake simulator\n", encoding="utf-8")
    target_run_id = "20260630120000_1_1_0_0_20_30_5_2_180_55"
    decoy_run_id = "20260630120009_1_1_0_0_20_30_5_2_180_55"

    def decoy_writing_runner(
        command: list[str],
        cwd: Path | None,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout_seconds
        values = _read_config_values(Path(command[2]))
        experiment_dir = Path(values["experiment_root"]) / values["experiment_name"]
        write_synthetic_run(experiment_dir / target_run_id, target_run_id, 55, 0.0)
        # The decoy's name sorts after the target and ends in the same seed,
        # so the legacy diff-and-take-last discovery would mis-attribute the
        # run to it. Its archived content uses another seed only so that the
        # downstream robustness report sees unique per-seed columns.
        write_synthetic_run(experiment_dir / decoy_run_id, decoy_run_id, 66, 0.0)
        return subprocess.CompletedProcess(
            command,
            0,
            f"Experiment run directory: {experiment_dir / target_run_id}\n",
            "",
        )

    result = run_seed_replication(
        SeedReplicationOptions(
            base_config=base_config,
            simulator=simulator,
            seeds=(55,),
            experiment_name="pytest_stdout_discovery",
            experiment_root=tmp_path / "experiments",
            show_simulation_progress=False,
        ),
        runner=decoy_writing_runner,
    )

    assert result.records[0]["run_id"] == target_run_id


def test_run_seed_replication_rejects_duplicate_seeds_when_parallel(tmp_path: Path) -> None:
    base_config = _write_minimal_base_config(tmp_path)
    simulator = tmp_path / "simulate"
    simulator.write_text("# fake simulator\n", encoding="utf-8")

    with pytest.raises(ValueError, match="distinct seeds"):
        run_seed_replication(
            SeedReplicationOptions(
                base_config=base_config,
                simulator=simulator,
                seeds=(55, 55),
                experiment_name="pytest_duplicate_seeds",
                experiment_root=tmp_path / "experiments",
                show_simulation_progress=False,
                jobs=2,
            ),
            runner=_synthetic_run_writer(),
        )


def test_seed_robustness_summary_includes_dispersion_columns() -> None:
    runs_index = pd.DataFrame(
        [
            {
                "run_id": "seed_1",
                "seed": 1,
                "time_steps": 100,
                "num_fundamentalists": 20,
                "num_chartists": 30,
                "num_noise_traders": 5,
                "num_buy_and_hold_agents": 0,
                "max_drawdown": 0.10,
            },
            {
                "run_id": "seed_2",
                "seed": 2,
                "time_steps": 100,
                "num_fundamentalists": 20,
                "num_chartists": 30,
                "num_noise_traders": 5,
                "num_buy_and_hold_agents": 0,
                "max_drawdown": 0.30,
            },
        ]
    )
    diagnostics = pd.DataFrame(
        [
            {"run_id": "seed_1", "log_return_std_dev": 0.01},
            {"run_id": "seed_2", "log_return_std_dev": 0.03},
        ]
    )

    summary = build_seed_robustness_summary(runs_index, diagnostics)

    assert summary.iloc[0]["max_drawdown_min"] == pytest.approx(0.10)
    assert summary.iloc[0]["max_drawdown_max"] == pytest.approx(0.30)
    assert summary.iloc[0]["max_drawdown_iqr"] == pytest.approx(0.10)
    assert summary.iloc[0]["max_drawdown_coefficient_of_variation"] > 0.0


def _synthetic_run_writer():
    """Build a fake simulator runner that archives one synthetic run per seed."""

    run_counter = {"value": 0}

    def fake_runner(
        command: list[str],
        cwd: Path | None,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout_seconds
        run_counter["value"] += 1
        values = _read_config_values(Path(command[2]))
        seed = int(values["seed"])
        run_id = f"202606301201{run_counter['value']:02d}_1_1_0_0_20_30_5_2_180_{seed}"
        write_synthetic_run(
            Path(values["experiment_root"]) / values["experiment_name"] / run_id,
            run_id,
            seed,
            0.0,
        )
        return subprocess.CompletedProcess(command, 0, "ok", "")

    return fake_runner


def _write_minimal_base_config(tmp_path: Path) -> Path:
    base_config = tmp_path / "base.cfg"
    base_config.write_text(
        "\n".join(
            [
                "seed = 55",
                "experiment_output_enabled = 0",
                "experiment_root = data/experiments",
                "experiment_name = demo",
                "run_label = base",
                "python_analysis_enabled = 1",
                "python_analysis_generate_comparison = 1",
                "database_output_enabled = 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return base_config


def _read_config_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", maxsplit=1)
        values[key.strip()] = value.split("#", maxsplit=1)[0].strip()
    return values
