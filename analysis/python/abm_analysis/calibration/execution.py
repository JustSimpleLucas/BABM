"""Simulator execution and isolated worker payload handling."""

from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
from typing import Any

import numpy as np
import pandas as pd

from abm_analysis.archive.benchmarks import build_benchmark_return_series, load_benchmark_timeseries_map
from abm_analysis.archive.data import prepare_return_series
from abm_analysis.statistics.diagnostics import diagnose_return_series
from abm_analysis.statistics.multi_asset import asset_series_id, build_asset_return_series
from abm_analysis.archive.run_discovery import discover_new_run_directory, run_directory_names

from .config import load_calibration_settings, patch_config_text
from .constants import FAILED_TRIAL_SCORE, RUN_CSV_ARTIFACT_FILENAMES
from .models import (
    CalibrationOptions,
    CalibrationScore,
    CalibrationSettings,
    SimulationExecutionResult,
    SimulatorRunner,
)
from .scoring import score_multi_asset_return_match, score_return_match

@lru_cache(maxsize=8)
def _cached_calibration_settings(settings_path: str | None) -> CalibrationSettings:
    """Load calibration settings once per path instead of once per seed run."""

    return load_calibration_settings(settings_path)

def _settings_for_options(options: CalibrationOptions) -> CalibrationSettings:
    path = options.settings_path
    return _cached_calibration_settings(None if path is None else str(path))

def _run_and_score_candidate(
    *,
    base_config_text: str,
    parameters: dict[str, object],
    seed: int,
    trial_number: int,
    phase: str,
    options: CalibrationOptions,
    output_dir: Path,
    config_dir: Path,
    simulations_root: Path,
    simulator_path: Path,
    benchmark_returns: dict[str, pd.Series],
    runner: SimulatorRunner | None,
    prune_csv_after_scoring: bool,
) -> tuple[SimulationExecutionResult, CalibrationScore]:
    """Execute one calibration candidate and score its simulated returns against benchmarks.

    Returns a failed-trial score instead of raising when the simulator does not
    complete or return-series analysis fails, so one bad trial cannot abort an
    Optuna study.
    """

    execution = _execute_simulation(
        base_config_text=base_config_text,
        parameters=parameters,
        seed=seed,
        trial_number=trial_number,
        phase=phase,
        options=options,
        output_dir=output_dir,
        config_dir=config_dir,
        simulations_root=simulations_root,
        simulator_path=simulator_path,
        runner=runner,
    )
    if execution.run_dir is None or execution.status != "completed":
        return execution, CalibrationScore(
            score=FAILED_TRIAL_SCORE,
            components={"market_distance": FAILED_TRIAL_SCORE, "stylised_penalty": 0.0},
            benchmark_scores=[],
            diagnostics={"diagnostic_status": execution.status, "message": execution.message},
        )

    try:
        score = _score_completed_run(
            execution.run_dir,
            benchmark_returns,
            options=options,
        )
        if prune_csv_after_scoring:
            _prune_run_csv_artifacts(execution.run_dir)
        return execution, score
    # These are the failure modes of run-directory loading (missing/malformed
    # CSVs) and the pandas/numpy/statsmodels analysis pipeline on degenerate
    # return series; anything else indicates a real bug and should propagate
    # instead of silently scoring the trial as failed.
    except (
        OSError,
        ValueError,
        KeyError,
        UnicodeDecodeError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
        np.linalg.LinAlgError,
    ) as exc:
        if prune_csv_after_scoring and execution.run_dir is not None:
            _prune_run_csv_artifacts(execution.run_dir)
        failed_execution = SimulationExecutionResult(
            status="analysis_failed",
            config_path=execution.config_path,
            run_dir=execution.run_dir,
            return_code=execution.return_code,
            stdout=execution.stdout,
            stderr=execution.stderr,
            message=str(exc),
        )
        return failed_execution, CalibrationScore(
            score=FAILED_TRIAL_SCORE,
            components={"market_distance": FAILED_TRIAL_SCORE, "stylised_penalty": 0.0},
            benchmark_scores=[],
            diagnostics={"diagnostic_status": "analysis_failed", "message": str(exc)},
        )

