"""Per-candidate seed-robustness evaluation for calibration ranking.

The seed-robustness report evaluates one experiment directory at a time; a
calibration study instead validates several candidates inside one shared
``simulation_runs/validation`` directory. This module reuses the report's
computation layer verbatim on a per-candidate subset of that directory so the
final candidate ranking can combine benchmark fit with seed stability.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from abm_analysis.statistics.diagnostics import (
    build_asset_stylised_fact_diagnostics,
    build_pairwise_ks_table,
    build_return_series_by_run,
)
from abm_analysis.statistics.multi_asset import build_asset_return_series
from abm_analysis.statistics.robustness import build_seed_robustness_summary
from abm_analysis.statistics.robustness_tests import (
    build_adf_stationarity_table,
    build_cross_seed_distribution_tests,
    summarise_adf_rejections,
    summarise_pairwise_ks,
)
from abm_analysis.statistics.robustness_verdicts import VerdictThresholds, build_robustness_verdicts
from abm_analysis.statistics.seed_convergence import build_seed_convergence_table


@dataclass
class CandidateRobustness:
    """Cross-seed robustness evidence for one calibration candidate."""

    verdicts: pd.DataFrame
    pass_rate: float
    pass_count: int
    borderline_count: int
    fail_count: int
    not_available_count: int
    seed_count: int


def filter_candidate_runs_index(
    validation_index: pd.DataFrame,
    run_dirs: list[Path],
) -> pd.DataFrame:
    """Select the index rows belonging to one candidate's validation runs.

    Filtering on ``run_directory`` (the archive folder name) rather than
    ``run_id`` keeps the subset correct when a summary CSV substitutes its own
    run identifier, and shields the ranking from stale archives left behind by
    a previously interrupted calibration in the same output directory.
    """

    if validation_index.empty or "run_directory" not in validation_index.columns:
        return validation_index.iloc[0:0]
    names = {run_dir.name for run_dir in run_dirs}
    subset = validation_index[validation_index["run_directory"].astype(str).isin(names)]
    return subset.reset_index(drop=True)


def evaluate_candidate_robustness(
    run_dirs: list[Path],
    candidate_index: pd.DataFrame,
    *,
    phase: str,
    price_column: str,
    thresholds: VerdictThresholds | None = None,
    borderline_credit: float = 0.5,
) -> CandidateRobustness:
    """Compute seed-robustness verdicts for one candidate's validation runs.

    Mirrors the computation layer of ``build_seed_robustness_report`` without
    the figures and HTML. Recomputing the diagnostics from the archived runs
    keeps a single tested code path; the cost is seconds per run against
    minutes for the simulations themselves.
    """

    if not run_dirs or candidate_index.empty:
        return summarise_verdicts(
            pd.DataFrame(),
            seed_count=0,
            borderline_credit=borderline_credit,
        )

    diagnostics = build_asset_stylised_fact_diagnostics(
        run_dirs,
        phase=phase,
        price_column=price_column,
    )
    seed_count = _distinct_seed_count(candidate_index)
    assets = _assets_in_diagnostics(diagnostics)

    # Each market is evaluated as its own seed-robustness problem and the
    # verdicts are pooled. A candidate that is stable in one market and erratic
    # in the other therefore ranks below one that is stable in both, which is
    # the same standard the fit score applies.
    verdict_frames: list[pd.DataFrame] = []
    for asset in assets:
        asset_diagnostics = _diagnostics_for_asset(diagnostics, asset)
        return_series_by_run = _return_series_for_asset(
            run_dirs,
            asset,
            phase=phase,
            price_column=price_column,
        )
        ks_summary = summarise_pairwise_ks(build_pairwise_ks_table(return_series_by_run))
        distribution_tests = build_cross_seed_distribution_tests(return_series_by_run)
        adf_summary = summarise_adf_rejections(
            build_adf_stationarity_table(return_series_by_run, _seed_by_run(candidate_index))
        )
        asset_verdicts = build_robustness_verdicts(
            build_seed_robustness_summary(candidate_index, asset_diagnostics),
            distribution_tests,
            ks_summary,
            adf_summary,
            build_seed_convergence_table(candidate_index, asset_diagnostics),
            seed_count=seed_count,
            thresholds=thresholds,
        )
        if asset_verdicts.empty:
            continue
        if asset:
            asset_verdicts = asset_verdicts.copy()
            asset_verdicts.insert(0, "asset", asset)
        verdict_frames.append(asset_verdicts)

    verdicts = (
        pd.concat(verdict_frames, ignore_index=True) if verdict_frames else pd.DataFrame()
    )
    return summarise_verdicts(
        verdicts,
        seed_count=seed_count,
        borderline_credit=borderline_credit,
    )


def _assets_in_diagnostics(diagnostics: pd.DataFrame) -> list[str]:
    """Return the assets present in a diagnostics frame, in first-seen order.

    Yields ``[""]`` for archives with no per-asset artefact, which selects the
    single-asset path and keeps pre-existing calibration studies unchanged.
    """

    if diagnostics.empty or "asset" not in diagnostics.columns:
        return [""]
    names = [str(value or "") for value in diagnostics["asset"].tolist()]
    ordered = list(dict.fromkeys(name for name in names if name))
    return ordered or [""]


def _diagnostics_for_asset(diagnostics: pd.DataFrame, asset: str) -> pd.DataFrame:
    if not asset or "asset" not in diagnostics.columns:
        return diagnostics
    subset = diagnostics[diagnostics["asset"].astype(str) == asset]
    return subset.reset_index(drop=True)


def _return_series_for_asset(
    run_dirs: list[Path],
    asset: str,
    *,
    phase: str,
    price_column: str,
) -> dict[str, pd.Series]:
    """Collect one asset's return series across runs, keyed by run id.

    Keying by run id rather than by a composite (run, asset) id is deliberate:
    the cross-seed tests join these series against the candidate index's seeds,
    and one asset at a time is exactly one series per seed.
    """

    if not asset:
        return build_return_series_by_run(run_dirs, phase=phase, price_column=price_column)

    series: dict[str, pd.Series] = {}
    for run_dir in run_dirs:
        returns_by_asset = build_asset_return_series(run_dir, phase=phase)
        if asset in returns_by_asset:
            series[run_dir.name] = returns_by_asset[asset]
    return series


def summarise_verdicts(
    verdicts: pd.DataFrame,
    *,
    seed_count: int,
    borderline_credit: float,
) -> CandidateRobustness:
    """Reduce a verdict table to the counts and pass rate used for ranking.

    Borderline verdicts earn partial credit: the verdict layer frames them as
    "report with caution" rather than failure, and zero credit would
    systematically punish the fat-tailed regimes calibration is trying to
    find. ``pass_rate`` is NaN when no criterion could be evaluated.
    """

    if verdicts.empty or "verdict" not in verdicts.columns:
        counts = pd.Series(dtype=int)
    else:
        counts = verdicts["verdict"].value_counts()
    pass_count = int(counts.get("pass", 0))
    borderline_count = int(counts.get("borderline", 0))
    fail_count = int(counts.get("fail", 0))
    not_available_count = int(counts.get("not_available", 0))
    evaluated = pass_count + borderline_count + fail_count
    pass_rate = (
        float("nan")
        if evaluated == 0
        else (pass_count + borderline_credit * borderline_count) / evaluated
    )
    return CandidateRobustness(
        verdicts=verdicts,
        pass_rate=pass_rate,
        pass_count=pass_count,
        borderline_count=borderline_count,
        fail_count=fail_count,
        not_available_count=not_available_count,
        seed_count=seed_count,
    )


def robust_ranking_score(
    ranking_score: float,
    pass_rate: float,
    *,
    penalty_weight: float,
) -> float:
    """Scale the fit-based ranking score by the robustness shortfall.

    ``score * (1 + w * (1 - pass_rate))`` is scale-free in the fit score and
    monotone in both inputs: with ``w = 1`` a candidate with no demonstrated
    robustness must fit twice as well as a fully robust one to win. A NaN
    pass rate is treated as zero (inability to demonstrate robustness).
    """

    effective_pass_rate = 0.0 if not np.isfinite(pass_rate) else float(pass_rate)
    effective_pass_rate = min(max(effective_pass_rate, 0.0), 1.0)
    return float(ranking_score) * (1.0 + penalty_weight * (1.0 - effective_pass_rate))


def _seed_by_run(runs_index: pd.DataFrame) -> dict[str, object]:
    if runs_index.empty or not {"run_id", "seed"}.issubset(runs_index.columns):
        return {}
    return dict(zip(runs_index["run_id"].astype(str), runs_index["seed"], strict=True))


def _distinct_seed_count(runs_index: pd.DataFrame) -> int:
    if runs_index.empty:
        return 0
    if "seed" not in runs_index.columns:
        return int(len(runs_index))
    return int(pd.to_numeric(runs_index["seed"], errors="coerce").nunique())
