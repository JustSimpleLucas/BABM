"""Minimum-distance calibration score for simulated return series."""

from __future__ import annotations

import numpy as np
import pandas as pd

from abm_analysis.comparisons import compare_return_series
from abm_analysis.diagnostics import diagnose_return_series

from .constants import FAILED_TRIAL_SCORE
from .models import CalibrationScore, ScoreWeights

def score_return_match(
    simulation_returns: pd.Series,
    benchmark_returns: dict[str, pd.Series],
    *,
    diagnostics: dict[str, object] | None = None,
    weights: ScoreWeights = ScoreWeights(),
) -> CalibrationScore:
    """Score one simulated return series against empirical benchmarks.

    The objective is a transparent weighted distance rather than a binary pass
    condition. This reduces the risk of overfitting to one diagnostic while
    still penalising failures on the major stylised facts.
    """

    if not benchmark_returns:
        raise ValueError("At least one empirical benchmark series is required for calibration.")

    finite_simulation = _finite_series(simulation_returns)
    if len(finite_simulation) == 0:
        return CalibrationScore(
            score=FAILED_TRIAL_SCORE,
            components={"market_distance": FAILED_TRIAL_SCORE},
            benchmark_scores=[],
            diagnostics=diagnostics or {},
        )

    diagnostics = diagnostics or diagnose_return_series(
        "simulation",
        finite_simulation,
        phase="simulation",
    )
    benchmark_score_rows: list[dict[str, float | str]] = []
    market_scores: list[float] = []
    component_names = [
        "ks_statistic",
        "normalised_wasserstein",
        "tail_quantile_error",
        "acf_raw_rmse",
        "acf_absolute_rmse",
        "acf_squared_rmse",
    ]

    for benchmark_id, benchmark_series in sorted(benchmark_returns.items()):
        finite_benchmark = _finite_series(benchmark_series)
        comparison = compare_return_series(
            "simulation",
            benchmark_id,
            finite_simulation,
            finite_benchmark,
        )
        if comparison.get("status") != "completed":
            row_score = FAILED_TRIAL_SCORE
            row = {"benchmark_id": benchmark_id, "score": row_score, "status": "failed"}
            benchmark_score_rows.append(row)
            market_scores.append(row_score)
            continue

        scale = _return_scale(finite_benchmark)
        tail_error = _mean_finite(
            [
                _normalised_abs(comparison.get(f"q{level}_absolute_error"), scale)
                for level in ("01", "05", "95", "99")
            ],
            fallback=1.0,
        )
        normalised_wasserstein = _normalised_abs(
            comparison.get("wasserstein_distance"),
            scale,
        )
        row_components = {
            "ks_statistic": _finite_or_penalty(comparison.get("ks_statistic")),
            "normalised_wasserstein": normalised_wasserstein,
            "tail_quantile_error": tail_error,
            "acf_raw_rmse": _finite_or_penalty(comparison.get("acf_raw_rmse")),
            "acf_absolute_rmse": _finite_or_penalty(comparison.get("acf_absolute_rmse")),
            "acf_squared_rmse": _finite_or_penalty(comparison.get("acf_squared_rmse")),
        }
        row_score = (
            weights.ks_statistic * row_components["ks_statistic"]
            + weights.normalised_wasserstein * row_components["normalised_wasserstein"]
            + weights.tail_quantile_error * row_components["tail_quantile_error"]
            + weights.acf_raw_rmse * row_components["acf_raw_rmse"]
            + weights.acf_absolute_rmse * row_components["acf_absolute_rmse"]
            + weights.acf_squared_rmse * row_components["acf_squared_rmse"]
        )
        benchmark_score_rows.append(
            {
                "benchmark_id": benchmark_id,
                "score": float(row_score),
                "status": "completed",
                **row_components,
            }
        )
        market_scores.append(float(row_score))

    market_distance = _mean_finite(market_scores, fallback=FAILED_TRIAL_SCORE)
    stylised_penalty = _stylised_fact_penalty(diagnostics, weights)
    components = {
        "market_distance": market_distance,
        "stylised_penalty": stylised_penalty,
        "benchmark_count": float(len(benchmark_score_rows)),
    }
    for component_name in component_names:
        components[component_name] = _mean_finite(
            [
                float(row[component_name])
                for row in benchmark_score_rows
                if component_name in row
            ],
            fallback=1.0,
        )
    return CalibrationScore(
        score=float(market_distance + stylised_penalty),
        components=components,
        benchmark_scores=benchmark_score_rows,
        diagnostics=diagnostics,
    )

