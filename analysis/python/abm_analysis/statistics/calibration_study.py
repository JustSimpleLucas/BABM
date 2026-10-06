"""Reading a finished calibration study, and taking its score apart.

A calibration study ends with one number per trial, and one number cannot say
*why* a candidate scored what it did, nor whether the search is still finding
anything. The study's own files can: ``calibration_trials.csv`` keeps every
trial's score together with the components it was built from, and the summary
JSON records the settings of the run. This module reads those files and answers
the questions a number hides — is the best score still improving, how much of it
is a stylised-fact penalty rather than distance from the benchmarks, and how
many of the three stylised facts did the *best* trial still fail?

The score is built (``calibration.scoring``) as::

    score = market_distance + stylised_penalty

where ``stylised_penalty`` adds one fixed weight for each of three stylised facts
the candidate's returns fail to reproduce. The identity is exact in the trial
table, and :func:`decompose_scores` checks it rather than assuming it, so a study
written by a changed scoring rule is reported as such instead of mis-drawn.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from abm_analysis.archive.archives import resolve_artifact_path


#: The marker that makes a directory a calibration study. ``summary`` and the
#: candidate table may be absent from a study that was interrupted, but the trial
#: table is written trial by trial from the first one, so it is always there.
CALIBRATION_TRIALS_FILENAME = "calibration_trials.csv"
CALIBRATION_SUMMARY_FILENAME = "calibration_summary.json"
CANDIDATE_SUMMARY_FILENAME = "candidate_validation_summary.csv"
CANDIDATE_SUMMARY_DIRECTORY = "calibration_report"

#: Trial table values the readers key on.
SEARCH_PHASE = "search"
VALIDATION_PHASE = "validation"
COMPLETED_STATUS = "completed"

#: Weights of the three stylised-fact penalties, in the order the scorer adds them.
PENALTY_WEIGHT_KEYS = (
    "autocorrelation_penalty",
    "fat_tail_penalty",
    "volatility_clustering_penalty",
)

#: Largest gap between ``score`` and the sum of its two parts that still counts as
#: the identity holding. Written scores carry full double precision.
IDENTITY_TOLERANCE = 1.0e-9


@dataclass(frozen=True)
class CalibrationStudy:
    """The files of one calibration study, read.

    ``score_weights`` are the weights the score was built with. When the study
    recorded them they are exact; a study written before they were recorded gets
    the library defaults and ``weights_recorded`` is false, so the reader knows
    the decomposition rests on an assumption about how that study was run.
    """

    name: str
    directory: Path
    trials: pd.DataFrame
    candidates: pd.DataFrame
    summary: dict[str, Any]
    score_weights: dict[str, float]
    weights_recorded: bool

    @property
    def parameter_columns(self) -> list[str]:
        """Return the trial table's searched-parameter columns."""

        return [column for column in self.trials.columns if column.startswith("param_")]


@dataclass(frozen=True)
class ScoreDecomposition:
    """A study's search scores taken apart into distance and penalty."""

    trial_number: pd.Series
    market_distance: pd.Series
    stylised_penalty: pd.Series
    identity_holds: bool
    largest_residual: float | None
    penalty_per_fact: float | None
    penalty_levels: pd.DataFrame


def is_calibration_study(directory: Path) -> bool:
    """Return whether a directory holds a calibration study's trial table."""

    return directory.is_dir() and resolve_artifact_path(directory, CALIBRATION_TRIALS_FILENAME) is not None


def read_calibration_study(study_dir: Path | str) -> CalibrationStudy:
    """Read a calibration study's trial table, summary and candidate ranking.

    Raises:
        FileNotFoundError: when the directory has no trial table.
    """

    directory = Path(study_dir).expanduser().resolve()
    trials_path = resolve_artifact_path(directory, CALIBRATION_TRIALS_FILENAME)
    if trials_path is None:
        raise FileNotFoundError(
            f"Not a calibration study (no {CALIBRATION_TRIALS_FILENAME}): {directory}"
        )

    candidates_path = resolve_artifact_path(
        directory / CANDIDATE_SUMMARY_DIRECTORY, CANDIDATE_SUMMARY_FILENAME
    )
    summary = _read_summary(directory)
    weights, recorded = _score_weights(summary)
    return CalibrationStudy(
        name=str(summary.get("calibration_name") or directory.name),
        directory=directory,
        trials=pd.read_csv(trials_path),
        candidates=pd.read_csv(candidates_path) if candidates_path is not None else pd.DataFrame(),
        summary=summary,
        score_weights=weights,
        weights_recorded=recorded,
    )


