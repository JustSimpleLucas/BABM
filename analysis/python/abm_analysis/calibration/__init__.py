"""Optuna-driven calibration for the behavioural-finance ABM.

The calibration layer treats the C++ executable as the reproducible simulator
and keeps search logic in Python. The model remains a transparent data-
generating process, while this package handles simulation-based minimum-distance
calibration against empirical return data.
"""

from __future__ import annotations

from .config import (
    default_calibration_output_dir,
    format_config_value,
    load_calibration_settings,
    load_search_space,
    parse_seed_list,
    patch_config_text,
    resolve_simulator_path,
    suggest_trial_parameters,
    warn_if_simulator_stale,
)
from .constants import CONFIG_KEY_PATTERN, FAILED_TRIAL_SCORE, RUN_CSV_ARTIFACT_FILENAMES
from .execution import _render_progress_chunk, run_candidate_worker_payload
from .models import (
    BudgetSettings,
    CalibrationOptions,
    CalibrationScore,
    CalibrationSettings,
    RankingSettings,
    ScoreWeights,
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
from .scoring import score_return_match
from .study import options_to_json, run_calibration

__all__ = [
    "CONFIG_KEY_PATTERN",
    "FAILED_TRIAL_SCORE",
    "RUN_CSV_ARTIFACT_FILENAMES",
    "BudgetSettings",
    "CalibrationOptions",
    "CalibrationScore",
    "CalibrationSettings",
    "CandidateRobustness",
    "RankingSettings",
    "ScoreWeights",
    "SimulationExecutionResult",
    "SimulatorRunner",
    "_render_progress_chunk",
    "default_calibration_output_dir",
    "evaluate_candidate_robustness",
    "filter_candidate_runs_index",
    "format_config_value",
    "load_calibration_settings",
    "load_search_space",
    "options_to_json",
    "parse_seed_list",
    "patch_config_text",
    "resolve_simulator_path",
    "robust_ranking_score",
    "run_calibration",
    "run_candidate_worker_payload",
    "score_return_match",
    "suggest_trial_parameters",
    "summarise_verdicts",
    "warn_if_simulator_stale",
]