def _score_completed_run(
    run_dir: Path,
    benchmark_returns: dict[str, pd.Series],
    *,
    options: CalibrationOptions,
) -> CalibrationScore:
    """Score one completed run against the benchmarks, market by market.

    Every enabled asset is scored and the trial's objective is the mean of the
    per-asset scores, so calibration cannot buy a good fit in one market at the
    cost of the other. Archives with no per-asset artefact fall back to the
    single-asset ``step_timeseries.csv`` view and score exactly as before.
    """

    weights = _settings_for_options(options).score_weights
    returns_by_asset = build_asset_return_series(run_dir, phase=options.phase)
    if not returns_by_asset:
        simulation_returns = prepare_return_series(
            run_dir,
            phase=options.phase,
            price_column=options.price_column,
        )
        return score_return_match(
            simulation_returns,
            benchmark_returns,
            diagnostics=diagnose_return_series(
                run_dir.name,
                simulation_returns,
                phase=options.phase,
                price_column=options.price_column,
            ),
            weights=weights,
        )

    diagnostics_by_asset = {
        asset: diagnose_return_series(
            asset_series_id(run_dir.name, asset),
            returns,
            phase=options.phase,
            price_column=options.price_column,
        )
        for asset, returns in returns_by_asset.items()
    }
    return score_multi_asset_return_match(
        returns_by_asset,
        benchmark_returns,
        diagnostics_by_asset=diagnostics_by_asset,
        weights=weights,
    )

def _run_and_score_candidate_with_optional_worker(
    *,
    base_config_text: str,
    parameters: dict[str, object],
    seed: int,
    trial_number: int,
    phase: str,
    options: CalibrationOptions,
    output_dir: Path,
    config_dir: Path,
    simulations_root: Path,
    simulator_path: Path,
    benchmark_returns: dict[str, pd.Series],
    runner: SimulatorRunner | None,
    prune_csv_after_scoring: bool,
) -> tuple[SimulationExecutionResult, CalibrationScore]:
    """Run a candidate in a fresh Python worker unless tests inject a runner."""

    if runner is not None or not options.isolate_trials:
        return _run_and_score_candidate(
            base_config_text=base_config_text,
            parameters=parameters,
            seed=seed,
            trial_number=trial_number,
            phase=phase,
            options=options,
            output_dir=output_dir,
            config_dir=config_dir,
            simulations_root=simulations_root,
            simulator_path=simulator_path,
            benchmark_returns=benchmark_returns,
            runner=runner,
            prune_csv_after_scoring=prune_csv_after_scoring,
        )

    return _run_candidate_in_worker_process(
        base_config_text=base_config_text,
        parameters=parameters,
        seed=seed,
        trial_number=trial_number,
        phase=phase,
        options=options,
        output_dir=output_dir,
        config_dir=config_dir,
        simulations_root=simulations_root,
        simulator_path=simulator_path,
        prune_csv_after_scoring=prune_csv_after_scoring,
    )

