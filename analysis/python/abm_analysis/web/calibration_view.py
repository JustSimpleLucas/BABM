"""Calibration explorer payload: what a study's search actually did.

A calibration study reports one winner. The questions a thesis has to answer
about it are the ones a winner hides: did the search keep finding better
candidates or stall early, how much of the winning score is distance from the
empirical benchmarks and how much is a penalty for stylised facts the model
still fails, which of the searched parameters the score responded to, and how
much of a candidate's search score was luck of the one seed it was scored on.

Nothing here computes a research statistic. The running best, the decomposition
and the penalty levels are ``statistics.calibration_study``'s, and the candidate
ranking is read from the table the study itself wrote
(``calibration_report/candidate_validation_summary.csv``), so a number on the
page and the same number in the study's files cannot disagree. This module
decides only which column becomes which payload field.

The studies in an archive may predate the model they now describe — a calibration
is a snapshot of a search against one version of the simulator — so the payload
always carries when the study was made, and says plainly where its own record is
incomplete rather than guessing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from abm_analysis.statistics.calibration_study import (
    CalibrationStudy,
    ScoreDecomposition,
    build_calibration_progress,
    decompose_scores,
    failed_search_trial_count,
    read_calibration_study,
    search_trials,
    validation_scores,
)
from abm_analysis.web.metrics import metric, values_of
from abm_analysis.web.serialisation import json_safe, numeric_or_none


#: Columns of the candidate table, as (column in the study's table, heading,
#: number format). A deliberate subset: fit, seed spread, robustness, and rank.
CANDIDATE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("trial_number", "Trial", "integer"),
    ("search_score", "Search score", "decimal"),
    ("mean_validation_score", "Mean validation score", "decimal"),
    ("validation_score_std", "Validation s.d.", "decimal"),
    ("robustness_pass_rate", "Robustness pass rate", "percent_fraction"),
    ("ranking_score", "Ranking score", "decimal"),
    ("robust_ranking_score", "Robust ranking score", "decimal"),
    ("seed_count", "Seeds", "integer"),
)

#: Prefix and noise words stripped from a searched parameter's column name to
#: make its heading: ``param_control_loss_aversion`` reads "Loss aversion".
PARAMETER_PREFIX = "param_"
PARAMETER_NOISE_PREFIX = "control_"


def describe_calibration_study(study_dir: Path, relative_path: str) -> dict[str, Any]:
    """Return the one-line description of a study for the sidebar listing."""

    study = read_calibration_study(study_dir)
    search = search_trials(study)
    scores = pd.to_numeric(search["score"], errors="coerce")
    return json_safe(
        {
            "path": relative_path,
            "name": study.name,
            "created_at": study.summary.get("created_at_local"),
            "trial_count": int(len(search)),
            "best_search_score": float(scores.min()) if scores.notna().any() else None,
            "best_trial": numeric_or_none(study.summary.get("best_trial_number")),
        }
    )


def build_calibration_view(study_dir: Path, relative_path: str) -> dict[str, Any]:
    """Build the explorer payload for one calibration study.

    Args:
        study_dir: Directory of the study (holding ``calibration_trials.csv``).
        relative_path: The handle the client used, echoed back so the interface
            can tell which study a reply belongs to.
    """

    study = read_calibration_study(study_dir)
    search = search_trials(study)
    decomposition = decompose_scores(search, study.score_weights)
    selected, candidate_trials = _candidate_trials(study)

    return json_safe(
        {
            "path": relative_path,
            "name": study.name,
            "created_at": study.summary.get("created_at_local"),
            "chips": _chips(study),
            "metrics": _metrics(study, search, decomposition),
            "progress": _progress(search),
            "decomposition": _decomposition(search, decomposition, study),
            "parameters": _parameters(study, search, selected, candidate_trials),
            "candidates": _candidates(study),
            "validation": _validation(study),
            "notes": _notes(study, search, decomposition),
        }
    )


def _chips(study: CalibrationStudy) -> list[dict[str, Any]]:
    """List the settings that identify how the study was run."""

    summary = study.summary
    entries = [
        ("Created", summary.get("created_at_local")),
        ("Benchmarks", ", ".join(summary.get("benchmark_ids") or []) or None),
        ("Search seeds", ", ".join(str(seed) for seed in summary.get("search_seeds") or []) or None),
        (
            "Validation seeds",
            f"{len(summary.get('validation_seeds') or [])} seeds"
            if summary.get("validation_seeds")
            else None,
        ),
        ("Sampler seed", summary.get("sampler_seed")),
        ("Score weights", "recorded" if study.weights_recorded else "library defaults assumed"),
    ]
    return [{"label": label, "value": str(value)} for label, value in entries if value is not None]


def _metrics(
    study: CalibrationStudy,
    search: pd.DataFrame,
    decomposition: ScoreDecomposition,
) -> list[dict[str, Any]]:
    """Build the headline tiles, leading with where the search ended."""

    summary = study.summary
    scores = pd.to_numeric(search["score"], errors="coerce")
    best_position = int(scores.idxmin()) if scores.notna().any() else None
    best_penalty = (
        numeric_or_none(decomposition.stylised_penalty.iloc[best_position])
        if best_position is not None
        else None
    )
    failed_facts = (
        None
        if best_penalty is None or not decomposition.penalty_per_fact
        else round(best_penalty / decomposition.penalty_per_fact)
    )
    return [
        metric("Search trials", len(search), format="integer"),
        metric("Failed trials", failed_search_trial_count(study), format="integer"),
        metric(
            "Best search score",
            float(scores.min()) if scores.notna().any() else None,
            format="decimal",
            emphasis=True,
        ),
        metric(
            "Stylised facts the best trial fails",
            failed_facts,
            format="integer",
            emphasis=True,
        ),
        metric("Best mean validation score", summary.get("best_mean_validation_score"), format="decimal"),
        metric("Best robust ranking score", summary.get("best_robust_ranking_score"), format="decimal"),
        metric("Best robustness pass rate", summary.get("best_robustness_pass_rate"), format="percent_fraction"),
    ]


def _progress(search: pd.DataFrame) -> dict[str, Any]:
    """Build the running-best curve and the individual trial scores."""

    if search.empty:
        return {"available": False}
    progress = build_calibration_progress(search)
    return {
        "available": True,
        "trial": values_of(progress["trial_number"]),
        "score": values_of(progress["score"]),
        "best_so_far": values_of(progress["best_so_far"]),
    }


def _decomposition(
    search: pd.DataFrame,
    decomposition: ScoreDecomposition,
    study: CalibrationStudy,
) -> dict[str, Any]:
    """Build the distance-and-penalty split of every trial's score."""

    if search.empty:
        return {"available": False}
    levels = decomposition.penalty_levels
    return {
        "available": decomposition.identity_holds,
        "identity_holds": decomposition.identity_holds,
        "largest_residual": decomposition.largest_residual,
        "weights_recorded": study.weights_recorded,
        "penalty_per_fact": decomposition.penalty_per_fact,
        "trial": values_of(decomposition.trial_number),
        "market_distance": values_of(decomposition.market_distance),
        "stylised_penalty": values_of(decomposition.stylised_penalty),
        "levels": [
            {
                "penalty": numeric_or_none(row["penalty"]),
                "trials": int(row["trials"]),
                "failed_facts": numeric_or_none(row["failed_facts"]),
            }
            for _, row in levels.iterrows()
        ],
        "minimum_penalty": (
            numeric_or_none(levels["penalty"].min()) if not levels.empty else None
        ),
    }