def score_multi_asset_return_match(
    returns_by_asset: dict[str, pd.Series],
    benchmark_returns: dict[str, pd.Series],
    *,
    diagnostics_by_asset: dict[str, dict[str, object]] | None = None,
    weights: ScoreWeights = ScoreWeights(),
) -> CalibrationScore:
    """Score every traded asset against the benchmarks and average the results.

    Each market is scored independently and the objective is the mean of those
    scores, so a candidate parameterisation has to reproduce the empirical
    stylised facts in *both* markets to rank well. Averaging rather than taking
    the worst asset keeps the objective smooth enough for the TPE sampler to
    follow, while still making a failing market cost roughly half the score.

    Component values are averaged the same way, and per-asset scores are
    recorded as ``asset_score.<name>`` so a study can see which market drove a
    candidate's rank. Assets with no usable returns take the failed-trial score
    rather than being dropped, so a candidate cannot improve its rank by
    killing one of its markets.

    :param returns_by_asset: Finite log returns keyed by asset name.
    :param diagnostics_by_asset: Pre-computed diagnostics keyed by asset name;
        missing entries are computed from the returns.
    """

    if not returns_by_asset:
        raise ValueError("At least one asset return series is required for calibration.")

    diagnostics_by_asset = diagnostics_by_asset or {}
    asset_scores: dict[str, CalibrationScore] = {}
    for asset, returns in returns_by_asset.items():
        asset_scores[asset] = score_return_match(
            returns,
            benchmark_returns,
            diagnostics=diagnostics_by_asset.get(asset),
            weights=weights,
        )

    component_names = sorted(
        {name for score in asset_scores.values() for name in score.components}
    )
    components: dict[str, float] = {}
    for component_name in component_names:
        components[component_name] = _mean_finite(
            [
                float(score.components[component_name])
                for score in asset_scores.values()
                if component_name in score.components
            ],
            fallback=FAILED_TRIAL_SCORE,
        )
    for asset, score in asset_scores.items():
        components[f"asset_score.{asset}"] = float(score.score)
    components["asset_count"] = float(len(asset_scores))

    overall = _mean_finite(
        [float(score.score) for score in asset_scores.values()],
        fallback=FAILED_TRIAL_SCORE,
    )
    benchmark_scores = [
        {"asset": asset, **row}
        for asset, score in asset_scores.items()
        for row in score.benchmark_scores
    ]
    diagnostics = {
        "per_asset": {asset: score.diagnostics for asset, score in asset_scores.items()},
    }
    return CalibrationScore(
        score=float(overall),
        components=components,
        benchmark_scores=benchmark_scores,
        diagnostics=diagnostics,
    )

def _finite_series(series: pd.Series) -> pd.Series:
    """Coerce a series to numeric and drop non-finite values, resetting the index."""

    values = pd.to_numeric(series, errors="coerce")
    return values[np.isfinite(values)].reset_index(drop=True)

def _return_scale(values: pd.Series) -> float:
    """Compute the sample standard deviation used to normalise distance metrics.

    Falls back to 1.0 when there are too few observations or the series is
    nearly constant, so downstream normalisation never divides by a
    near-zero scale.
    """

    scale = float(np.std(values.to_numpy(dtype=float), ddof=1)) if len(values) > 1 else np.nan
    if not np.isfinite(scale) or scale <= 1.0e-12:
        return 1.0
    return scale

def _normalised_abs(value: object, scale: float) -> float:
    """Return the absolute value of a metric normalised by scale, guarding against division by ~zero."""

    return _finite_or_penalty(value) / max(scale, 1.0e-12)

def _finite_or_penalty(value: object, penalty: float = 1.0) -> float:
    """Coerce a value to a finite float, substituting penalty when it is missing, non-numeric, or non-finite."""

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return penalty
    return numeric if np.isfinite(numeric) else penalty

def _mean_finite(values: list[float], *, fallback: float) -> float:
    """Return the mean of the finite values in the list, or fallback when none are finite."""

    finite_values = [float(value) for value in values if np.isfinite(value)]
    return float(np.mean(finite_values)) if finite_values else fallback

def _stylised_fact_penalty(diagnostics: dict[str, object], weights: ScoreWeights) -> float:
    """Score how well the diagnostics match the expected stylised facts of real markets.

    Adds a fixed weight penalty for each of the three stylised-fact checks
    (absence of raw-return autocorrelation, fat tails, volatility clustering)
    whose diagnostic conclusion does not match the expected pattern, so the
    objective rewards candidates that reproduce known market regularities and
    not just benchmark-distance alone.
    """

    penalty = 0.0
    autocorrelation = str(diagnostics.get("autocorrelation_conclusion", ""))
    fat_tails = str(diagnostics.get("fat_tail_conclusion", ""))
    volatility = str(diagnostics.get("volatility_clustering_conclusion", ""))

    if not autocorrelation.startswith("Consistent with absence of autocorrelation"):
        penalty += weights.autocorrelation_penalty
    if not fat_tails.startswith("Consistent with fat-tailed returns"):
        penalty += weights.fat_tail_penalty
    if not (
        volatility.startswith("Consistent with volatility clustering")
        or volatility.startswith("ARCH evidence supports volatility clustering")
    ):
        penalty += weights.volatility_clustering_penalty
    return float(penalty)