def _run_candidate_in_worker_process(
    *,
    base_config_text: str,
    parameters: dict[str, object],
    seed: int,
    trial_number: int,
    phase: str,
    options: CalibrationOptions,
    output_dir: Path,
    config_dir: Path,
    simulations_root: Path,
    simulator_path: Path,
    prune_csv_after_scoring: bool,
) -> tuple[SimulationExecutionResult, CalibrationScore]:
    """Run one candidate in an isolated subprocess and read back its JSON result.

    Isolating each trial in its own worker process contains crashes or resource
    leaks in the C++ simulator to a single trial instead of the whole calibration
    study.
    """

    worker_dir = output_dir / "worker_payloads"
    worker_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{phase}_trial_{trial_number:04d}_seed_{seed}"
    request_path = worker_dir / f"{stem}_request.json"
    response_path = worker_dir / f"{stem}_response.json"
    request_payload = {
        "base_config_text": base_config_text,
        "parameters": parameters,
        "seed": seed,
        "trial_number": trial_number,
        "phase": phase,
        "options": _serialisable_options(options),
        "output_dir": str(output_dir),
        "config_dir": str(config_dir),
        "simulations_root": str(simulations_root),
        "simulator_path": str(simulator_path),
        "prune_csv_after_scoring": prune_csv_after_scoring,
    }
    request_path.write_text(json.dumps(request_payload, sort_keys=True), encoding="utf-8")

    command = [
        sys.executable,
        "-m",
        "abm_analysis.calibration.worker",
        str(request_path),
        str(response_path),
    ]
    completed = subprocess.run(
        command,
        cwd=output_dir,
        capture_output=not options.show_simulation_progress,
        text=True,
        timeout=None if options.timeout_seconds is None else options.timeout_seconds + 30,
        check=False,
        env=_worker_environment(),
    )
    if response_path.is_file():
        return _deserialise_worker_response(json.loads(response_path.read_text(encoding="utf-8")))

    message = completed.stderr.strip() or completed.stdout.strip() or "Worker wrote no response."
    return (
            SimulationExecutionResult(
                status="worker_failed",
                config_path=config_dir / f"{phase}_trial_{trial_number:04d}_seed_{seed}.cfg",
                run_dir=None,
                return_code=int(completed.returncode),
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
                message=message,
            ),
        CalibrationScore(
            score=FAILED_TRIAL_SCORE,
            components={"market_distance": FAILED_TRIAL_SCORE, "stylised_penalty": 0.0},
            benchmark_scores=[],
            diagnostics={"diagnostic_status": "worker_failed", "message": message},
        ),
    )

def run_candidate_worker_payload(payload: dict[str, object]) -> dict[str, object]:
    """Run one calibration candidate from a JSON-serialisable worker payload."""

    options = _options_from_payload(payload["options"])
    benchmark_map = load_benchmark_timeseries_map(
        options.benchmark_dir,
        options.benchmark_series,
    )
    benchmark_returns = build_benchmark_return_series(benchmark_map)
    execution, score = _run_and_score_candidate(
        base_config_text=str(payload["base_config_text"]),
        parameters=dict(payload["parameters"]),
        seed=int(payload["seed"]),
        trial_number=int(payload["trial_number"]),
        phase=str(payload["phase"]),
        options=options,
        output_dir=Path(str(payload["output_dir"])),
        config_dir=Path(str(payload["config_dir"])),
        simulations_root=Path(str(payload["simulations_root"])),
        simulator_path=Path(str(payload["simulator_path"])),
        benchmark_returns=benchmark_returns,
        runner=None,
        prune_csv_after_scoring=bool(payload["prune_csv_after_scoring"]),
    )
    return _serialise_worker_response(execution, score)

def _serialisable_options(options: CalibrationOptions) -> dict[str, object]:
    """Convert a CalibrationOptions instance into a JSON-serialisable dictionary."""

    payload = asdict(options)
    for key, value in list(payload.items()):
        if isinstance(value, Path):
            payload[key] = str(value.expanduser().resolve())
        elif isinstance(value, tuple):
            payload[key] = list(value)
    return payload

def _options_from_payload(payload: object) -> CalibrationOptions:
    """Reconstruct a CalibrationOptions instance from a JSON-decoded worker payload."""

    if not isinstance(payload, dict):
        raise TypeError("Worker options payload must be a dictionary.")
    values = dict(payload)
    for key in [
        "base_config",
        "search_space",
        "simulator",
        "output_dir",
        "benchmark_dir",
        "settings_path",
    ]:
        if values.get(key) is not None:
            values[key] = Path(str(values[key]))
    values["seeds"] = tuple(int(seed) for seed in values.get("seeds", []))
    if values.get("validation_seeds") is not None:
        values["validation_seeds"] = tuple(int(seed) for seed in values["validation_seeds"])
    if values.get("search_seeds") is not None:
        values["search_seeds"] = tuple(int(seed) for seed in values["search_seeds"])
    return CalibrationOptions(**values)

def _worker_environment() -> dict[str, str]:
    """Build the environment for the worker subprocess, ensuring abm_analysis is importable.

    The worker is launched via `python -m abm_analysis.calibration.worker`;
    prepending the package's parent directory to PYTHONPATH keeps that import
    working regardless of the caller's working directory.
    """

    environment = os.environ.copy()
    analysis_python = str(Path(__file__).resolve().parents[2])
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        analysis_python
        if not existing_pythonpath
        else f"{analysis_python}{os.pathsep}{existing_pythonpath}"
    )
    return environment

