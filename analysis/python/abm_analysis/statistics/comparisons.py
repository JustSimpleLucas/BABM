"""Simulation-to-benchmark return distribution comparisons."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import acf


QUANTILE_LEVELS = (0.01, 0.05, 0.50, 0.95, 0.99)
ACF_DISTANCE_LAGS = 30


def build_simulation_benchmark_comparison(
    simulation_returns: dict[str, pd.Series],
    benchmark_returns: dict[str, pd.Series],
    *,
    run_labels: dict[str, str] | None = None,
    max_acf_lag: int = ACF_DISTANCE_LAGS,
) -> pd.DataFrame:
    """Compare every simulated return series with every empirical benchmark.

    The table intentionally combines distributional, quantile, and dependence
    diagnostics because stylised facts are not one-dimensional. A simulation can
    match tail thickness while missing volatility persistence, or vice versa.
    """

    rows: list[dict[str, object]] = []
    for run_id, sim_series in sorted(simulation_returns.items()):
        for benchmark_id, benchmark_series in sorted(benchmark_returns.items()):
            row = compare_return_series(
                run_id,
                benchmark_id,
                sim_series,
                benchmark_series,
                max_acf_lag=max_acf_lag,
            )
            if run_labels is not None:
                row["simulation_label"] = run_labels.get(str(run_id), str(run_id))
            rows.append(row)
    return pd.DataFrame(rows)


def compare_return_series(
    run_id: str,
    benchmark_id: str,
    simulation_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    max_acf_lag: int = ACF_DISTANCE_LAGS,
) -> dict[str, object]:
    """Compare one simulated run with one empirical market benchmark."""

    sim_values = _finite_values(simulation_returns)
    benchmark_values = _finite_values(benchmark_returns)
    row: dict[str, object] = {
        "run_id": run_id,
        "benchmark_id": benchmark_id,
        "simulation_observation_count": int(len(sim_values)),
        "benchmark_observation_count": int(len(benchmark_values)),
        "status": "completed",
    }
    if len(sim_values) == 0 or len(benchmark_values) == 0:
        row["status"] = "insufficient_observations"
        return row

    ks_result = stats.ks_2samp(sim_values, benchmark_values, alternative="two-sided", method="auto")
    row.update(
        {
            "ks_statistic": float(ks_result.statistic),
            "ks_p_value": float(ks_result.pvalue),
            "wasserstein_distance": float(stats.wasserstein_distance(sim_values, benchmark_values)),
        }
    )
    row.update(_quantile_error_metrics(sim_values, benchmark_values))
    row.update(_acf_distance_metrics(sim_values, benchmark_values, max_acf_lag=max_acf_lag))
    return row


def _finite_values(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    return values[np.isfinite(values)]


def _quantile_error_metrics(
    simulation_values: np.ndarray,
    benchmark_values: np.ndarray,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for level in QUANTILE_LEVELS:
        label = f"q{int(level * 100):02d}"
        simulation_quantile = float(np.quantile(simulation_values, level))
        benchmark_quantile = float(np.quantile(benchmark_values, level))
        result[f"{label}_simulation"] = simulation_quantile
        result[f"{label}_benchmark"] = benchmark_quantile
        result[f"{label}_error"] = simulation_quantile - benchmark_quantile
        result[f"{label}_absolute_error"] = abs(simulation_quantile - benchmark_quantile)
    return result


def _acf_distance_metrics(
    simulation_values: np.ndarray,
    benchmark_values: np.ndarray,
    *,
    max_acf_lag: int,
) -> dict[str, float]:
    transforms = {
        "raw": lambda values: values,
        "absolute": np.abs,
        "squared": lambda values: values**2,
    }
    result: dict[str, float] = {}
    for name, transform in transforms.items():
        sim_acf = _safe_acf(transform(simulation_values), max_acf_lag)
        benchmark_acf = _safe_acf(transform(benchmark_values), max_acf_lag)
        lag_count = min(len(sim_acf), len(benchmark_acf))
        if lag_count <= 1:
            result[f"acf_{name}_rmse"] = np.nan
            result[f"acf_{name}_mean_absolute_error"] = np.nan
            continue
        difference = sim_acf[1:lag_count] - benchmark_acf[1:lag_count]
        result[f"acf_{name}_rmse"] = float(np.sqrt(np.mean(difference**2)))
        result[f"acf_{name}_mean_absolute_error"] = float(np.mean(np.abs(difference)))
    return result


def _safe_acf(values: np.ndarray, max_lag: int) -> np.ndarray:
    finite_values = values[np.isfinite(values)]
    if len(finite_values) < 5 or np.std(finite_values) <= 0:
        return np.array([], dtype=float)
    lag_count = min(max_lag, max(1, len(finite_values) // 4))
    return acf(finite_values, nlags=lag_count, fft=True)
