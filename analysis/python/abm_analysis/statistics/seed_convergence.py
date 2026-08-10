"""Seed-count convergence analysis for replicated ABM experiments.

Simulation studies must justify their number of replications. Following the
sequential-precision argument in Law (2015, "Simulation Modeling and
Analysis", ch. 9), this module tracks how the ensemble mean and its 95%
confidence-interval half-width evolve as seeds accumulate. When the relative
half-width stabilises below the reporting threshold, additional seeds no
longer change the headline metrics and the replication count is defensible.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from abm_analysis.statistics.robustness import merge_run_and_diagnostic_metrics


# Headline metrics whose ensemble precision justifies the replication count.
# They mirror the report's summary cards: location, dispersion, tail
# thickness, and worst-case loss of the simulated market.
CONVERGENCE_METRICS = (
    "mean_log_return",
    "log_return_std_dev",
    "excess_kurtosis",
    "max_drawdown",
)

# Two-sided 95% normal critical value, matching the confidence intervals in
# ``abm_analysis.statistics.robustness._aggregate_metric`` so both tables agree.
NORMAL_95_CRITICAL_VALUE = 1.96

# Relative half-widths are undefined when the running mean is numerically
# zero; this guard mirrors the coefficient-of-variation guard in
# ``abm_analysis.statistics.robustness``.
NEAR_ZERO_MEAN_GUARD = 1.0e-12


def build_seed_convergence_table(
    runs_index: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    metrics: tuple[str, ...] = CONVERGENCE_METRICS,
) -> pd.DataFrame:
    """Compute running ensemble statistics as seeds accumulate.

    Runs are ordered by ascending seed (ties broken by run id) so that the
    convergence path is reproducible: re-running the analysis on the same
    experiment always accumulates seeds in the same order, regardless of the
    order in which the simulator produced the run folders.

    Returns a long-format table with one row per (metric, seed_count):
    ``metric, seed_count, newest_seed, running_mean, running_std,
    ci95_half_width, relative_ci95_half_width``. The standard deviation uses
    ``ddof=1`` and is undefined (NaN) at ``seed_count=1``.
    """

    if runs_index.empty or "run_id" not in runs_index.columns:
        return pd.DataFrame()
    if "seed" not in runs_index.columns:
        return pd.DataFrame()

    merged = merge_run_and_diagnostic_metrics(runs_index, diagnostics)
    merged = merged.copy()
    merged["seed"] = pd.to_numeric(merged["seed"], errors="coerce")
    merged = merged[merged["seed"].notna()]
    if merged.empty:
        return pd.DataFrame()
    merged = merged.sort_values(["seed", "run_id"]).reset_index(drop=True)

    rows: list[dict[str, object]] = []
    for metric in metrics:
        if metric not in merged.columns:
            continue
        values = pd.to_numeric(merged[metric], errors="coerce")
        observed = merged[values.notna()]
        observed_values = values.dropna().to_numpy(dtype=float)
        for count in range(1, len(observed_values) + 1):
            window = observed_values[:count]
            running_mean = float(np.mean(window))
            running_std = float(np.std(window, ddof=1)) if count > 1 else np.nan
            half_width = (
                NORMAL_95_CRITICAL_VALUE * running_std / math.sqrt(count)
                if count > 1
                else np.nan
            )
            relative_half_width = (
                half_width / abs(running_mean)
                if count > 1 and abs(running_mean) > NEAR_ZERO_MEAN_GUARD
                else np.nan
            )
            rows.append(
                {
                    "metric": metric,
                    "seed_count": count,
                    "newest_seed": int(observed["seed"].iloc[count - 1]),
                    "running_mean": running_mean,
                    "running_std": running_std,
                    "ci95_half_width": half_width,
                    "relative_ci95_half_width": relative_half_width,
                }
            )
    return pd.DataFrame(rows)


def final_relative_ci_half_widths(convergence_table: pd.DataFrame) -> dict[str, float]:
    """Extract each metric's relative CI half-width at the full seed count."""

    if convergence_table.empty or "metric" not in convergence_table.columns:
        return {}
    result: dict[str, float] = {}
    for metric, group in convergence_table.groupby("metric"):
        final_row = group.sort_values("seed_count").iloc[-1]
        result[str(metric)] = float(final_row["relative_ci95_half_width"])
    return result
