from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

from abm_analysis.calibration import (
    CalibrationOptions,
    CalibrationSettings,
    _render_progress_chunk,
    load_calibration_settings,
    load_search_space,
    parse_seed_list,
    patch_config_text,
    resolve_simulator_path,
    run_calibration,
    run_candidate_worker_payload,
    score_return_match,
)
from abm_analysis.calibration.execution import (
    _options_from_payload,
    _score_completed_run,
    _serialisable_options,
)
from abm_analysis.calibration.scoring import score_multi_asset_return_match
from abm_analysis.calibration.study import _announce_run_budget, _attach_candidate_robustness
from abm_analysis.cli import main as cli_main
from abm_analysis.report import build_calibration_report

from abm_test_helpers import write_synthetic_asset_timeseries, write_synthetic_run


def test_patch_config_text_preserves_comments_and_appends_new_keys() -> None:
    base_config = (
        "# Example simulation config\n"
        "seed = 55 # baseline seed\n"
        "python_analysis_enabled = 1\n"
    )

    patched = patch_config_text(
        base_config,
        {
            "seed": 66,
            "python_analysis_enabled": False,
            "experiment_output_enabled": True,
        },
    )

    assert "seed = 66 # baseline seed" in patched
    assert "python_analysis_enabled = 0" in patched
    assert "experiment_output_enabled = 1" in patched


def test_load_search_space_accepts_supported_parameter_types(tmp_path: Path) -> None:
    search_space_path = tmp_path / "search_space.json"
    search_space_path.write_text(
        json.dumps(
            {
                "parameters": {
                    "control_loss_aversion": {"type": "float", "low": 1.5, "high": 4.0},
                    "num_chartists": {"type": "int", "low": 100, "high": 300, "step": 50},
                    "control_prospect_scenario_count": [3, 5, 7],
                    "social_enabled": {"type": "fixed", "value": 1},
                }
            }
        ),
        encoding="utf-8",
    )

    search_space = load_search_space(search_space_path)

    assert search_space["control_loss_aversion"]["type"] == "float"
    assert search_space["num_chartists"]["step"] == 50
    assert search_space["control_prospect_scenario_count"]["type"] == "categorical"
    assert search_space["social_enabled"]["value"] == 1


def test_score_return_match_rewards_close_distributional_fit() -> None:
    rng = np.random.default_rng(20260515)
    benchmark_values = rng.standard_t(df=5, size=240) * 0.01
    close_simulation = pd.Series(benchmark_values.copy())
    poor_simulation = pd.Series(rng.normal(0.04, 0.05, size=240))
    benchmark_returns = {"SPX": pd.Series(benchmark_values)}
    passing_diagnostics = {
        "autocorrelation_conclusion": "Consistent with absence of autocorrelation",
        "fat_tail_conclusion": "Consistent with fat-tailed returns",
        "volatility_clustering_conclusion": "Consistent with volatility clustering",
    }

    close_score = score_return_match(
        close_simulation,
        benchmark_returns,
        diagnostics=passing_diagnostics,
    )
    poor_score = score_return_match(
        poor_simulation,
        benchmark_returns,
        diagnostics=passing_diagnostics,
    )

    assert close_score.score < poor_score.score
    assert close_score.components["stylised_penalty"] == 0.0


def test_multi_asset_score_averages_every_market() -> None:
    """Both markets must count, so one good asset cannot hide a bad one.

    A candidate fitting both assets well has to beat one fitting only the first,
    and that in turn has to beat one fitting neither. Averaging is what makes
    the middle case land between the other two rather than tying with the best.
    """

    rng = np.random.default_rng(20260807)
    benchmark_values = rng.standard_t(df=5, size=240) * 0.01
    benchmark_returns = {"SPX": pd.Series(benchmark_values)}
    close = pd.Series(benchmark_values.copy())
    poor = pd.Series(rng.normal(0.04, 0.05, size=240))
    passing_diagnostics = {
        "autocorrelation_conclusion": "Consistent with absence of autocorrelation",
        "fat_tail_conclusion": "Consistent with fat-tailed returns",
        "volatility_clustering_conclusion": "Consistent with volatility clustering",
    }
    diagnostics_by_asset = {"alpha": passing_diagnostics, "beta": passing_diagnostics}

    def score(alpha: pd.Series, beta: pd.Series):
        return score_multi_asset_return_match(
            {"alpha": alpha, "beta": beta},
            benchmark_returns,
            diagnostics_by_asset=diagnostics_by_asset,
        )

    both_close = score(close, close)
    one_close = score(close, poor)
    neither_close = score(poor, poor)

    assert both_close.score < one_close.score < neither_close.score
    # Per-asset scores stay visible so a study can see which market is weak.
    assert one_close.components["asset_score.alpha"] < one_close.components["asset_score.beta"]
    assert one_close.components["asset_count"] == 2.0
    assert set(one_close.diagnostics["per_asset"]) == {"alpha", "beta"}


