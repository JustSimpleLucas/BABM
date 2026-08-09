"""Output artefacts written at the end of a calibration study.

Every function here turns finished search state into a file on disk: the best
config, the summary JSON, the holdout report, the copied best runs. Keeping
them together means the study orchestration never interleaves computation with
file layout decisions.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Any
import numpy as np
import pandas as pd
from abm_analysis.report import (
    build_calibration_report,
    build_comparison_report,
    build_seed_robustness_report,
)
from .config import patch_config_text
from .execution import _prune_run_csv_artifacts
from .models import CalibrationOptions, CalibrationSettings


def _write_calibration_report_safely(
    *,
    output_dir: Path,
    options: CalibrationOptions,
    settings: CalibrationSettings,
    candidate_summary: pd.DataFrame,
    candidate_verdicts: pd.DataFrame,
    best_trial_number: int,
    validation_seed_count: int,
    estimated_total_runs: int,
) -> Path | None:
    """Write the cross-candidate report; a failure must not void the study."""

    try:
        return build_calibration_report(
            output_dir,
            calibration_name=options.calibration_name,
            candidate_summary=candidate_summary,
            candidate_verdicts=candidate_verdicts,
            best_trial_number=best_trial_number,
            robustness_penalty_weight=settings.ranking.robustness_penalty_weight,
            borderline_credit=settings.ranking.borderline_credit,
            validation_seed_count=validation_seed_count,
            estimated_total_runs=estimated_total_runs,
        )
    except Exception as exc:  # noqa: BLE001 - report loss must not void hours of runs.
        print(f"Warning: calibration report generation failed: {exc}")
        return None

def _write_best_runs_robustness_report_safely(
    *,
    best_runs_dir: Path,
    output_dir: Path,
    options: CalibrationOptions,
) -> Path | None:
    """Write the winner's full seed-robustness report from its best_runs copies.

    ``best_runs/`` holds exactly the winner's validation replicates, which is
    the experiment-dir shape the seed-robustness report was built for. Must
    run before CSV pruning removes the heavy per-run artefacts.
    """

    try:
        result = build_seed_robustness_report(
            best_runs_dir,
            output_dir=output_dir / "best_runs_robustness_report",
            phase=options.phase,
            price_column=options.price_column,
        )
        return result.report_path
    except Exception as exc:  # noqa: BLE001 - report loss must not void hours of runs.
        print(f"Warning: best-runs robustness report generation failed: {exc}")
        return None

def _prune_calibration_csv_artifacts(
    *,
    simulations_root: Path,
    validation_results: list[dict[str, object]],
    best_runs_dir: Path,
) -> None:
    """Remove heavy per-run CSV artefacts after calibration scoring is complete."""

    for validation_result in validation_results:
        for run_dir in validation_result.get("run_dirs", []):
            if isinstance(run_dir, Path):
                _prune_run_csv_artifacts(run_dir)

    if best_runs_dir.is_dir():
        for run_dir in best_runs_dir.iterdir():
            if run_dir.is_dir():
                _prune_run_csv_artifacts(run_dir)

    for experiment_dir in [simulations_root / "search", simulations_root / "validation"]:
        manifest_path = experiment_dir / "experiment_manifest.csv"
        if manifest_path.exists():
            manifest_path.unlink()

def _write_best_config(
    *,
    output_dir: Path,
    base_config_text: str,
    parameters: dict[str, object],
    seed: int,
) -> Path:
    best_config_path = output_dir / "best_config.cfg"
    best_config_text = patch_config_text(
        base_config_text,
        {
            **parameters,
            "seed": seed,
            "experiment_output_enabled": True,
            "experiment_root": output_dir,
            "experiment_name": "best_runs",
            "run_label": "best_optuna_config",
            "python_analysis_enabled": True,
            "python_analysis_generate_comparison": True,
        },
    )
    best_config_path.write_text(best_config_text, encoding="utf-8")
    return best_config_path

def _copy_best_runs(output_dir: Path, run_dirs: list[Path]) -> Path:
    best_runs_dir = output_dir / "best_runs"
    best_runs_dir.mkdir(parents=True, exist_ok=True)
    for run_dir in run_dirs:
        target = best_runs_dir / run_dir.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(run_dir, target)
    return best_runs_dir

def _write_holdout_validation(
    *,
    options: CalibrationOptions,
    best_runs_dir: Path,
    benchmark_dir: Path,
) -> Path:
    holdout_dir = best_runs_dir.parent / "holdout_validation"
    holdout_dir.mkdir(parents=True, exist_ok=True)
    if not options.holdout_benchmark_series:
        (holdout_dir / "summary.json").write_text(
            json.dumps(
                {
                    "status": "not_run",
                    "reason": "No holdout benchmark series was supplied.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return holdout_dir

    build_comparison_report(
        best_runs_dir,
        output_dir=holdout_dir,
        phase=options.phase,
        price_column=options.price_column,
        benchmark_dir=benchmark_dir,
        benchmark_series=options.holdout_benchmark_series,
    )
    return holdout_dir

def _write_summary(
    *,
    output_dir: Path,
    options: CalibrationOptions,
    study: Any,
    best_validation: dict[str, object],
    best_config_path: Path,
    best_runs_dir: Path,
    holdout_path: Path,
    search_space_path: Path,
    benchmark_ids: list[str],
    settings: CalibrationSettings,
    validation_seeds: tuple[int, ...],
    search_seeds: tuple[int, ...],
    estimated_total_runs: int,
    robustness_verdicts_status: str,
    calibration_report_path: Path | None,
    best_runs_report_path: Path | None,
) -> Path:
    best_parameters = dict(best_validation["parameters"])
    best_config_json_path = output_dir / "best_config.json"
    best_config_json_path.write_text(
        json.dumps(best_parameters, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outputs = {
        "calibration_trials_csv": "calibration_trials.csv",
        "best_config_cfg": best_config_path.name,
        "best_config_json": best_config_json_path.name,
        "best_runs": best_runs_dir.name,
        "holdout_validation": holdout_path.name,
    }
    if calibration_report_path is not None:
        outputs["calibration_report"] = str(calibration_report_path.relative_to(output_dir))
    if best_runs_report_path is not None:
        outputs["best_runs_robustness_report"] = str(
            best_runs_report_path.relative_to(output_dir)
        )
    summary = {
        "calibration_name": options.calibration_name,
        "created_at_local": datetime.now().isoformat(timespec="seconds"),
        "trial_count": len(study.trials),
        "requested_trials": options.trials,
        "seeds": list(options.seeds),
        "validation_seeds": list(validation_seeds),
        "search_seeds": list(search_seeds),
        "search_seed_aggregate": options.search_seed_aggregate,
        "sampler_seed": options.sampler_seed,
        "estimated_total_runs": estimated_total_runs,
        "robustness_verdicts_status": robustness_verdicts_status,
        "minimum_seeds_for_verdicts": (
            settings.verdict_thresholds.minimum_seeds_for_verdicts
        ),
        "benchmark_ids": benchmark_ids,
        "benchmark_series": options.benchmark_series,
        "holdout_benchmark_series": options.holdout_benchmark_series,
        "search_space": str(search_space_path),
        "robustness_penalty_weight": settings.ranking.robustness_penalty_weight,
        "borderline_credit": settings.ranking.borderline_credit,
        "best_trial_number": best_validation["trial_number"],
        "best_search_score": best_validation["search_score"],
        "best_mean_validation_score": best_validation["mean_validation_score"],
        "best_validation_score_std": best_validation["validation_score_std"],
        "best_ranking_score": best_validation["ranking_score"],
        "best_robustness_pass_rate": _finite_or_null(
            best_validation.get("robustness_pass_rate")
        ),
        "best_robust_ranking_score": _finite_or_null(
            best_validation.get("robust_ranking_score")
        ),
        "best_parameters": best_parameters,
        "outputs": outputs,
    }
    summary_path = output_dir / "calibration_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path

def _finite_or_null(value: object) -> float | None:
    """Keep calibration_summary.json strict-JSON parseable (no NaN tokens)."""

    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None
