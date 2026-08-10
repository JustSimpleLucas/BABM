"""Optuna study orchestration and calibration output writing."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
from typing import Any


from abm_analysis.archive.benchmarks import build_benchmark_return_series, load_benchmark_timeseries_map
from abm_analysis.parallel import map_in_order, resolve_job_count

from .config import (
    default_calibration_output_dir,
    load_calibration_settings,
    load_search_space,
    resolve_simulator_path,
    suggest_trial_parameters,
    warn_if_simulator_stale,
)
from .execution import _run_and_score_candidate_with_optional_worker
from .models import (
    CalibrationOptions,
    CalibrationScore,
    CalibrationSettings,
    SimulationExecutionResult,
    SimulatorRunner,
)
from .trials import (
    _TrialCsvWriter,
    _aggregate_search_scores,
    _build_stopping_callback,
    _build_trial_record,
    _import_optuna,
)
from .validation import (
    _attach_candidate_robustness,
    _build_candidate_summary_frame,
    _build_candidate_verdicts_frame,
    _format_missing_validation_archives_message,
    _print_simulation_run_header,
    _validate_top_candidates,
)
from .artifacts import (
    _copy_best_runs,
    _prune_calibration_csv_artifacts,
    _write_best_config,
    _write_best_runs_robustness_report_safely,
    _write_calibration_report_safely,
    _write_holdout_validation,
    _write_summary,
)


def run_calibration(
    options: CalibrationOptions,
    *,
    runner: SimulatorRunner | None = None,
) -> Path:
    """Run an Optuna calibration study and return the output directory."""

    optuna = _import_optuna()
    base_config_path = options.base_config.expanduser().resolve()
    search_space = load_search_space(options.search_space)
    simulator_path = resolve_simulator_path(options.simulator)
    warn_if_simulator_stale(simulator_path)
    if not base_config_path.is_file():
        raise FileNotFoundError(f"Base config does not exist: {base_config_path}")
    if not options.benchmark_dir:
        raise ValueError("Calibration requires a benchmark directory.")
    if options.trials <= 0:
        raise ValueError("Calibration requires at least one Optuna trial.")
    if not options.seeds:
        raise ValueError("Calibration requires at least one deterministic seed.")
    if options.top_candidates <= 0:
        raise ValueError("top_candidates must be greater than zero.")
    if options.search_seed_aggregate not in {"mean", "median"}:
        raise ValueError("search_seed_aggregate must be 'mean' or 'median'.")

    settings = _resolve_settings(options)
    validation_seeds = options.validation_seeds or options.seeds
    search_seeds = options.search_seeds or (options.seeds[0],)
    search_parallelism = resolve_job_count(options.jobs, len(search_seeds))
    validation_parallelism = resolve_job_count(options.jobs, len(validation_seeds))
    if search_parallelism > 1 and len(set(search_seeds)) != len(search_seeds):
        # Duplicate seeds launched in the same second produce identical
        # run-ids, and the simulator's exists-check-then-create is not atomic
        # across processes, so two runs would write into one archive.
        raise ValueError("Parallel calibration requires distinct search seeds.")
    if validation_parallelism > 1 and len(set(validation_seeds)) != len(validation_seeds):
        raise ValueError("Parallel calibration requires distinct validation seeds.")
    if max(search_parallelism, validation_parallelism) > 1 and options.show_simulation_progress:
        print(
            f"Running seed batches with up to "
            f"{max(search_parallelism, validation_parallelism)} parallel jobs; "
            "live simulator progress is disabled.",
            flush=True,
        )
        # One normalisation flips every downstream consumer — including the
        # isolated worker subprocess — to captured output instead of a live bar.
        options = replace(options, show_simulation_progress=False)
    minimum_seeds = settings.verdict_thresholds.minimum_seeds_for_verdicts
    if options.require_robustness_verdicts and len(validation_seeds) < minimum_seeds:
        raise ValueError(
            f"require_robustness_verdicts needs at least {minimum_seeds} validation "
            f"seeds; got {len(validation_seeds)}. Supply more via "
            "--validation-seeds (e.g. '55,101:109')."
        )
    estimated_total_runs = _announce_run_budget(
        options, settings, validation_seeds, search_seeds
    )

    output_dir = (
        options.output_dir.expanduser().resolve()
        if options.output_dir is not None
        else default_calibration_output_dir(options.calibration_name)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    config_dir = output_dir / "trial_configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    simulations_root = output_dir / "simulation_runs"
    trials_csv_path = output_dir / "calibration_trials.csv"
    base_config_text = base_config_path.read_text(encoding="utf-8")
    benchmark_map = load_benchmark_timeseries_map(
        options.benchmark_dir,
        options.benchmark_series,
    )
    benchmark_returns = build_benchmark_return_series(benchmark_map)
    if not benchmark_returns:
        raise ValueError("No benchmark return series were loaded for calibration.")

    records: list[dict[str, object]] = []
    trials_writer = _TrialCsvWriter(trials_csv_path, records)
    best_value = {"score": float("inf"), "stale_trials": 0}
    primary_seed = options.seeds[0]
    sampler = (
        optuna.samplers.TPESampler(seed=options.sampler_seed)
        if options.sampler_seed is not None
        else None
    )
    study = optuna.create_study(
        direction="minimize",
        study_name=options.calibration_name,
        sampler=sampler,
    )

    def objective(trial: Any) -> float:
        parameters = suggest_trial_parameters(trial, search_space)
        trial.set_user_attr("full_parameters", parameters)
        seed_scores: list[float] = []

        def run_search_seed(
            seed_index: int, seed: int
        ) -> tuple[SimulationExecutionResult, CalibrationScore]:
            _print_simulation_run_header(
                options=options,
                phase="search",
                trial_number=trial.number,
                seed=seed,
                search_trial_index=trial.number + 1,
                search_seed_index=seed_index,
                search_seed_total=len(search_seeds),
            )
            if search_parallelism > 1:
                print(f"[trial {trial.number} seed {seed}] simulator started", flush=True)
            return _run_and_score_candidate_with_optional_worker(
                base_config_text=base_config_text,
                parameters=parameters,
                seed=seed,
                trial_number=trial.number,
                phase="search",
                options=options,
                output_dir=output_dir,
                config_dir=config_dir,
                simulations_root=simulations_root,
                simulator_path=simulator_path,
                benchmark_returns=benchmark_returns,
                runner=runner,
                prune_csv_after_scoring=not options.keep_run_csv,
            )

        def record_search_result(
            seed_index: int,
            result: tuple[SimulationExecutionResult, CalibrationScore],
        ) -> None:
            execution, score = result
            seed_scores.append(score.score)
            trials_writer.append(
                _build_trial_record(
                    trial_number=trial.number,
                    phase="search",
                    seed=search_seeds[seed_index - 1],
                    parameters=parameters,
                    execution=execution,
                    score=score,
                )
            )
            if search_parallelism > 1:
                print(
                    f"[trial {trial.number} seed {search_seeds[seed_index - 1]}] "
                    f"{execution.status}",
                    flush=True,
                )

        map_in_order(
            search_seeds,
            run_search_seed,
            jobs=options.jobs,
            on_result=record_search_result,
            # The first run of a fresh experiment dir writes the manifest
            # header; that check-then-write is not safe against a concurrent
            # writer, so it must finish before the pool opens.
            run_first_synchronously=not (
                simulations_root / "search" / "experiment_manifest.csv"
            ).exists(),
        )
        trial.set_user_attr("seed_scores", list(seed_scores))
        return _aggregate_search_scores(seed_scores, options.search_seed_aggregate)

    callbacks = [_build_stopping_callback(options, best_value)]
    study.optimize(objective, n_trials=options.trials, callbacks=callbacks)

    complete_trials = [
        trial
        for trial in study.trials
        if trial.value is not None and getattr(trial.state, "name", "") == "COMPLETE"
    ]
    if not complete_trials:
        raise RuntimeError("Calibration finished without any completed Optuna trials.")

    validation_results = _validate_top_candidates(
        complete_trials=complete_trials,
        base_config_text=base_config_text,
        options=options,
        output_dir=output_dir,
        config_dir=config_dir,
        simulations_root=simulations_root,
        simulator_path=simulator_path,
        benchmark_returns=benchmark_returns,
        trials_writer=trials_writer,
        runner=runner,
        validation_seeds=validation_seeds,
    )
    verdicts_evaluated = _attach_candidate_robustness(
        validation_results,
        validation_root=simulations_root / "validation",
        options=options,
        settings=settings,
    )
    if verdicts_evaluated:
        robustness_verdicts_status = "evaluated"
    elif len(validation_seeds) < minimum_seeds:
        _print_fit_only_fallback_banner(len(validation_seeds), settings)
        robustness_verdicts_status = "not_available_insufficient_seeds"
    else:
        robustness_verdicts_status = "not_available_evaluation_failed"
    best_validation = min(
        validation_results,
        key=lambda row: (row["robust_ranking_score"], row["trial_number"]),
    )
    best_parameters = dict(best_validation["parameters"])
    best_seed_runs = list(best_validation["run_dirs"])
    if not best_seed_runs:
        raise RuntimeError(
            _format_missing_validation_archives_message(best_validation, simulator_path)
        )

    best_config_path = _write_best_config(
        output_dir=output_dir,
        base_config_text=base_config_text,
        parameters=best_parameters,
        seed=primary_seed,
    )
    best_runs_dir = _copy_best_runs(output_dir, best_seed_runs)
    best_trial_number = int(best_validation["trial_number"])
    calibration_report_path = _write_calibration_report_safely(
        output_dir=output_dir,
        options=options,
        settings=settings,
        candidate_summary=_build_candidate_summary_frame(validation_results, best_trial_number),
        candidate_verdicts=_build_candidate_verdicts_frame(validation_results),
        best_trial_number=best_trial_number,
        validation_seed_count=len(validation_seeds),
        estimated_total_runs=estimated_total_runs,
    )
    best_runs_report_path = _write_best_runs_robustness_report_safely(
        best_runs_dir=best_runs_dir,
        output_dir=output_dir,
        options=options,
    )
    holdout_path = _write_holdout_validation(
        options=options,
        best_runs_dir=best_runs_dir,
        benchmark_dir=options.benchmark_dir,
    )
    if not options.keep_run_csv:
        _prune_calibration_csv_artifacts(
            simulations_root=simulations_root,
            validation_results=validation_results,
            best_runs_dir=best_runs_dir,
        )
    summary_path = _write_summary(
        output_dir=output_dir,
        options=options,
        study=study,
        best_validation=best_validation,
        best_config_path=best_config_path,
        best_runs_dir=best_runs_dir,
        holdout_path=holdout_path,
        search_space_path=options.search_space,
        benchmark_ids=sorted(benchmark_returns),
        settings=settings,
        validation_seeds=validation_seeds,
        search_seeds=search_seeds,
        estimated_total_runs=estimated_total_runs,
        robustness_verdicts_status=robustness_verdicts_status,
        calibration_report_path=calibration_report_path,
        best_runs_report_path=best_runs_report_path,
    )
    print(f"Calibration summary: {summary_path}")
    print(f"Best config: {best_config_path}")
    print(f"Best runs: {best_runs_dir}")
    if calibration_report_path is not None:
        print(f"Calibration report: {calibration_report_path}")
    if best_runs_report_path is not None:
        print(f"Best-runs robustness report: {best_runs_report_path}")
    return output_dir

def _resolve_settings(options: CalibrationOptions) -> CalibrationSettings:
    """Load calibration settings and apply CLI convenience overrides."""

    settings = load_calibration_settings(options.settings_path)
    if options.robustness_penalty_weight is not None:
        settings = replace(
            settings,
            ranking=replace(
                settings.ranking,
                robustness_penalty_weight=float(options.robustness_penalty_weight),
            ),
        )
    return settings

def _announce_run_budget(
    options: CalibrationOptions,
    settings: CalibrationSettings,
    validation_seeds: tuple[int, ...],
    search_seeds: tuple[int, ...],
) -> int:
    """Print the campaign's estimated simulator-run cost and any budget warnings.

    Warnings never abort the study: an oversized campaign is a deliberate
    user choice, and a low validation-seed count degrades gracefully to the
    fit-only ranking.
    """

    candidate_count = max(1, options.top_candidates)
    estimated_total = (
        options.trials * len(search_seeds) + candidate_count * len(validation_seeds)
    )
    print(
        f"Estimated simulator runs: {estimated_total} "
        f"({options.trials} search trials x {len(search_seeds)} search seed(s) + "
        f"{candidate_count} candidates x {len(validation_seeds)} validation seeds)"
    )
    if estimated_total > settings.budget.max_total_runs:
        print(
            f"Warning: estimated {estimated_total} runs exceed the configured "
            f"budget of {settings.budget.max_total_runs}. Reduce --trials, "
            "--search-seeds, --top-candidates, or --validation-seeds to shrink "
            "the campaign."
        )
    if len(validation_seeds) < settings.verdict_thresholds.minimum_seeds_for_verdicts:
        _print_fit_only_fallback_banner(len(validation_seeds), settings)
    return estimated_total

def _print_fit_only_fallback_banner(
    validation_seed_count: int,
    settings: CalibrationSettings,
) -> None:
    """Make the fit-only ranking degradation impossible to miss.

    Printed both before the study starts and again after validation, because
    the start-of-run warning scrolls away during a multi-hour campaign.
    """

    minimum_seeds = settings.verdict_thresholds.minimum_seeds_for_verdicts
    border = "=" * 72
    print(border)
    print("WARNING: ROBUSTNESS VERDICTS DISABLED")
    print(
        f"  {validation_seed_count} validation seed(s) is below the minimum of "
        f"{minimum_seeds} required for seed-robustness verdicts."
    )
    print("  Candidate ranking falls back to the fit-only rule")
    print("  (mean validation score + std) with no robustness penalty.")
    print(
        "  Fix: pass --validation-seeds, e.g. '55,101:109' "
        f"(>= {settings.budget.recommended_min_validation_seeds} seeds recommended)."
    )
    print(border)

def options_to_json(options: CalibrationOptions) -> str:
    """Serialise calibration options for diagnostics or tests."""

    payload = asdict(options)
    for key, value in list(payload.items()):
        if isinstance(value, Path):
            payload[key] = str(value)
    return json.dumps(payload, indent=2, sort_keys=True)