def _candidate_trials(study: CalibrationStudy) -> tuple[int | None, list[int]]:
    """Return the selected candidate's trial number and every validated candidate's."""

    candidates = study.candidates
    if candidates.empty or "trial_number" not in candidates.columns:
        best = numeric_or_none(study.summary.get("best_trial_number"))
        return (None if best is None else int(best)), []
    trials = [int(value) for value in pd.to_numeric(candidates["trial_number"], errors="coerce").dropna()]
    selected: int | None = None
    if "selected" in candidates.columns:
        flagged = candidates[candidates["selected"].astype(str).str.lower().isin(("true", "1"))]
        if not flagged.empty:
            selected = int(flagged["trial_number"].iloc[0])
    if selected is None:
        best = numeric_or_none(study.summary.get("best_trial_number"))
        selected = None if best is None else int(best)
    return selected, trials


def _parameter_label(column: str) -> str:
    """Turn a searched parameter's column name into a heading."""

    name = column[len(PARAMETER_PREFIX):] if column.startswith(PARAMETER_PREFIX) else column
    if name.startswith(PARAMETER_NOISE_PREFIX):
        name = name[len(PARAMETER_NOISE_PREFIX):]
    text = name.replace("_", " ")
    return text[:1].upper() + text[1:]


def _parameters(
    study: CalibrationStudy,
    search: pd.DataFrame,
    selected: int | None,
    candidate_trials: list[int],
) -> dict[str, Any]:
    """Build each searched parameter's value against the score it earned."""

    if search.empty:
        return {"available": False, "series": []}
    series: list[dict[str, Any]] = []
    for column in study.parameter_columns:
        values = pd.to_numeric(search[column], errors="coerce")
        if values.notna().sum() < 2:
            continue
        series.append(
            {
                "key": column[len(PARAMETER_PREFIX):],
                "label": _parameter_label(column),
                "trial": values_of(search["trial_number"]),
                "value": values_of(values),
                "score": values_of(search["score"]),
                "constant": bool(values.nunique() == 1),
            }
        )
    return {
        "available": bool(series),
        "selected_trial": selected,
        "candidate_trials": candidate_trials,
        "series": series,
    }


