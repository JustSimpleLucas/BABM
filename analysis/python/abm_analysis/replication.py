"""Fixed-configuration seed replication for ABM robustness checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import subprocess
from typing import Callable

import pandas as pd

from abm_analysis.calibration import (
    patch_config_text,
    resolve_simulator_path,
    warn_if_simulator_stale,
)
from abm_analysis.calibration.execution import _run_simulator_subprocess
from abm_analysis.parallel import map_in_order, resolve_job_count
from abm_analysis.report import build_comparison_report, build_seed_robustness_report
from abm_analysis.run_discovery import discover_new_run_directory, run_directory_names


DEFAULT_SEED_SPEC = "1:30"

SimulatorRunner = Callable[[list[str], Path | None, int | None], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SeedReplicationOptions:
    """Runtime options for one fixed-configuration seed robustness batch."""

    base_config: Path
    simulator: Path
    seeds: tuple[int, ...]
    experiment_name: str | None = None
    experiment_root: Path | None = None
    phase: str = "simulation"
    price_column: str = "market_price"
    max_runs: int = 8
    benchmark_dir: Path | None = None
    benchmark_series: str | None = None
    timeout_seconds: int | None = None
    export_images: bool = False
    figure_formats: tuple[str, ...] = ("png", "pdf", "svg")
    show_simulation_progress: bool = True
    # Concurrent simulator subprocesses; 0 means one per CPU core (capped at
    # the seed count) and 1 restores strictly sequential execution.
    jobs: int = 0
    # The dedicated seed-robustness report is always built; the broad
    # comparison report (market dynamics, microstructure, agent panels) is
    # opt-in because replicated runs differ only in the random seed and the
    # extra ~20 figures are costly for 30-seed batches.
    generate_comparison_report: bool = False


@dataclass(frozen=True)
class SeedReplicationResult:
    """Output locations and run counts produced by a seed replication batch."""

    experiment_dir: Path
    replication_runs_csv_path: Path
    replication_summary_json_path: Path
    robustness_report_path: Path | None
    comparison_report_path: Path | None
    seed_robustness_csv_path: Path | None
    completed_count: int
    failed_count: int
    records: tuple[dict[str, object], ...]


def parse_seed_spec(value: str | None) -> tuple[int, ...]:
    """Parse comma-separated seeds and inclusive ``start:end`` seed ranges.

    Repeated-seed experiments are a Monte Carlo robustness device: every seed
    keeps the modelling assumptions fixed while changing only stochastic draws.
    Supporting explicit lists and compact ranges makes that replication design
    easy to document in thesis appendices and shell histories.
    """

    raw_value = DEFAULT_SEED_SPEC if value is None else str(value).strip()
    if not raw_value:
        raise ValueError("At least one seed must be supplied.")

    seeds: list[int] = []
    for token in raw_value.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            seeds.extend(_parse_seed_range(token))
        else:
            seeds.append(_parse_seed_value(token))

    if not seeds:
        raise ValueError("At least one seed must be supplied.")
    return tuple(seeds)


def run_seed_replication(
    options: SeedReplicationOptions,
    *,
    runner: SimulatorRunner | None = None,
) -> SeedReplicationResult:
    """Run one fixed simulation configuration across deterministic seeds."""

    base_config_path = options.base_config.expanduser().resolve()
    if not base_config_path.is_file():
        raise FileNotFoundError(f"Base config does not exist: {base_config_path}")
    if not options.seeds:
        raise ValueError("Seed replication requires at least one deterministic seed.")

    effective_jobs = resolve_job_count(options.jobs, len(options.seeds))
    if effective_jobs > 1 and len(set(options.seeds)) != len(options.seeds):
        # Duplicate seeds launched in the same second produce identical
        # run-ids, and the simulator's exists-check-then-create is not atomic
        # across processes, so two runs would write into one archive.
        raise ValueError("Parallel seed replication requires distinct seeds.")
    show_progress = options.show_simulation_progress and effective_jobs == 1

    simulator_path = resolve_simulator_path(options.simulator)
    warn_if_simulator_stale(simulator_path)
    experiment_name = options.experiment_name or timestamped_replication_name()
    experiment_root = (
        options.experiment_root.expanduser().resolve()
        if options.experiment_root is not None
        else default_experiment_root()
    )
    experiment_dir = experiment_root / experiment_name
    config_dir = experiment_dir / "replication_configs"
    robustness_report_dir = experiment_dir / "robustness_reports" / "latest_seed_robustness"
    comparison_report_dir = experiment_dir / "comparison_reports" / "latest_seed_robustness"
    experiment_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    base_config_text = base_config_path.read_text(encoding="utf-8")
    runs_csv_path = experiment_dir / "replication_runs.csv"
    records: list[dict[str, object]] = []
    if effective_jobs > 1 and options.show_simulation_progress:
        print(
            f"Running {len(options.seeds)} seeds across {effective_jobs} parallel jobs; "
            "live simulator progress is disabled.",
            flush=True,
        )

    def run_one(index: int, seed: int) -> dict[str, object]:
        return _run_one_seed(
            base_config_text=base_config_text,
            seed=seed,
            options=options,
            simulator_path=simulator_path,
            experiment_root=experiment_root,
            experiment_name=experiment_name,
            experiment_dir=experiment_dir,
            config_dir=config_dir,
            runner=runner,
            show_progress=show_progress,
            announce=effective_jobs > 1,
        )

    def checkpoint(index: int, record: dict[str, object]) -> None:
        records.append(record)
        _write_replication_runs_csv(runs_csv_path, records)
        if effective_jobs > 1:
            print(f"[seed {record['seed']}] {record['status']}", flush=True)

    map_in_order(
        options.seeds,
        run_one,
        jobs=effective_jobs,
        on_result=checkpoint,
        # The first run of a fresh experiment dir writes the manifest header;
        # its header-if-empty check is not safe against a concurrent writer.
        run_first_synchronously=not (experiment_dir / "experiment_manifest.csv").exists(),
    )

    completed_count = sum(1 for record in records if record["status"] == "completed")
    failed_count = len(records) - completed_count
    robustness_report_path: Path | None = None
    comparison_report_path: Path | None = None
    seed_robustness_csv_path: Path | None = None
    if completed_count > 0:
        robustness_result = build_seed_robustness_report(
            experiment_dir,
            output_dir=robustness_report_dir,
            phase=options.phase,
            price_column=options.price_column,
            max_runs=options.max_runs,
            export_images=options.export_images,
            figure_formats=options.figure_formats,
        )
        robustness_report_path = robustness_result.report_path
        seed_robustness_csv_path = robustness_result.seed_robustness_csv_path
        if options.generate_comparison_report:
            comparison_result = build_comparison_report(
                experiment_dir,
                output_dir=comparison_report_dir,
                phase=options.phase,
                price_column=options.price_column,
                max_runs=options.max_runs,
                benchmark_dir=options.benchmark_dir,
                benchmark_series=options.benchmark_series,
                export_images=options.export_images,
                figure_formats=options.figure_formats,
                source="files",
            )
            comparison_report_path = comparison_result.report_path

    summary_path = experiment_dir / "replication_summary.json"
    _write_replication_runs_csv(runs_csv_path, records)
    _write_replication_summary_json(
        summary_path,
        options=options,
        experiment_name=experiment_name,
        experiment_dir=experiment_dir,
        simulator_path=simulator_path,
        completed_count=completed_count,
        failed_count=failed_count,
        robustness_report_path=robustness_report_path,
        comparison_report_path=comparison_report_path,
        seed_robustness_csv_path=seed_robustness_csv_path,
    )

    return SeedReplicationResult(
        experiment_dir=experiment_dir,
        replication_runs_csv_path=runs_csv_path,
        replication_summary_json_path=summary_path,
        robustness_report_path=robustness_report_path,
        comparison_report_path=comparison_report_path,
        seed_robustness_csv_path=seed_robustness_csv_path,
        completed_count=completed_count,
        failed_count=failed_count,
        records=tuple(records),
    )


def timestamped_replication_name() -> str:
    """Return the default experiment name for seed robustness batches."""

    return f"seed_robustness_{datetime.now().strftime('%Y%m%d%H%M%S')}"


def default_experiment_root() -> Path:
    """Return the repository-local experiment archive root."""

    repository_root = Path(__file__).resolve().parents[3]
    return repository_root / "data" / "experiments"


def _run_one_seed(
    *,
    base_config_text: str,
    seed: int,
    options: SeedReplicationOptions,
    simulator_path: Path,
    experiment_root: Path,
    experiment_name: str,
    experiment_dir: Path,
    config_dir: Path,
    runner: SimulatorRunner | None,
    show_progress: bool,
    announce: bool = False,
) -> dict[str, object]:
    before_runs = run_directory_names(experiment_dir)
    config_path = config_dir / f"seed_{seed}.cfg"
    generated_config_text = patch_config_text(
        base_config_text,
        {
            "seed": seed,
            "experiment_output_enabled": True,
            "experiment_root": experiment_root,
            "experiment_name": experiment_name,
            "run_label": f"seed_{seed}",
            "python_analysis_enabled": False,
            "python_analysis_generate_comparison": False,
            "database_output_enabled": False,
        },
    )
    config_path.write_text(generated_config_text, encoding="utf-8")

    command = [str(simulator_path), "--config", str(config_path)]
    if announce:
        print(f"[seed {seed}] simulator started", flush=True)
    try:
        completed = (
            runner(command, experiment_dir, options.timeout_seconds)
            if runner is not None
            else _run_simulator(
                command,
                cwd=experiment_dir,
                timeout=options.timeout_seconds,
                show_progress=show_progress,
            )
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "seed": seed,
            "status": "timeout",
            "config_path": str(config_path),
            "run_id": "",
            "run_dir": "",
            "return_code": -1,
            "message": f"Simulator exceeded timeout of {options.timeout_seconds} seconds.",
            "stdout_excerpt": _single_line_excerpt(exc.stdout or ""),
            "stderr_excerpt": _single_line_excerpt(exc.stderr or ""),
        }

    run_dir = discover_new_run_directory(
        stdout=completed.stdout or "",
        experiment_dir=experiment_dir,
        cwd=experiment_dir,
        before_names=before_runs,
        seed=seed,
    )
    status = "completed" if completed.returncode == 0 and run_dir is not None else "failed"
    message = "" if status == "completed" else "Simulator failed or did not create a run archive."
    return {
        "seed": seed,
        "status": status,
        "config_path": str(config_path),
        "run_id": run_dir.name if run_dir is not None else "",
        "run_dir": str(run_dir) if run_dir is not None else "",
        "return_code": int(completed.returncode),
        "message": message,
        "stdout_excerpt": _single_line_excerpt(completed.stdout or ""),
        "stderr_excerpt": _single_line_excerpt(completed.stderr or ""),
    }


def _run_simulator(
    command: list[str],
    *,
    cwd: Path,
    timeout: int | None,
    show_progress: bool,
) -> subprocess.CompletedProcess[str]:
    return _run_simulator_subprocess(
        command,
        cwd=cwd,
        timeout=timeout,
        show_progress=show_progress,
    )


def _write_replication_runs_csv(path: Path, records: list[dict[str, object]]) -> None:
    pd.DataFrame(records).to_csv(path, index=False)


def _write_replication_summary_json(
    path: Path,
    *,
    options: SeedReplicationOptions,
    experiment_name: str,
    experiment_dir: Path,
    simulator_path: Path,
    completed_count: int,
    failed_count: int,
    robustness_report_path: Path | None,
    comparison_report_path: Path | None,
    seed_robustness_csv_path: Path | None,
) -> None:
    summary = {
        "experiment_name": experiment_name,
        "created_at_local": datetime.now().isoformat(timespec="seconds"),
        "base_config": str(options.base_config.expanduser().resolve()),
        "simulator": str(simulator_path),
        "experiment_dir": str(experiment_dir),
        "seeds": list(options.seeds),
        "requested_seed_count": len(options.seeds),
        "completed_seed_count": completed_count,
        "failed_seed_count": failed_count,
        "phase": options.phase,
        "price_column": options.price_column,
        "benchmark_dir": str(options.benchmark_dir.expanduser().resolve())
        if options.benchmark_dir is not None
        else None,
        "benchmark_series": options.benchmark_series,
        "outputs": {
            "replication_runs_csv": "replication_runs.csv",
            "robustness_report": _relative_or_none(experiment_dir, robustness_report_path),
            "comparison_report": _relative_or_none(experiment_dir, comparison_report_path),
            "seed_robustness_csv": _relative_or_none(experiment_dir, seed_robustness_csv_path),
        },
    }
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _relative_or_none(root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _parse_seed_range(value: str) -> list[int]:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) not in {2, 3} or any(part == "" for part in parts):
        raise ValueError(f"Invalid seed range '{value}'. Use start:end or start:end:step.")
    start = _parse_seed_value(parts[0])
    end = _parse_seed_value(parts[1])
    step = _parse_seed_value(parts[2]) if len(parts) == 3 else 1
    if step <= 0:
        raise ValueError("Seed range step must be greater than zero.")
    if start > end:
        raise ValueError("Seed range start must be less than or equal to end.")
    return list(range(start, end + 1, step))


def _parse_seed_value(value: str) -> int:
    try:
        seed = int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid seed value '{value}'.") from exc
    if seed < 0:
        raise ValueError("Seeds must be non-negative integers.")
    return seed


def _single_line_excerpt(text: object, *, limit: int = 400) -> str:
    collapsed = " ".join(str(text).split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[:limit - 3]}..."