def _serialise_worker_response(
    execution: SimulationExecutionResult,
    score: CalibrationScore,
) -> dict[str, object]:
    """Serialise a simulation execution result and calibration score into a JSON-ready worker response payload."""

    return {
        "execution": {
            "status": execution.status,
            "config_path": str(execution.config_path),
            "run_dir": str(execution.run_dir) if execution.run_dir is not None else None,
            "return_code": execution.return_code,
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "message": execution.message,
        },
        "score": {
            "score": score.score,
            "components": score.components,
            "benchmark_scores": score.benchmark_scores,
            "diagnostics": _json_ready(score.diagnostics),
        },
    }

def _deserialise_worker_response(
    payload: dict[str, object],
) -> tuple[SimulationExecutionResult, CalibrationScore]:
    """Parse a worker response payload back into a (SimulationExecutionResult, CalibrationScore) pair."""

    execution_payload = dict(payload["execution"])
    score_payload = dict(payload["score"])
    execution = SimulationExecutionResult(
        status=str(execution_payload["status"]),
        config_path=Path(str(execution_payload["config_path"])),
        run_dir=(
            Path(str(execution_payload["run_dir"]))
            if execution_payload.get("run_dir") is not None
            else None
        ),
        return_code=int(execution_payload["return_code"]),
        stdout=str(execution_payload.get("stdout", "")),
        stderr=str(execution_payload.get("stderr", "")),
        message=str(execution_payload.get("message", "")),
    )
    score = CalibrationScore(
        score=float(score_payload["score"]),
        components={
            str(key): float(value)
            for key, value in dict(score_payload["components"]).items()
        },
        benchmark_scores=list(score_payload.get("benchmark_scores", [])),
        diagnostics=dict(score_payload.get("diagnostics", {})),
    )
    return execution, score

def _json_ready(value: object) -> object:
    """Recursively coerce a value into a JSON-serialisable form.

    Handles nested dict/list/tuple containers, numpy scalar types, and
    non-finite or NaN floats, which the standard json module cannot encode
    directly.
    """

    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if pd.isna(value):
        return None
    return value

def _execute_simulation(
    *,
    base_config_text: str,
    parameters: dict[str, object],
    seed: int,
    trial_number: int,
    phase: str,
    options: CalibrationOptions,
    output_dir: Path,
    config_dir: Path,
    simulations_root: Path,
    simulator_path: Path,
    runner: SimulatorRunner | None,
) -> SimulationExecutionResult:
    """Run the C++ simulator once for a candidate configuration and locate its output run directory.

    The run directory is identified by diffing the experiment directory's
    contents before and after the subprocess call, since the simulator names
    run folders itself.
    """

    experiment_name = phase
    experiment_dir = simulations_root / experiment_name
    before_runs = run_directory_names(experiment_dir)
    config_path = config_dir / f"{phase}_trial_{trial_number:04d}_seed_{seed}.cfg"
    config_updates = {
        **parameters,
        "seed": seed,
        "experiment_output_enabled": True,
        "experiment_root": simulations_root,
        "experiment_name": experiment_name,
        "run_label": f"{phase}_trial_{trial_number:04d}_seed_{seed}",
    }
    config_path.write_text(patch_config_text(base_config_text, config_updates), encoding="utf-8")

    command = [str(simulator_path), "--config", str(config_path)]
    try:
        completed = (
            runner(command, output_dir, options.timeout_seconds)
            if runner is not None
            else _run_simulator_subprocess(
                command,
                cwd=output_dir,
                timeout=options.timeout_seconds,
                show_progress=options.show_simulation_progress,
            )
        )
    except subprocess.TimeoutExpired as exc:
        return SimulationExecutionResult(
            status="timeout",
            config_path=config_path,
            run_dir=None,
            return_code=-1,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            message=f"Simulator exceeded timeout of {options.timeout_seconds} seconds.",
        )

    run_dir = discover_new_run_directory(
        stdout=completed.stdout or "",
        experiment_dir=experiment_dir,
        cwd=output_dir,
        before_names=before_runs,
        seed=seed,
    )
    status = "completed" if completed.returncode == 0 and run_dir is not None else "failed"
    return SimulationExecutionResult(
        status=status,
        config_path=config_path,
        run_dir=run_dir,
        return_code=int(completed.returncode),
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        message=(
            ""
            if status == "completed"
            else "Simulator failed or did not create a run archive."
        ),
    )