def _candidates(study: CalibrationStudy) -> dict[str, Any]:
    """Build the validated-candidate table from the study's own ranking file."""

    candidates = study.candidates
    if candidates.empty:
        return {"available": False, "columns": [], "rows": []}
    columns = [
        (column, heading, number_format)
        for column, heading, number_format in CANDIDATE_COLUMNS
        if column in candidates.columns
    ]
    rows: list[dict[str, Any]] = []
    for _, record in candidates.iterrows():
        row: dict[str, Any] = {
            column: numeric_or_none(record[column]) for column, _heading, _format in columns
        }
        row["selected"] = str(record.get("selected", "")).strip().lower() in ("true", "1")
        rows.append(row)
    return {
        "available": True,
        "columns": [
            {"key": column, "label": heading, "format": number_format}
            for column, heading, number_format in columns
        ],
        "rows": rows,
    }


def _validation(study: CalibrationStudy) -> dict[str, Any]:
    """Build each validated candidate's score on every validation seed."""

    scores = validation_scores(study)
    if scores.empty:
        return {"available": False, "candidates": []}
    candidates = study.candidates
    search_score = (
        dict(
            zip(
                pd.to_numeric(candidates["trial_number"], errors="coerce"),
                pd.to_numeric(candidates["search_score"], errors="coerce"),
            )
        )
        if {"trial_number", "search_score"} <= set(candidates.columns)
        else {}
    )
    entries = []
    for trial_number, group in scores.groupby("trial_number", sort=True):
        entries.append(
            {
                "trial_number": int(trial_number),
                "search_score": numeric_or_none(search_score.get(trial_number)),
                "seed": values_of(group["seed"]),
                "score": values_of(group["score"]),
            }
        )
    return {"available": True, "candidates": entries}


def _notes(
    study: CalibrationStudy,
    search: pd.DataFrame,
    decomposition: ScoreDecomposition,
) -> list[str]:
    """State what the study's record supports, and where it stops."""

    notes: list[str] = []
    failed = failed_search_trial_count(study)
    if failed:
        notes.append(
            f"{failed} search trial(s) failed and are left out of every chart on this page."
        )
    if not decomposition.identity_holds and not search.empty:
        residual = decomposition.largest_residual
        notes.append(
            "In this study the score is not market distance plus stylised-fact penalty "
            + (
                f"(largest gap {residual:.3g}), "
                if residual is not None
                else "(its component columns are missing), "
            )
            + "so its scoring rule differs from the current one and the decomposition is not drawn."
        )
    if decomposition.identity_holds and not study.weights_recorded:
        notes.append(
            "This study did not record its score weights, so the penalty is read as "
            "the library defaults would give it: "
            + (
                f"{decomposition.penalty_per_fact:g} per failed stylised fact."
                if decomposition.penalty_per_fact
                else "the three penalties differ, so the number of failed facts cannot be recovered."
            )
        )
    levels = decomposition.penalty_levels
    if decomposition.identity_holds and not levels.empty and float(levels["penalty"].min()) > 0:
        notes.append(
            "No search trial reproduced all three stylised facts: the lowest penalty "
            f"reached was {float(levels['penalty'].min()):g}, so every candidate's score "
            "includes a floor that no parameter setting in the search removed."
        )
    notes.append(
        "A study is a snapshot of a search against one version of the simulator; read "
        "its creation date against the model's history before quoting it."
    )
    return notes
