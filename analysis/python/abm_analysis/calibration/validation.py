"""Robustness validation of the calibration search's best candidates.

Fit alone can rank a candidate highly on one lucky seed, so the top candidates
are re-run across validation seeds and scored on how consistently they hold up.
This module owns that second pass and the frames that report it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from abm_analysis.archive.data import build_runs_index
from abm_analysis.parallel import map_in_order, resolve_job_count
from .constants import FAILED_TRIAL_SCORE
from .execution import _run_and_score_candidate_with_optional_worker
from .models import (
    CalibrationOptions,
    CalibrationScore,
    CalibrationSettings,
    SimulationExecutionResult,
    SimulatorRunner,
)
from .robustness import (
    CandidateRobustness,
    evaluate_candidate_robustness,
    filter_candidate_runs_index,
    robust_ranking_score,
    summarise_verdicts,
)
from .scoring import _mean_finite
from .trials import _TrialCsvWriter, _build_trial_record


def _attach_candidate_robustness(
    validation_results: list[dict[str, object]],
    *,
    validation_root: Path,
    options: CalibrationOptions,
    settings: CalibrationSettings,
) -> bool:
    """Attach robustness evidence and the combined ranking score per candidate.

    Returns True when at least one candidate produced evaluated verdicts.
    When none did (for example the legacy single-seed configuration), every
    candidate keeps ``robust_ranking_score == ranking_score`` so existing
    invocations select the identical winner.
    """

    try:
        validation_index = build_runs_index(validation_root)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Warning: could not index validation runs for robustness ranking: {exc}")
        validation_index = pd.DataFrame()

    for result in validation_results:
        run_dirs = [path for path in result["run_dirs"] if isinstance(path, Path)]
        candidate_index = filter_candidate_runs_index(validation_index, run_dirs)
        try:
            robustness = evaluate_candidate_robustness(
                run_dirs,
                candidate_index,
                phase=options.phase,
                price_column=options.price_column,
                thresholds=settings.verdict_thresholds,
                borderline_credit=settings.ranking.borderline_credit,
            )
        # Same recoverable failure modes as scoring: archive loading and the
        # statistical pipeline on degenerate series. A candidate whose
        # robustness cannot be evaluated is ranked as non-robust rather than
        # aborting a multi-hour calibration.
        except (
            OSError,
            ValueError,
            KeyError,
            pd.errors.ParserError,
            pd.errors.EmptyDataError,
            np.linalg.LinAlgError,
        ) as exc:
            print(
                "Warning: robustness evaluation failed for trial "
                f"{result['trial_number']}: {exc}"
            )
            robustness = summarise_verdicts(
                pd.DataFrame(),
                seed_count=0,
                borderline_credit=settings.ranking.borderline_credit,
            )
        result["robustness"] = robustness
        result["robustness_pass_rate"] = robustness.pass_rate

    any_evaluated = any(
        np.isfinite(float(result["robustness_pass_rate"])) for result in validation_results
    )
    for result in validation_results:
        if any_evaluated:
            result["robust_ranking_score"] = robust_ranking_score(
                float(result["ranking_score"]),
                float(result["robustness_pass_rate"]),
                penalty_weight=settings.ranking.robustness_penalty_weight,
            )
        else:
            result["robust_ranking_score"] = float(result["ranking_score"])
    if not any_evaluated:
        print(
            "Robustness verdicts unavailable for every candidate; ranking uses "
            "the fit-only rule (mean validation score + std)."
        )
    return any_evaluated

def _build_candidate_summary_frame(
    validation_results: list[dict[str, object]],
    best_trial_number: int,
) -> pd.DataFrame:
    """One row per validated candidate, ordered by the final ranking."""

    ordered = sorted(
        validation_results,
        key=lambda row: (row["robust_ranking_score"], row["trial_number"]),
    )
    rows: list[dict[str, object]] = []
    for result in ordered:
        robustness = result.get("robustness")
        record: dict[str, object] = {
            "trial_number": result["trial_number"],
            "search_score": result["search_score"],
            "mean_validation_score": result["mean_validation_score"],
            "validation_score_std": result["validation_score_std"],
            "ranking_score": result["ranking_score"],
            "robustness_pass_rate": result.get("robustness_pass_rate", float("nan")),
            "robustness_pass_count": (
                robustness.pass_count if isinstance(robustness, CandidateRobustness) else 0
            ),
            "robustness_borderline_count": (
                robustness.borderline_count if isinstance(robustness, CandidateRobustness) else 0
            ),
            "robustness_fail_count": (
                robustness.fail_count if isinstance(robustness, CandidateRobustness) else 0
            ),
            "robustness_not_available_count": (
                robustness.not_available_count
                if isinstance(robustness, CandidateRobustness)
                else 0
            ),
            "seed_count": (
                robustness.seed_count if isinstance(robustness, CandidateRobustness) else 0
            ),
            "robust_ranking_score": result["robust_ranking_score"],
            "selected": result["trial_number"] == best_trial_number,
        }
        for key, value in dict(result["parameters"]).items():
            record[f"param_{key}"] = value
        rows.append(record)
    return pd.DataFrame(rows)

def _build_candidate_verdicts_frame(
    validation_results: list[dict[str, object]],
) -> pd.DataFrame:
    """Concatenate every candidate's verdict table under a trial_number key."""

    frames: list[pd.DataFrame] = []
    for result in validation_results:
        robustness = result.get("robustness")
        if not isinstance(robustness, CandidateRobustness) or robustness.verdicts.empty:
            continue
        frame = robustness.verdicts.copy()
        frame.insert(0, "trial_number", result["trial_number"])
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["trial_number", "criterion", "verdict"])
    return pd.concat(frames, ignore_index=True)

