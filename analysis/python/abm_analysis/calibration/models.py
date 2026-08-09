"""Calibration option and result data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Callable

from abm_analysis.robustness_verdicts import VerdictThresholds

@dataclass
class CalibrationOptions:
    """Runtime options for one calibration study."""

    base_config: Path
    search_space: Path
    simulator: Path
    calibration_name: str
    trials: int
    seeds: tuple[int, ...]
    output_dir: Path | None = None
    benchmark_dir: Path | None = None
    benchmark_series: str | None = None
    holdout_benchmark_series: str | None = None
    top_candidates: int = 5
    score_threshold: float | None = None
    no_improvement_trials: int | None = None
    phase: str = "simulation"
    price_column: str = "market_price"
    timeout_seconds: int | None = None
    keep_run_csv: bool = False
    isolate_trials: bool = True
    show_simulation_progress: bool = True
    # Concurrent seed-level simulator runs within one trial; trials themselves
    # stay sequential so Optuna's sampler sees every completed result. 0 means
    # one job per CPU core (capped at the seed count), 1 is sequential.
    jobs: int = 0
    # Seeds used only for the top-candidate validation phase; ``None`` keeps
    # the legacy behaviour of validating on ``seeds``.
    validation_seeds: tuple[int, ...] | None = None
    # Optional calibration_settings.json overriding score weights, verdict
    # thresholds, ranking, and budget defaults.
    settings_path: Path | None = None
    # CLI convenience override applied on top of the settings file.
    robustness_penalty_weight: float | None = None
    # Seeds each search trial is scored over; ``None`` keeps the legacy
    # single-seed search (first entry of ``seeds``).
    search_seeds: tuple[int, ...] | None = None
    # How per-seed search scores combine into one Optuna objective value.
    # ``mean`` lets one crashed seed dominate (rejecting fragile candidates);
    # ``median`` tolerates one bad seed but can mask crash-prone regions.
    search_seed_aggregate: str = "mean"
    # Deterministic Optuna TPE sampler seed; ``None`` restores the
    # nondeterministic legacy sampler.
    sampler_seed: int | None = 55
    # Abort up front when the validation seed count cannot support
    # robustness verdicts instead of degrading to the fit-only ranking.
    require_robustness_verdicts: bool = False

@dataclass
class CalibrationScore:
    """Lower-is-better calibration score with transparent components."""

    score: float
    components: dict[str, float]
    benchmark_scores: list[dict[str, float | str]]
    diagnostics: dict[str, object]

@dataclass
class ScoreWeights:
    """Weights used in the minimum-distance calibration objective."""

    ks_statistic: float = 1.0
    normalised_wasserstein: float = 1.0
    tail_quantile_error: float = 1.0
    acf_raw_rmse: float = 0.50
    acf_absolute_rmse: float = 1.0
    acf_squared_rmse: float = 1.0
    autocorrelation_penalty: float = 0.75
    fat_tail_penalty: float = 0.75
    volatility_clustering_penalty: float = 0.75

@dataclass(frozen=True)
class RankingSettings:
    """How fit and robustness combine into the final candidate ranking.

    ``robust_ranking_score = ranking_score * (1 + weight * (1 - pass_rate))``
    with borderline verdicts credited at ``borderline_credit`` of a pass.
    """

    robustness_penalty_weight: float = 1.0
    borderline_credit: float = 0.5

@dataclass(frozen=True)
class BudgetSettings:
    """Guardrails on the total number of simulator runs per campaign."""

    max_total_runs: int = 300
    recommended_min_validation_seeds: int = 10

@dataclass(frozen=True)
class CalibrationSettings:
    """Configurable calibration behaviour loaded from calibration_settings.json."""

    score_weights: ScoreWeights = field(default_factory=ScoreWeights)
    verdict_thresholds: VerdictThresholds = field(default_factory=VerdictThresholds)
    ranking: RankingSettings = field(default_factory=RankingSettings)
    budget: BudgetSettings = field(default_factory=BudgetSettings)

@dataclass
class SimulationExecutionResult:
    """Outcome of one simulator execution."""

    status: str
    config_path: Path
    run_dir: Path | None
    return_code: int
    stdout: str
    stderr: str
    message: str = ""

SimulatorRunner = Callable[[list[str], Path | None, int | None], subprocess.CompletedProcess[str]]
