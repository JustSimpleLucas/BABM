"""Cross-seed inferential tests for seed-robustness analysis.

The seed-robustness report asks one central question: do replicated runs that
differ only in the random seed produce statistically indistinguishable market
behaviour? The tests in this module address that question from three angles:

- distribution equality across seeds (Anderson-Darling k-sample,
  Kruskal-Wallis for location, Brown-Forsythe for dispersion),
- a summary of the pairwise two-sample Kolmogorov-Smirnov table already
  computed by :mod:`abm_analysis.statistics.diagnostics`,
- per-seed stationarity of log returns (Augmented Dickey-Fuller).

All tests are diagnostic evidence, not proofs: under the null hypothesis that
every seed draws from the same data-generating process, occasional rejections
at the 5% level are expected, and the pairwise K-S statistics share samples so
the tests are not independent. The report prose carries these caveats.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import adfuller

from abm_analysis.statistics.diagnostics import SIGNIFICANCE_LEVEL


# Minimum finite log-return observations per series before a test is run.
# This matches the floor used by ``diagnose_return_series`` so that the same
# runs are either included in or excluded from every statistical layer.
MINIMUM_OBSERVATIONS_PER_SERIES = 50

# SciPy caps the Anderson-Darling k-sample p-value to this interval because
# the reference tables in Scholz & Stephens (1987) only cover interior
# significance levels. Capped values must be displayed as bounds, not as
# exact probabilities.
ANDERSON_DARLING_P_VALUE_FLOOR = 0.001
ANDERSON_DARLING_P_VALUE_CAP = 0.25


def summarise_pairwise_ks(
    pairwise_ks: pd.DataFrame,
    *,
    significance_level: float = SIGNIFICANCE_LEVEL,
) -> dict[str, float]:
    """Summarise the pairwise K-S table into cross-seed stability metrics.

    Under the null hypothesis that all seeds share one return distribution,
    roughly ``1 - significance_level`` of the pairwise tests should fail to
    reject. The ``insignificant_share`` therefore acts as a distributional
    stability score across seeds. The pairs are not independent (each run
    appears in many pairs), so the share is a descriptive summary rather than
    an exact test.
    """

    summary: dict[str, float] = {
        "pair_count": 0,
        "mean_ks_statistic": np.nan,
        "median_ks_statistic": np.nan,
        "insignificant_share": np.nan,
    }
    if pairwise_ks.empty or "ks_statistic" not in pairwise_ks.columns:
        return summary

    statistics = pd.to_numeric(pairwise_ks["ks_statistic"], errors="coerce")
    p_values = pd.to_numeric(pairwise_ks.get("ks_p_value"), errors="coerce")
    finite_mask = statistics.notna() & p_values.notna()
    if not finite_mask.any():
        return summary

    statistics = statistics[finite_mask]
    p_values = p_values[finite_mask]
    summary["pair_count"] = int(len(statistics))
    summary["mean_ks_statistic"] = float(statistics.mean())
    summary["median_ks_statistic"] = float(statistics.median())
    summary["insignificant_share"] = float((p_values > significance_level).mean())
    return summary


def build_cross_seed_distribution_tests(
    return_series_by_run: dict[str, pd.Series],
    *,
    significance_level: float = SIGNIFICANCE_LEVEL,
) -> pd.DataFrame:
    """Test whether log-return distributions are equal across seeds.

    Three complementary k-sample tests are reported so a rejection can be
    attributed to a specific distributional feature:

    - Anderson-Darling k-sample: sensitive to any distributional difference,
      with extra weight in the tails (Scholz & Stephens, 1987).
    - Kruskal-Wallis: rank-based test of equal location, robust to the
      heavy tails expected in simulated returns.
    - Brown-Forsythe (Levene with median centring): equality of dispersion,
      chosen over mean-centred Levene because return distributions are
      leptokurtic (Brown & Forsythe, 1974).

    Returns an empty frame when fewer than two usable series exist; a run is
    usable when it has at least ``MINIMUM_OBSERVATIONS_PER_SERIES`` finite
    log returns.
    """

    samples = _finite_samples(return_series_by_run)
    usable = {
        run_id: values
        for run_id, values in samples.items()
        if len(values) >= MINIMUM_OBSERVATIONS_PER_SERIES
    }
    if len(usable) < 2:
        return pd.DataFrame()

    ordered_samples = [usable[run_id] for run_id in sorted(usable)]
    shared_fields = {
        "sample_count": len(ordered_samples),
        "min_observations": int(min(len(values) for values in ordered_samples)),
        "max_observations": int(max(len(values) for values in ordered_samples)),
        "significance_level": significance_level,
    }

    rows = [
        _anderson_darling_row(ordered_samples, shared_fields, significance_level),
        _kruskal_wallis_row(ordered_samples, shared_fields, significance_level),
        _brown_forsythe_row(ordered_samples, shared_fields, significance_level),
    ]
    return pd.DataFrame(rows)


def build_adf_stationarity_table(
    return_series_by_run: dict[str, pd.Series],
    seed_by_run: dict[str, object] | None = None,
    *,
    regression: str = "c",
    autolag: str = "AIC",
    significance_level: float = SIGNIFICANCE_LEVEL,
) -> pd.DataFrame:
    """Run the Augmented Dickey-Fuller test on each seed's log returns.

    Stationary log returns are a prerequisite for the moment-based robustness
    metrics (means, variances, kurtosis) to be well defined, so the report
    verifies stationarity seed by seed. The null hypothesis is a unit root
    (Dickey & Fuller, 1979); rejecting it for (nearly) every seed supports
    treating the per-seed metrics as draws from one stationary process.
    """

    rows: list[dict[str, object]] = []
    for run_id in sorted(return_series_by_run):
        values = _finite_values(return_series_by_run[run_id])
        row: dict[str, object] = {
            "run_id": run_id,
            "seed": (seed_by_run or {}).get(run_id, pd.NA),
            "n_observations": int(len(values)),
            "status": "completed",
        }
        if len(values) < MINIMUM_OBSERVATIONS_PER_SERIES:
            row.update(
                {
                    "adf_statistic": np.nan,
                    "adf_p_value": np.nan,
                    "used_lag": np.nan,
                    "critical_value_5pct": np.nan,
                    "rejects_unit_root": pd.NA,
                    "status": "insufficient_observations",
                }
            )
            rows.append(row)
            continue
        if np.std(values) <= 0:
            row.update(
                {
                    "adf_statistic": np.nan,
                    "adf_p_value": np.nan,
                    "used_lag": np.nan,
                    "critical_value_5pct": np.nan,
                    "rejects_unit_root": pd.NA,
                    "status": "degenerate_series",
                }
            )
            rows.append(row)
            continue

        statistic, p_value, used_lag, _, critical_values, _ = adfuller(
            values,
            regression=regression,
            autolag=autolag,
        )
        row.update(
            {
                "adf_statistic": float(statistic),
                "adf_p_value": float(p_value),
                "used_lag": int(used_lag),
                "critical_value_5pct": float(critical_values.get("5%", np.nan)),
                "rejects_unit_root": bool(float(p_value) < significance_level),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def summarise_adf_rejections(
    adf_table: pd.DataFrame,
    *,
    significance_level: float = SIGNIFICANCE_LEVEL,
) -> dict[str, float]:
    """Summarise per-seed ADF outcomes into one rejection rate."""

    summary: dict[str, float] = {
        "tested_seed_count": 0,
        "rejection_rate": np.nan,
        "significance_level": significance_level,
    }
    if adf_table.empty or "adf_p_value" not in adf_table.columns:
        return summary

    completed = adf_table[adf_table.get("status", "") == "completed"]
    p_values = pd.to_numeric(completed["adf_p_value"], errors="coerce").dropna()
    if p_values.empty:
        return summary

    summary["tested_seed_count"] = int(len(p_values))
    summary["rejection_rate"] = float((p_values < significance_level).mean())
    return summary


def _anderson_darling_row(
    samples: list[np.ndarray],
    shared_fields: dict[str, object],
    significance_level: float,
) -> dict[str, object]:
    row: dict[str, object] = {
        "test_name": "anderson_darling_ksample",
        "null_hypothesis": "All seeds draw log returns from the same distribution.",
        **shared_fields,
    }
    try:
        with warnings.catch_warnings():
            # SciPy warns when it caps the p-value to its tabulated range;
            # the capping is detected numerically below instead.
            warnings.simplefilter("ignore")
            result = stats.anderson_ksamp(samples)
    except ValueError as exc:
        return _degenerate_test_row(row, exc)

    p_value = float(result.significance_level)
    is_capped = (
        p_value <= ANDERSON_DARLING_P_VALUE_FLOOR
        or p_value >= ANDERSON_DARLING_P_VALUE_CAP
    )
    row.update(
        {
            "statistic": float(result.statistic),
            "p_value": p_value,
            "p_value_display": _format_capped_p_value(p_value, is_capped),
            "p_value_is_capped": is_capped,
            "rejects_null": bool(p_value < significance_level),
            "status": "completed",
        }
    )
    return row


def _kruskal_wallis_row(
    samples: list[np.ndarray],
    shared_fields: dict[str, object],
    significance_level: float,
) -> dict[str, object]:
    row: dict[str, object] = {
        "test_name": "kruskal_wallis",
        "null_hypothesis": "All seeds share the same log-return location (median).",
        **shared_fields,
    }
    try:
        with warnings.catch_warnings():
            # Constant samples make SciPy divide by zero before it returns a
            # NaN statistic; degeneracy is detected from that NaN instead.
            warnings.simplefilter("ignore", RuntimeWarning)
            statistic, p_value = stats.kruskal(*samples)
    except ValueError as exc:
        return _degenerate_test_row(row, exc)
    return _completed_test_row(row, float(statistic), float(p_value), significance_level)


def _brown_forsythe_row(
    samples: list[np.ndarray],
    shared_fields: dict[str, object],
    significance_level: float,
) -> dict[str, object]:
    row: dict[str, object] = {
        "test_name": "levene_brown_forsythe",
        "null_hypothesis": "All seeds share the same log-return dispersion (variance).",
        **shared_fields,
    }
    try:
        with warnings.catch_warnings():
            # Same NaN-based degeneracy detection as the Kruskal-Wallis row.
            warnings.simplefilter("ignore", RuntimeWarning)
            statistic, p_value = stats.levene(*samples, center="median")
    except ValueError as exc:
        return _degenerate_test_row(row, exc)
    return _completed_test_row(row, float(statistic), float(p_value), significance_level)


def _completed_test_row(
    row: dict[str, object],
    statistic: float,
    p_value: float,
    significance_level: float,
) -> dict[str, object]:
    # SciPy signals some degenerate inputs (for example constant samples in
    # Levene's test) with NaN statistics instead of raising, so the same
    # degenerate status must be applied here as in the except branches.
    if not (np.isfinite(statistic) and np.isfinite(p_value)):
        return _degenerate_test_row(
            row,
            ValueError("Test statistic is undefined for the provided samples."),
        )
    row.update(
        {
            "statistic": statistic,
            "p_value": p_value,
            "p_value_display": _format_p_value(p_value),
            "p_value_is_capped": False,
            "rejects_null": bool(p_value < significance_level),
            "status": "completed",
        }
    )
    return row


def _degenerate_test_row(row: dict[str, object], exc: Exception) -> dict[str, object]:
    # SciPy raises ValueError when samples are constant or otherwise leave the
    # test statistic undefined; this is a data property, not an analysis bug.
    row.update(
        {
            "statistic": np.nan,
            "p_value": np.nan,
            "p_value_display": "not available",
            "p_value_is_capped": False,
            "rejects_null": pd.NA,
            "status": "degenerate_samples",
            "status_message": str(exc),
        }
    )
    return row


def _format_capped_p_value(p_value: float, is_capped: bool) -> str:
    if not is_capped:
        return _format_p_value(p_value)
    if p_value <= ANDERSON_DARLING_P_VALUE_FLOOR:
        return f"<= {ANDERSON_DARLING_P_VALUE_FLOOR:g}"
    return f">= {ANDERSON_DARLING_P_VALUE_CAP:g}"


def _format_p_value(p_value: float) -> str:
    if not np.isfinite(p_value):
        return "not available"
    if p_value != 0 and abs(p_value) < 0.001:
        return f"{p_value:.3e}"
    return f"{p_value:.4f}"


def _finite_samples(return_series_by_run: dict[str, pd.Series]) -> dict[str, np.ndarray]:
    return {
        run_id: _finite_values(series)
        for run_id, series in return_series_by_run.items()
    }


def _finite_values(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    return values[np.isfinite(values)]
