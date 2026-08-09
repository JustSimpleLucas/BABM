"""Per-trial bookkeeping for the calibration search.

These helpers own the Optuna-facing mechanics — scoring aggregation, the
early-stopping callback, and the trial record written to CSV — so the study
orchestration reads as a sequence of phases rather than a mix of phases and
record keeping.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable
import numpy as np
from .models import CalibrationOptions, CalibrationScore, SimulationExecutionResult


def _build_trial_record(
    *,
    trial_number: int,
    phase: str,
    seed: int,
    parameters: dict[str, object],
    execution: SimulationExecutionResult,
    score: CalibrationScore,
) -> dict[str, object]:
    record: dict[str, object] = {
        "trial_number": trial_number,
        "phase": phase,
        "seed": seed,
        "status": execution.status,
        "score": score.score,
        "run_id": execution.run_dir.name if execution.run_dir is not None else "",
        "return_code": execution.return_code,
        "message": execution.message,
    }
    for key, value in score.components.items():
        record[f"component_{key}"] = value
    for key, value in parameters.items():
        record[f"param_{key}"] = value
    return record

class _TrialCsvWriter:
    """Append trial records to calibration_trials.csv without full rewrites.

    The previous implementation rewrote the whole CSV after every trial,
    O(n^2) over a study. Appending keeps the file valid and tail-able during
    a multi-hour run. The header is only ever extended (never reordered), so
    a full rewrite happens at most once per new record shape — e.g. when a
    failed trial's reduced component set is followed by a complete one.
    """

    def __init__(self, path: Path, records: list[dict[str, object]]) -> None:
        self._path = path
        self._records = records
        self._columns: list[str] = []

    def append(self, record: dict[str, object]) -> None:
        self._records.append(record)
        new_keys = [key for key in record if key not in self._columns]
        if new_keys or not self._path.exists():
            self._columns.extend(new_keys)
            self._rewrite()
            return
        with self._path.open("a", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=self._columns, restval="").writerow(record)

    def _rewrite(self) -> None:
        with self._path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self._columns, restval="")
            writer.writeheader()
            writer.writerows(self._records)

def _aggregate_search_scores(seed_scores: list[float], aggregate: str) -> float:
    """Combine per-seed search scores into one Optuna objective value.

    ``mean`` keeps FAILED_TRIAL_SCORE dominant, so a candidate that crashes on
    any search seed is effectively rejected; ``median`` tolerates one bad seed.
    """

    if aggregate == "median":
        return float(np.median(seed_scores))
    return float(np.mean(seed_scores))

def _build_stopping_callback(options: CalibrationOptions, best_value: dict[str, float]) -> Callable:
    def callback(study: Any, trial: Any) -> None:
        if trial.value is None:
            return
        value = float(trial.value)
        if value + 1.0e-12 < best_value["score"]:
            best_value["score"] = value
            best_value["stale_trials"] = 0
        else:
            best_value["stale_trials"] += 1

        if options.score_threshold is not None and value <= options.score_threshold:
            study.stop()
        if (
            options.no_improvement_trials is not None
            and best_value["stale_trials"] >= options.no_improvement_trials
        ):
            study.stop()

    return callback

def _import_optuna() -> Any:
    try:
        import optuna
    except ImportError as exc:  # pragma: no cover - depends on local environment.
        raise RuntimeError(
            "Optuna is required for calibration. Install project dependencies with "
            "'.venv/bin/pip install -r requirements.txt'."
        ) from exc
    return optuna