def search_trials(study: CalibrationStudy) -> pd.DataFrame:
    """Return the completed search-phase trials in trial order.

    Failed trials are left out: the scorer gives them a sentinel score a billion
    times any real one, which would flatten every chart that includes it.
    """

    trials = study.trials
    keep = pd.Series(True, index=trials.index)
    if "phase" in trials.columns:
        keep &= trials["phase"].astype(str) == SEARCH_PHASE
    if "status" in trials.columns:
        keep &= trials["status"].astype(str) == COMPLETED_STATUS
    return trials[keep].sort_values("trial_number").reset_index(drop=True)


def failed_search_trial_count(study: CalibrationStudy) -> int:
    """Return how many search-phase trials did not complete."""

    trials = study.trials
    if "status" not in trials.columns:
        return 0
    in_search = (
        trials["phase"].astype(str) == SEARCH_PHASE if "phase" in trials.columns else True
    )
    return int(((trials["status"].astype(str) != COMPLETED_STATUS) & in_search).sum())


def validation_scores(study: CalibrationStudy) -> pd.DataFrame:
    """Return each validated candidate's score on each validation seed.

    The search scored every trial on one seed. Validation re-runs the best few on
    many, so the spread here is how much of a search score was the seed.
    """

    trials = study.trials
    if "phase" not in trials.columns:
        return pd.DataFrame(columns=["trial_number", "seed", "score"])
    validation = trials[trials["phase"].astype(str) == VALIDATION_PHASE]
    columns = ["trial_number", "seed", "score"]
    if validation.empty or not set(columns) <= set(validation.columns):
        return pd.DataFrame(columns=columns)
    return validation[columns].sort_values(["trial_number", "seed"]).reset_index(drop=True)


def build_calibration_progress(search: pd.DataFrame) -> pd.DataFrame:
    """Return each search trial's score beside the best score reached so far.

    The running minimum is the answer to "is the search still finding anything":
    a curve that went flat many trials ago says more trials will not help, however
    low the final number looks.
    """

    scores = _numeric_column(search, "score")
    return pd.DataFrame(
        {
            "trial_number": _numeric_column(search, "trial_number"),
            "score": scores,
            "best_so_far": scores.cummin(),
        }
    )


def decompose_scores(search: pd.DataFrame, score_weights: dict[str, float]) -> ScoreDecomposition:
    """Split the search scores into benchmark distance and stylised-fact penalty.

    The penalty is added once per failed stylised fact, so when the three penalty
    weights are equal a penalty of ``k`` times that weight means exactly ``k``
    facts failed. With unequal weights the count cannot be recovered from the
    penalty alone, and ``penalty_per_fact`` is ``None``.

    Returns:
        The two parts per trial, whether ``score`` equals their sum, and how many
        trials sit at each distinct penalty level. A study in which no trial has a
        penalty of zero never found parameters that reproduce all three facts.
    """

    score = _numeric_column(search, "score")
    distance = _numeric_column(search, "component_market_distance")
    penalty = _numeric_column(search, "component_stylised_penalty")

    residual = (score - distance - penalty).abs()
    largest = float(residual.max()) if residual.notna().any() else None
    weights = [score_weights.get(key) for key in PENALTY_WEIGHT_KEYS]
    equal = all(weight is not None for weight in weights) and len(set(weights)) == 1
    per_fact = float(weights[0]) if equal and weights[0] else None

    levels = (
        penalty.round(9)
        .value_counts()
        .sort_index()
        .rename_axis("penalty")
        .reset_index(name="trials")
    )
    levels["failed_facts"] = (
        (levels["penalty"] / per_fact).round().astype(int) if per_fact else np.nan
    )
    return ScoreDecomposition(
        trial_number=_numeric_column(search, "trial_number"),
        market_distance=distance,
        stylised_penalty=penalty,
        identity_holds=bool(largest is not None and largest <= IDENTITY_TOLERANCE),
        largest_residual=largest,
        penalty_per_fact=per_fact,
        penalty_levels=levels,
    )


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return one column as numbers, or an all-missing series when it is absent.

    A study written before a component existed simply lacks its column; the
    decomposition should then report the identity as unverifiable rather than fail.
    """

    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _read_summary(directory: Path) -> dict[str, Any]:
    """Read ``calibration_summary.json``, tolerating a missing or unreadable file."""

    path = directory / CALIBRATION_SUMMARY_FILENAME
    if not path.is_file():
        return {}
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return content if isinstance(content, dict) else {}


def _score_weights(summary: dict[str, Any]) -> tuple[dict[str, float], bool]:
    """Return the study's score weights and whether the study recorded them.

    A study written before the weights were recorded falls back to the library's
    defaults. Imported on demand, because the fallback is only for old archives
    and the calibration package is not otherwise needed to read a study.
    """

    recorded = summary.get("score_weights")
    if isinstance(recorded, dict) and recorded:
        return {str(key): float(value) for key, value in recorded.items()}, True

    from abm_analysis.calibration.models import ScoreWeights

    return {key: float(value) for key, value in asdict(ScoreWeights()).items()}, False