def _validate_top_candidates(
    *,
    complete_trials: list[Any],
    base_config_text: str,
    options: CalibrationOptions,
    output_dir: Path,
    config_dir: Path,
    simulations_root: Path,
    simulator_path: Path,
    benchmark_returns: dict[str, pd.Series],
    trials_writer: _TrialCsvWriter,
    runner: SimulatorRunner | None,
    validation_seeds: tuple[int, ...],
) -> list[dict[str, object]]:
    top_trials = sorted(complete_trials, key=lambda trial: float(trial.value))[
        : max(1, options.top_candidates)
    ]
    validation_rows: list[dict[str, object]] = []
    validation_parallelism = resolve_job_count(options.jobs, len(validation_seeds))
    for frozen_trial in top_trials:
        parameters = dict(frozen_trial.user_attrs.get("full_parameters", frozen_trial.params))
        seed_scores: list[float] = []
        run_dirs: list[Path] = []
        validation_executions: list[SimulationExecutionResult] = []

        def run_validation_seed(
            seed_index: int, seed: int
        ) -> tuple[SimulationExecutionResult, CalibrationScore]:
            _print_simulation_run_header(
                options=options,
                phase="validation",
                trial_number=int(frozen_trial.number),
                seed=seed,
                validation_seed_index=seed_index,
                validation_seed_total=len(validation_seeds),
            )
            if validation_parallelism > 1:
                print(
                    f"[validation trial {frozen_trial.number} seed {seed}] simulator started",
                    flush=True,
                )
            return _run_and_score_candidate_with_optional_worker(
                base_config_text=base_config_text,
                parameters=parameters,
                seed=seed,
                trial_number=int(frozen_trial.number),
                phase="validation",
                options=options,
                output_dir=output_dir,
                config_dir=config_dir,
                simulations_root=simulations_root,
                simulator_path=simulator_path,
                benchmark_returns=benchmark_returns,
                runner=runner,
                prune_csv_after_scoring=False,
            )

        def record_validation_result(
            seed_index: int,
            result: tuple[SimulationExecutionResult, CalibrationScore],
        ) -> None:
            execution, score = result
            seed_scores.append(score.score)
            validation_executions.append(execution)
            if execution.run_dir is not None:
                run_dirs.append(execution.run_dir)
            trials_writer.append(
                _build_trial_record(
                    trial_number=int(frozen_trial.number),
                    phase="validation",
                    seed=validation_seeds[seed_index - 1],
                    parameters=parameters,
                    execution=execution,
                    score=score,
                )
            )
            if validation_parallelism > 1:
                print(
                    f"[validation trial {frozen_trial.number} "
                    f"seed {validation_seeds[seed_index - 1]}] {execution.status}",
                    flush=True,
                )

        map_in_order(
            validation_seeds,
            run_validation_seed,
            jobs=options.jobs,
            on_result=record_validation_result,
            # The first run of a fresh experiment dir writes the manifest
            # header; that check-then-write is not safe against a concurrent
            # writer, so it must finish before the pool opens.
            run_first_synchronously=not (
                simulations_root / "validation" / "experiment_manifest.csv"
            ).exists(),
        )

        mean_score = _mean_finite(seed_scores, fallback=FAILED_TRIAL_SCORE)
        score_std = float(np.std(seed_scores, ddof=1)) if len(seed_scores) > 1 else 0.0
        validation_rows.append(
            {
                "trial_number": int(frozen_trial.number),
                "search_score": float(frozen_trial.value),
                "mean_validation_score": mean_score,
                "validation_score_std": score_std,
                "ranking_score": float(mean_score + score_std),
                "parameters": parameters,
                "run_dirs": run_dirs,
                "executions": validation_executions,
            }
        )
    return validation_rows