def _run_simulator_subprocess(
    command: list[str],
    *,
    cwd: Path,
    timeout: int | None,
    show_progress: bool,
) -> subprocess.CompletedProcess[str]:
    """Run the simulator, optionally forwarding only its progress bar live."""

    if not show_progress:
        # Tell the simulator not to render frames nobody is reading, rather than
        # rendering them into a pipe and discarding the bytes here.
        return subprocess.run(
            [*command, "--quiet-progress"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0,
    )
    selector = selectors.DefaultSelector()
    if process.stdout is not None:
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    if process.stderr is not None:
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    progress_segment = ""
    start_time = time.monotonic()

    try:
        while selector.get_map():
            if timeout is not None and time.monotonic() - start_time > timeout:
                process.kill()
                stdout, stderr = process.communicate()
                raise subprocess.TimeoutExpired(
                    command,
                    timeout,
                    output="".join(stdout_parts) + (stdout or ""),
                    stderr="".join(stderr_parts) + (stderr or ""),
                )

            for key, _events in selector.select(timeout=0.10):
                stream = key.fileobj
                chunk = stream.read(1)
                if chunk == "":
                    selector.unregister(stream)
                    continue
                if key.data == "stdout":
                    stdout_parts.append(chunk)
                else:
                    stderr_parts.append(chunk)
                    progress_segment = _render_progress_chunk(progress_segment, chunk)
    finally:
        selector.close()

    return_code = process.wait()
    stdout_text = "".join(stdout_parts)
    stderr_text = _without_progress_frames("".join(stderr_parts))
    _flush_progress_segment(progress_segment)
    if return_code != 0 and stderr_text:
        print(stderr_text, file=sys.stderr, end="", flush=True)
    return subprocess.CompletedProcess(
        command,
        return_code,
        stdout_text,
        stderr_text,
    )

def _without_progress_frames(stderr_text: str) -> str:
    """Drop progress-bar redraws so only real diagnostics remain.

    The bar shares the diagnostic stream with warnings and error messages. A
    failing run would otherwise report hundreds of redraw frames ahead of the
    one line that explains the failure.
    """

    kept = [
        segment
        for segment in stderr_text.replace("\r", "\n").split("\n")
        if segment and not segment.startswith("Simulation progress")
    ]
    return "\n".join(kept) + "\n" if kept else ""

def _render_progress_chunk(progress_segment: str, chunk: str) -> str:
    """Buffer simulator stderr and render complete progress-bar frames.

    The C++ simulator redraws its progress bar with carriage returns on its
    diagnostic stream, keeping stdout clean for the run summary and artefact
    paths. Reading byte-by-byte is necessary for live feedback, but printing
    each byte would flood captured logs, so only complete
    ``Simulation progress`` frames are emitted. Other stderr output stays
    buffered and is reported if the run fails.
    """

    for character in chunk:
        if character == "\r":
            _flush_progress_segment(progress_segment, end="")
            progress_segment = ""
        elif character == "\n":
            _flush_progress_segment(progress_segment)
            progress_segment = ""
        else:
            progress_segment += character
    return progress_segment

def _flush_progress_segment(progress_segment: str, *, end: str = "\n") -> None:
    """Print one buffered progress frame when it is a simulator progress bar."""

    if progress_segment.startswith("Simulation progress"):
        print(f"\r{progress_segment}", end=end, flush=True)

def _prune_run_csv_artifacts(run_dir: Path) -> None:
    """Delete simulator CSV files that are not needed after objective scoring."""

    for filename in RUN_CSV_ARTIFACT_FILENAMES:
        path = run_dir / filename
        if path.exists():
            path.unlink()