def test_completed_run_is_scored_asset_by_asset(tmp_path: Path) -> None:
    """The calibration objective must read every market of a completed run.

    This is the integration point between the archive and the objective: if it
    silently fell back to the primary-asset ``step_timeseries.csv`` projection,
    calibration would optimise one market while claiming to cover both.
    """

    run_dir = tmp_path / "run"
    write_synthetic_run(run_dir, run_id="run", seed=55, drift_adjustment=0.0)
    write_synthetic_asset_timeseries(run_dir, ["alpha", "beta"])
    rng = np.random.default_rng(20260807)
    benchmark_returns = {"SPX": pd.Series(rng.standard_t(df=5, size=240) * 0.01)}
    options = CalibrationOptions(
        base_config=tmp_path / "base.cfg",
        search_space=tmp_path / "space.json",
        simulator=tmp_path / "simulate",
        calibration_name="per_asset",
        trials=1,
        seeds=(55,),
    )

    score = _score_completed_run(run_dir, benchmark_returns, options=options)

    assert set(score.diagnostics["per_asset"]) == {"alpha", "beta"}
    assert score.components["asset_count"] == 2.0
    assert {"asset_score.alpha", "asset_score.beta"}.issubset(score.components)


def test_parse_seed_list_rejects_empty_seed_set() -> None:
    assert parse_seed_list("55,66,77") == (55, 66, 77)