def _format_missing_validation_archives_message(
    best_validation: dict[str, object],
    simulator_path: Path,
) -> str:
    """Explain why calibration could not promote a validated candidate."""

    lines = [
        "Calibration did not produce any validation run archives.",
        f"Simulator: {simulator_path}",
        f"Trial: {best_validation.get('trial_number', '<unknown>')}",
    ]
    executions = [
        execution
        for execution in best_validation.get("executions", [])
        if isinstance(execution, SimulationExecutionResult)
    ]
    if not executions:
        lines.append("No validation execution details were captured.")
        return "\n".join(lines)

    for index, execution in enumerate(executions, start=1):
        lines.extend(
            [
                f"Validation execution {index}:",
                f"  Config: {execution.config_path}",
                f"  Status: {execution.status}",
                f"  Return code: {execution.return_code}",
            ]
        )
        if execution.message:
            lines.append(f"  Message: {_single_line_excerpt(execution.message)}")
        if execution.stderr:
            lines.append(f"  Stderr: {_single_line_excerpt(execution.stderr)}")
        if execution.stdout:
            lines.append(f"  Stdout: {_single_line_excerpt(execution.stdout)}")
    return "\n".join(lines)

def _single_line_excerpt(text: str, *, limit: int = 600) -> str:
    """Keep subprocess diagnostics readable in a raised exception."""

    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[:limit - 3]}..."

def _print_simulation_run_header(
    *,
    options: CalibrationOptions,
    phase: str,
    trial_number: int,
    seed: int,
    search_trial_index: int | None = None,
    search_seed_index: int | None = None,
    search_seed_total: int | None = None,
    validation_seed_index: int | None = None,
    validation_seed_total: int | None = None,
) -> None:
    """Print a compact label before the C++ step progress bar starts."""

    if not options.show_simulation_progress:
        return
    if phase == "search" and search_trial_index is not None:
        seed_suffix = (
            f", seed {search_seed_index}/{search_seed_total}"
            if search_seed_index is not None and (search_seed_total or 0) > 1
            else ""
        )
        print(
            f"\nCalibration search simulation {search_trial_index}/{options.trials} "
            f"(trial {trial_number}, seed {seed}{seed_suffix})",
            flush=True,
        )
        return
    if phase == "validation" and validation_seed_index is not None:
        seed_total = (
            validation_seed_total if validation_seed_total is not None else len(options.seeds)
        )
        print(
            f"\nCalibration validation simulation "
            f"(trial {trial_number}, seed {seed}, "
            f"seed {validation_seed_index}/{seed_total})",
            flush=True,
        )