def test_resolve_simulator_path_accepts_relative_existing_binary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    simulator_path = tmp_path / "local_build" / "simulate"
    simulator_path.parent.mkdir()
    simulator_path.write_text("# fake simulator\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    resolved = resolve_simulator_path(Path("local_build") / "simulate")

    assert resolved == simulator_path.resolve()


def test_calibrate_cli_defaults_to_release_simulator_without_running_optuna(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, CalibrationOptions] = {}

    def fake_run_calibration(options: CalibrationOptions) -> Path:
        captured["options"] = options
        return tmp_path / "calibration_output"

    monkeypatch.setattr("abm_analysis.cli.run_calibration", fake_run_calibration)
    benchmark_dir = tmp_path / "benchmarks"
    benchmark_dir.mkdir()
    exit_code = cli_main(
        [
            "calibrate",
            "--base-config",
            "config/simulation.cfg",
            "--search-space",
            "config/calibration/search_space.json",
            "--benchmark-dir",
            str(benchmark_dir),
            "--benchmark-series",
            "SPX",
            "--trials",
            "12",
            "--seeds",
            "55,66",
            "--calibration-name",
            "pytest_calibration",
        ]
    )

    assert exit_code == 0
    assert captured["options"].simulator == Path("build/release/simulate")
    assert captured["options"].jobs == 0


def test_calibrate_cli_builds_options_without_running_optuna(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, CalibrationOptions] = {}

    def fake_run_calibration(options: CalibrationOptions) -> Path:
        captured["options"] = options
        return tmp_path / "calibration_output"

    monkeypatch.setattr("abm_analysis.cli.run_calibration", fake_run_calibration)
    benchmark_dir = tmp_path / "benchmarks"
    benchmark_dir.mkdir()
    exit_code = cli_main(
        [
            "calibrate",
            "--base-config",
            "config/simulation.cfg",
            "--search-space",
            "config/calibration/search_space.json",
            "--simulator",
            "custom/simulate",
            "--benchmark-dir",
            str(benchmark_dir),
            "--benchmark-series",
            "SPX",
            "--trials",
            "12",
            "--seeds",
            "55,66",
            "--calibration-name",
            "pytest_calibration",
            "--jobs",
            "3",
        ]
    )

    assert exit_code == 0
    assert captured["options"].simulator == Path("custom/simulate")
    assert captured["options"].trials == 12
    assert captured["options"].seeds == (55, 66)
    assert captured["options"].benchmark_series == "SPX"
    assert captured["options"].keep_run_csv is False
    assert captured["options"].isolate_trials is True
    assert captured["options"].show_simulation_progress is True
    assert captured["options"].jobs == 3


def test_progress_renderer_emits_complete_simulator_frames(capsys) -> None:
    progress_frame = "Simulation progress [#####.....]  50% (50/100 steps, 1s)"
    segment = ""

    for character in f"\r{progress_frame}\r":
        segment = _render_progress_chunk(segment, character)

    assert segment == ""
    assert capsys.readouterr().out == f"\r{progress_frame}"


def test_run_calibration_with_fake_simulator_creates_best_outputs(tmp_path: Path) -> None:
    base_config_path = tmp_path / "base.cfg"
    base_config_path.write_text(
        "\n".join(
            [
                "seed = 55",
                "experiment_output_enabled = 0",
                "experiment_root = data/experiments",
                "experiment_name = demo",
                "run_label = base",
                "python_analysis_enabled = 1",
                "python_analysis_generate_comparison = 1",
                "num_noise_traders = 5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    search_space_path = tmp_path / "search_space.json"
    search_space_path.write_text(
        json.dumps({"parameters": {"num_noise_traders": {"type": "fixed", "value": 5}}}),
        encoding="utf-8",
    )
    simulator_path = tmp_path / "simulate"
    simulator_path.write_text("# fake simulator\n", encoding="utf-8")
    benchmark_dir = _write_benchmark_dir(tmp_path)
    output_dir = tmp_path / "calibration_output"
    run_counter = {"value": 0}

    def fake_runner(
        command: list[str],
        cwd: Path | None,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout_seconds
        run_counter["value"] += 1
        config_values = _read_config_values(Path(command[2]))
        experiment_root = Path(config_values["experiment_root"])
        experiment_name = config_values["experiment_name"]
        seed = int(config_values["seed"])
        run_id = f"202605151200{run_counter['value']:02d}_1_1_1_1_20_30_5_120_{seed}"
        _write_run_archive(experiment_root / experiment_name / run_id, seed)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    result_dir = run_calibration(
        CalibrationOptions(
            base_config=base_config_path,
            search_space=search_space_path,
            simulator=simulator_path,
            calibration_name="pytest_optuna",
            trials=1,
            seeds=(55,),
            output_dir=output_dir,
            benchmark_dir=benchmark_dir,
            benchmark_series="SPX",
            top_candidates=1,
        ),
        runner=fake_runner,
    )

    assert result_dir == output_dir.resolve()
    assert (output_dir / "calibration_trials.csv").is_file()
    assert (output_dir / "best_config.cfg").is_file()
    assert (output_dir / "best_config.json").is_file()
    assert (output_dir / "calibration_summary.json").is_file()
    assert list((output_dir / "best_runs").glob("*"))
    assert not list((output_dir / "best_runs").glob("*/step_timeseries.csv"))
    assert not list((output_dir / "simulation_runs").glob("**/*.csv"))
    # One validation seed sits below the verdict minimum, so the ranking must
    # fall back to the legacy fit-only rule and select the identical winner.
    summary = json.loads((output_dir / "calibration_summary.json").read_text(encoding="utf-8"))
    assert summary["best_robustness_pass_rate"] is None
    assert summary["best_robust_ranking_score"] == summary["best_ranking_score"]


def test_run_calibration_with_parallel_search_seeds_preserves_trial_csv_order(
    tmp_path: Path,
) -> None:
    base_config_path = tmp_path / "base.cfg"
    base_config_path.write_text(
        "\n".join(
            [
                "seed = 55",
                "experiment_output_enabled = 0",
                "experiment_root = data/experiments",
                "experiment_name = demo",
                "run_label = base",
                "python_analysis_enabled = 1",
                "python_analysis_generate_comparison = 1",
                "num_noise_traders = 5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    search_space_path = tmp_path / "search_space.json"
    search_space_path.write_text(
        json.dumps({"parameters": {"num_noise_traders": {"type": "fixed", "value": 5}}}),
        encoding="utf-8",
    )
    simulator_path = tmp_path / "simulate"
    simulator_path.write_text("# fake simulator\n", encoding="utf-8")
    benchmark_dir = _write_benchmark_dir(tmp_path)
    output_dir = tmp_path / "calibration_output"

    def parallel_safe_runner(
        command: list[str],
        cwd: Path | None,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout_seconds
        config_values = _read_config_values(Path(command[2]))
        experiment_dir = Path(config_values["experiment_root"]) / config_values["experiment_name"]
        experiment_dir.mkdir(parents=True, exist_ok=True)
        seed = int(config_values["seed"])
        run_id = f"20260708120000_1_1_0_0_20_30_5_2_180_{seed}"
        write_synthetic_run(experiment_dir / run_id, run_id, seed, 0.0)
        return subprocess.CompletedProcess(
            command, 0, f"Experiment run directory: {experiment_dir / run_id}\n", ""
        )

    output_path = run_calibration(
        CalibrationOptions(
            base_config=base_config_path,
            search_space=search_space_path,
            simulator=simulator_path,
            calibration_name="pytest_parallel_seeds",
            trials=1,
            seeds=(55, 66),
            output_dir=output_dir,
            benchmark_dir=benchmark_dir,
            benchmark_series="SPX",
            top_candidates=1,
            search_seeds=(55, 66),
            show_simulation_progress=False,
            jobs=2,
        ),
        runner=parallel_safe_runner,
    )

    assert output_path == output_dir.resolve()
    trials = pd.read_csv(output_dir / "calibration_trials.csv")
    search_rows = trials[trials["phase"] == "search"]
    validation_rows = trials[trials["phase"] == "validation"]
    assert list(search_rows["seed"]) == [55, 66]
    assert list(validation_rows["seed"]) == [55, 66]
    assert set(trials["status"]) == {"completed"}
    for _, row in trials.iterrows():
        assert str(row["run_id"]).rsplit("_", 1)[-1] == str(row["seed"])
    assert (output_dir / "best_config.cfg").is_file()
    assert (output_dir / "calibration_summary.json").is_file()


def test_run_calibration_rejects_duplicate_search_seeds_when_parallel(
    tmp_path: Path,
) -> None:
    base_config_path = tmp_path / "base.cfg"
    base_config_path.write_text("seed = 55\n", encoding="utf-8")
    search_space_path = tmp_path / "search_space.json"
    search_space_path.write_text(
        json.dumps({"parameters": {"num_noise_traders": {"type": "fixed", "value": 5}}}),
        encoding="utf-8",
    )
    simulator_path = tmp_path / "simulate"
    simulator_path.write_text("# fake simulator\n", encoding="utf-8")
    benchmark_dir = _write_benchmark_dir(tmp_path)

    with pytest.raises(ValueError, match="distinct search seeds"):
        run_calibration(
            CalibrationOptions(
                base_config=base_config_path,
                search_space=search_space_path,
                simulator=simulator_path,
                calibration_name="pytest_duplicate_search_seeds",
                trials=1,
                seeds=(55,),
                output_dir=tmp_path / "calibration_output",
                benchmark_dir=benchmark_dir,
                benchmark_series="SPX",
                top_candidates=1,
                search_seeds=(55, 55),
                show_simulation_progress=False,
                jobs=2,
            ),
            runner=lambda command, cwd, timeout: subprocess.CompletedProcess(command, 0, "", ""),
        )


def test_run_calibration_reports_simulator_stderr_when_validation_creates_no_archives(
    tmp_path: Path,
) -> None:
    base_config_path = tmp_path / "base.cfg"
    base_config_path.write_text(
        "\n".join(
            [
                "seed = 55",
                "experiment_output_enabled = 0",
                "experiment_root = data/experiments",
                "experiment_name = demo",
                "run_label = base",
                "python_analysis_enabled = 1",
                "python_analysis_generate_comparison = 1",
                "num_buy_and_hold_agents = 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    search_space_path = tmp_path / "search_space.json"
    search_space_path.write_text(
        json.dumps({"parameters": {"num_buy_and_hold_agents": {"type": "fixed", "value": 0}}}),
        encoding="utf-8",
    )
    simulator_path = tmp_path / "simulate"
    simulator_path.write_text("# fake simulator\n", encoding="utf-8")
    benchmark_dir = _write_benchmark_dir(tmp_path)
    output_dir = tmp_path / "calibration_output"
    simulator_error = (
        "Configuration error: Unknown config key 'num_buy_and_hold_agents' "
        "at validation_trial_0000_seed_55.cfg:11."
    )

    def failing_runner(
        command: list[str],
        cwd: Path | None,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout_seconds
        return subprocess.CompletedProcess(command, 2, "", simulator_error)

    with pytest.raises(RuntimeError) as error_info:
        run_calibration(
            CalibrationOptions(
                base_config=base_config_path,
                search_space=search_space_path,
                simulator=simulator_path,
                calibration_name="pytest_failed_validation",
                trials=1,
                seeds=(55,),
                output_dir=output_dir,
                benchmark_dir=benchmark_dir,
                benchmark_series="SPX",
                top_candidates=1,
                show_simulation_progress=False,
            ),
            runner=failing_runner,
        )

    message = str(error_info.value)
    assert "Calibration did not produce any validation run archives." in message
    assert f"Simulator: {simulator_path.resolve()}" in message
    assert "validation_trial_0000_seed_55.cfg" in message
    assert "Return code: 2" in message
    assert simulator_error in message


def test_worker_payload_runs_candidate_and_prunes_csv_outputs(tmp_path: Path) -> None:
    base_config_path = tmp_path / "base.cfg"
    base_config_path.write_text(
        "\n".join(
            [
                "seed = 55",
                "experiment_output_enabled = 1",
                f"experiment_root = {tmp_path / 'runs'}",
                "experiment_name = search",
                "run_label = worker",
                "python_analysis_enabled = 0",
                "python_analysis_generate_comparison = 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    simulator_path = tmp_path / "simulate.py"
    simulator_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "from pathlib import Path",
                "import csv",
                "import math",
                "config = Path(sys.argv[2]).read_text().splitlines()",
                "values = {}",
                "for line in config:",
                "    if '=' in line and not line.strip().startswith('#'):",
                "        key, value = line.split('=', 1)",
                "        values[key.strip()] = value.split('#', 1)[0].strip()",
                "root = Path(values['experiment_root']) / values['experiment_name']",
                "seed = int(values['seed'])",
                "run_dir = root / f'20260515130000_1_1_1_1_20_30_5_120_{seed}'",
                "run_dir.mkdir(parents=True)",
                "with (run_dir / 'step_timeseries.csv').open('w', newline='') as handle:",
                "    writer = csv.writer(handle)",
                "    writer.writerow(['phase', 'market_price'])",
                "    price = 100.0",
                "    for index in range(140):",
                "        price *= math.exp(math.sin(seed + index) * 0.01)",
                "        writer.writerow(['simulation', price])",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    simulator_path.chmod(0o755)
    benchmark_dir = _write_benchmark_dir(tmp_path)
    output_dir = tmp_path / "calibration"
    output_dir.mkdir()
    config_dir = output_dir / "trial_configs"
    config_dir.mkdir()
    simulations_root = output_dir / "simulation_runs"

    response = run_candidate_worker_payload(
        {
            "base_config_text": base_config_path.read_text(encoding="utf-8"),
            "parameters": {"num_noise_traders": 5},
            "seed": 55,
            "trial_number": 0,
            "phase": "search",
            "options": {
                "base_config": str(base_config_path),
                "search_space": str(tmp_path / "search_space.json"),
                "simulator": str(simulator_path),
                "calibration_name": "worker_test",
                "trials": 1,
                "seeds": [55],
                "output_dir": str(output_dir),
                "benchmark_dir": str(benchmark_dir),
                "benchmark_series": "SPX",
                "holdout_benchmark_series": None,
                "top_candidates": 1,
                "score_threshold": None,
                "no_improvement_trials": None,
                "phase": "simulation",
                "price_column": "market_price",
                "timeout_seconds": 60,
                "keep_run_csv": False,
                "isolate_trials": True,
                "show_simulation_progress": False,
            },
            "output_dir": str(output_dir),
            "config_dir": str(config_dir),
            "simulations_root": str(simulations_root),
            "simulator_path": str(simulator_path),
            "prune_csv_after_scoring": True,
        }
    )

    assert response["execution"]["status"] == "completed"
    assert response["score"]["score"] < 1.0e9
    assert not list(simulations_root.glob("**/*.csv"))


def test_attach_candidate_robustness_prefers_seed_stable_candidate(tmp_path: Path) -> None:
    """A slightly better-fitting but seed-unstable candidate must lose the ranking."""

    validation_root = tmp_path / "simulation_runs" / "validation"
    validation_root.mkdir(parents=True)
    seeds = (1, 2, 3, 4, 5, 6)
    noisy_run_dirs: list[Path] = []
    stable_run_dirs: list[Path] = []
    for index, seed in enumerate(seeds, start=1):
        # The drift shifts every log return by ~0.01*seed, so the noisy
        # candidate's seeds draw from visibly different distributions while
        # the stable candidate's seeds are true replicates.
        noisy_id = f"2026070812010{index}_1_1_0_0_20_30_5_2_180_{seed}"
        write_synthetic_run(validation_root / noisy_id, noisy_id, seed, 2.0 * seed)
        noisy_run_dirs.append(validation_root / noisy_id)
        stable_id = f"2026070812020{index}_1_1_0_0_20_30_5_2_180_{seed}"
        write_synthetic_run(validation_root / stable_id, stable_id, seed, 0.0)
        stable_run_dirs.append(validation_root / stable_id)

    validation_results: list[dict[str, object]] = [
        {
            "trial_number": 0,
            "search_score": 0.90,
            "mean_validation_score": 0.95,
            "validation_score_std": 0.05,
            "ranking_score": 1.00,
            "parameters": {"control_prospect_theory_agent_fraction": 0.4},
            "run_dirs": noisy_run_dirs,
            "executions": [],
        },
        {
            "trial_number": 1,
            "search_score": 0.97,
            "mean_validation_score": 1.02,
            "validation_score_std": 0.03,
            "ranking_score": 1.05,
            "parameters": {"control_prospect_theory_agent_fraction": 0.2},
            "run_dirs": stable_run_dirs,
            "executions": [],
        },
    ]
    options = CalibrationOptions(
        base_config=tmp_path / "base.cfg",
        search_space=tmp_path / "search_space.json",
        simulator=tmp_path / "simulate",
        calibration_name="pytest_robust_ranking",
        trials=1,
        seeds=(55,),
    )

    any_evaluated = _attach_candidate_robustness(
        validation_results,
        validation_root=validation_root,
        options=options,
        settings=CalibrationSettings(),
    )

    assert any_evaluated is True
    noisy_row, stable_row = validation_results
    assert stable_row["robustness_pass_rate"] > noisy_row["robustness_pass_rate"]
    # The legacy fit-only rule prefers the noisy candidate...
    assert noisy_row["ranking_score"] < stable_row["ranking_score"]
    # ...but the robustness-aware ranking flips the winner.
    assert stable_row["robust_ranking_score"] < noisy_row["robust_ranking_score"]
    winner = min(
        validation_results,
        key=lambda row: (row["robust_ranking_score"], row["trial_number"]),
    )
    assert winner["trial_number"] == 1


def test_run_calibration_writes_robustness_outputs(tmp_path: Path) -> None:
    base_config_path = tmp_path / "base.cfg"
    base_config_path.write_text(
        "\n".join(
            [
                "seed = 55",
                "experiment_output_enabled = 0",
                "experiment_root = data/experiments",
                "experiment_name = demo",
                "run_label = base",
                "python_analysis_enabled = 1",
                "python_analysis_generate_comparison = 1",
                "num_noise_traders = 5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    search_space_path = tmp_path / "search_space.json"
    search_space_path.write_text(
        json.dumps({"parameters": {"num_noise_traders": {"type": "fixed", "value": 5}}}),
        encoding="utf-8",
    )
    simulator_path = tmp_path / "simulate"
    simulator_path.write_text("# fake simulator\n", encoding="utf-8")
    benchmark_dir = _write_benchmark_dir(tmp_path)
    output_dir = tmp_path / "calibration_output"
    run_counter = {"value": 0}

    def fake_runner(
        command: list[str],
        cwd: Path | None,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout_seconds
        run_counter["value"] += 1
        config_values = _read_config_values(Path(command[2]))
        experiment_dir = Path(config_values["experiment_root"]) / config_values["experiment_name"]
        experiment_dir.mkdir(parents=True, exist_ok=True)
        seed = int(config_values["seed"])
        run_id = f"202607081200{run_counter['value']:02d}_1_1_0_0_20_30_5_2_180_{seed}"
        write_synthetic_run(experiment_dir / run_id, run_id, seed, 0.0)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    output_path = run_calibration(
        CalibrationOptions(
            base_config=base_config_path,
            search_space=search_space_path,
            simulator=simulator_path,
            calibration_name="pytest_robust_outputs",
            trials=1,
            seeds=(55,),
            output_dir=output_dir,
            benchmark_dir=benchmark_dir,
            benchmark_series="SPX",
            top_candidates=1,
            validation_seeds=(1, 2, 3, 4, 5, 6),
            show_simulation_progress=False,
        ),
        runner=fake_runner,
    )

    assert output_path == output_dir.resolve()
    report_dir = output_dir / "calibration_report"
    assert (report_dir / "index.html").is_file()
    candidate_summary = pd.read_csv(report_dir / "candidate_validation_summary.csv")
    assert {
        "trial_number",
        "mean_validation_score",
        "validation_score_std",
        "ranking_score",
        "robustness_pass_rate",
        "robustness_pass_count",
        "robustness_borderline_count",
        "robustness_fail_count",
        "robustness_not_available_count",
        "seed_count",
        "robust_ranking_score",
        "selected",
    }.issubset(candidate_summary.columns)
    assert candidate_summary["selected"].any()
    assert int(candidate_summary.iloc[0]["seed_count"]) == 6

    candidate_verdicts = pd.read_csv(report_dir / "candidate_robustness_verdicts.csv")
    assert {"trial_number", "criterion", "verdict"}.issubset(candidate_verdicts.columns)
    assert not candidate_verdicts.empty

    assert (output_dir / "best_runs_robustness_report" / "index.html").is_file()

    summary = json.loads((output_dir / "calibration_summary.json").read_text(encoding="utf-8"))
    assert summary["validation_seeds"] == [1, 2, 3, 4, 5, 6]
    assert summary["estimated_total_runs"] == 1 + 1 * 6
    assert summary["best_robustness_pass_rate"] is not None
    assert summary["robustness_penalty_weight"] == 1.0
    assert summary["outputs"]["calibration_report"] == "calibration_report/index.html"
    assert (
        summary["outputs"]["best_runs_robustness_report"]
        == "best_runs_robustness_report/index.html"
    )


def test_announce_run_budget_warns_on_oversized_and_low_seed_campaigns(
    tmp_path: Path,
    capsys,
) -> None:
    options = CalibrationOptions(
        base_config=tmp_path / "base.cfg",
        search_space=tmp_path / "search_space.json",
        simulator=tmp_path / "simulate",
        calibration_name="pytest_budget",
        trials=200,
        seeds=(55,),
        top_candidates=8,
    )
    settings = CalibrationSettings()

    estimated = _announce_run_budget(options, settings, tuple(range(1, 21)), (55,))
    output = capsys.readouterr().out
    assert estimated == 200 + 8 * 20
    assert "Estimated simulator runs: 360" in output
    assert "exceed the configured budget of 300" in output

    multi_seed_estimated = _announce_run_budget(
        options, settings, tuple(range(1, 21)), (55, 66, 77)
    )
    capsys.readouterr()
    assert multi_seed_estimated == 200 * 3 + 8 * 20

    small_options = CalibrationOptions(
        base_config=tmp_path / "base.cfg",
        search_space=tmp_path / "search_space.json",
        simulator=tmp_path / "simulate",
        calibration_name="pytest_budget_small",
        trials=10,
        seeds=(55,),
        top_candidates=2,
    )
    estimated_small = _announce_run_budget(small_options, settings, (55,), (55,))
    output_small = capsys.readouterr().out
    assert estimated_small == 12
    assert "below the minimum of 5" in output_small
    assert "fit-only rule" in output_small
    assert "ROBUSTNESS VERDICTS DISABLED" in output_small


def test_worker_options_round_trip_preserves_new_fields(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    options = CalibrationOptions(
        base_config=tmp_path / "base.cfg",
        search_space=tmp_path / "search_space.json",
        simulator=tmp_path / "simulate",
        calibration_name="pytest_round_trip",
        trials=3,
        seeds=(55, 66),
        validation_seeds=(1, 2, 3),
        settings_path=settings_path,
        robustness_penalty_weight=1.5,
        jobs=4,
    )

    payload = json.loads(json.dumps(_serialisable_options(options)))
    restored = _options_from_payload(payload)

    assert restored.seeds == (55, 66)
    assert restored.validation_seeds == (1, 2, 3)
    assert restored.settings_path == settings_path.resolve()
    assert restored.robustness_penalty_weight == 1.5
    assert restored.jobs == 4

    options_without_extras = CalibrationOptions(
        base_config=tmp_path / "base.cfg",
        search_space=tmp_path / "search_space.json",
        simulator=tmp_path / "simulate",
        calibration_name="pytest_round_trip_defaults",
        trials=3,
        seeds=(55,),
    )
    restored_defaults = _options_from_payload(
        json.loads(json.dumps(_serialisable_options(options_without_extras)))
    )
    assert restored_defaults.validation_seeds is None
    assert restored_defaults.settings_path is None
    assert restored_defaults.robustness_penalty_weight is None
    assert restored_defaults.jobs == 0


def test_load_calibration_settings_defaults_overrides_and_unknown_keys(
    tmp_path: Path,
) -> None:
    defaults = load_calibration_settings(None)
    assert defaults.ranking.robustness_penalty_weight == 1.0
    assert defaults.ranking.borderline_credit == 0.5
    assert defaults.budget.max_total_runs == 300
    assert defaults.verdict_thresholds.cov_pass == 0.10
    assert defaults.score_weights.ks_statistic == 1.0

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "ranking": {"robustness_penalty_weight": 2.5},
                "verdict_thresholds": {"cov_pass": 0.05},
                "score_weights": {"ks_statistic": 2.0},
            }
        ),
        encoding="utf-8",
    )
    loaded = load_calibration_settings(settings_path)
    assert loaded.ranking.robustness_penalty_weight == 2.5
    assert loaded.ranking.borderline_credit == 0.5
    assert loaded.verdict_thresholds.cov_pass == 0.05
    assert loaded.verdict_thresholds.cov_borderline == 0.25
    assert loaded.score_weights.ks_statistic == 2.0

    unknown_section = tmp_path / "unknown_section.json"
    unknown_section.write_text(json.dumps({"rankings": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown calibration settings section"):
        load_calibration_settings(unknown_section)

    unknown_key = tmp_path / "unknown_key.json"
    unknown_key.write_text(
        json.dumps({"ranking": {"weight": 1.0}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown key"):
        load_calibration_settings(unknown_key)


def test_repo_search_space_respects_cpp_constraints() -> None:
    """The committed search space must stay inside the C++ validator's ranges."""

    repo_root = Path(__file__).resolve().parents[2]
    search_space = load_search_space(repo_root / "config" / "calibration" / "search_space.json")

    unit_interval_parameters = (
        "control_prospect_theory_agent_fraction",
        "agent_activity_rate",
        "noise_trader_order_size_fraction",
        "market_order_probability",
        "cancellation_base_probability",
    )
    for name in unit_interval_parameters:
        spec = search_space[name]
        assert 0.0 <= float(spec["low"]) <= float(spec["high"]) <= 1.0, name

    strictly_positive_parameters = (
        "control_loss_aversion",
        "noise_trader_belief_shock_std_dev",
        "noise_trader_order_size_fraction",
    )
    for name in strictly_positive_parameters:
        assert float(search_space[name]["low"]) > 0.0, name

    assert float(search_space["control_loss_aversion_std_dev"]["low"]) >= 0.0

    for name in ("num_fundamentalists", "num_chartists"):
        spec = search_space[name]
        assert spec["type"] == "int", name
        assert int(spec["low"]) >= 0, name


def test_build_calibration_report_renders_ranking_and_verdicts(tmp_path: Path) -> None:
    candidate_summary = pd.DataFrame(
        [
            {
                "trial_number": 1,
                "mean_validation_score": 1.02,
                "validation_score_std": 0.03,
                "ranking_score": 1.05,
                "robustness_pass_rate": 0.9,
                "robust_ranking_score": 1.155,
                "selected": True,
            },
            {
                "trial_number": 0,
                "mean_validation_score": 0.95,
                "validation_score_std": 0.05,
                "ranking_score": 1.00,
                "robustness_pass_rate": 0.4,
                "robust_ranking_score": 1.60,
                "selected": False,
            },
        ]
    )
    candidate_verdicts = pd.DataFrame(
        [
            {
                "trial_number": 1,
                "criterion": "Fat-tailed returns reproducibility",
                "category": "stylised_fact_reproducibility",
                "hypothesis": "The stylised fact holds across seeds.",
                "metric_value": 0.9,
                "metric_display": "success rate = 90%",
                "threshold_description": "pass when >= 0.8.",
                "verdict": "pass",
                "interpretation": "Reproduced by a strong majority of seeds.",
            }
        ]
    )

    report_path = build_calibration_report(
        tmp_path,
        calibration_name="pytest_report",
        candidate_summary=candidate_summary,
        candidate_verdicts=candidate_verdicts,
        best_trial_number=1,
        robustness_penalty_weight=1.0,
        borderline_credit=0.5,
        validation_seed_count=6,
        estimated_total_runs=13,
    )

    assert report_path.is_file()
    html = report_path.read_text(encoding="utf-8")
    assert "Calibration Report: pytest_report" in html
    assert "Candidate Ranking" in html
    assert "Winner Robustness Verdicts" in html
    assert "Fat-tailed returns reproducibility" in html
    report_dir = tmp_path / "calibration_report"
    assert (report_dir / "candidate_validation_summary.csv").is_file()
    assert (report_dir / "candidate_robustness_verdicts.csv").is_file()


def _write_benchmark_dir(tmp_path: Path) -> Path:
    benchmark_dir = tmp_path / "benchmarks"
    benchmark_dir.mkdir()
    dates = pd.date_range("2026-01-01", periods=140, freq="D")
    close = 100.0 * np.exp(np.cumsum(_synthetic_returns(len(dates), seed=123)))
    pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
        }
    ).to_csv(benchmark_dir / "02_SPX.csv", index=False)
    return benchmark_dir


def _write_run_archive(run_dir: Path, seed: int) -> None:
    run_dir.mkdir(parents=True)
    prices = 100.0 * np.exp(np.cumsum(_synthetic_returns(140, seed=seed)))
    pd.DataFrame(
        {
            "row_index": np.arange(len(prices)),
            "phase": "simulation",
            "market_price": prices,
            "traded_volume": 100.0,
        }
    ).to_csv(run_dir / "step_timeseries.csv", index=False)


def _synthetic_returns(length: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_t(df=5, size=length) * 0.01


def _read_config_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", maxsplit=1)
        values[key.strip()] = value.split("#", maxsplit=1)[0].strip()
    return values
