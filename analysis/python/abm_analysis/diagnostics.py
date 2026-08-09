"""Stylised-fact diagnostics using established Python econometrics libraries."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from arch import arch_model
from arch.utility.exceptions import ConvergenceWarning
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
from statsmodels.stats.stattools import jarque_bera

from abm_analysis.data import prepare_return_series
from abm_analysis.multi_asset import (
    asset_series_id,
    build_asset_return_series,
    compute_asset_path_metrics,
    load_multi_asset_configuration,
)


SIGNIFICANCE_LEVEL = 0.05
LJUNG_BOX_LAGS = (10, 20, 30)
ARCH_LAGS = (10, 20)


def run_stylised_fact_diagnostics(
    run_dir: Path | str,
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
    significance_level: float = SIGNIFICANCE_LEVEL,
    ljung_box_lags: tuple[int, ...] = LJUNG_BOX_LAGS,
    arch_lags: tuple[int, ...] = ARCH_LAGS,
) -> dict[str, object]:
    """Compute thesis-oriented stylised-fact diagnostics for one run.

    The tests map directly onto standard empirical-finance stylised facts:
    weak raw-return autocorrelation (Ljung-Box), heavy-tailed returns
    (Jarque-Bera and kurtosis), and volatility clustering (Engle ARCH LM and
    Student-t GARCH(1,1)). These are diagnostic summaries, not causal claims.
    """

    run_path = Path(run_dir).expanduser().resolve()
    returns = prepare_return_series(run_path, phase=phase, price_column=price_column)
    return diagnose_return_series(
        run_path.name,
        returns,
        phase=phase,
        price_column=price_column,
    )


def diagnose_return_series(
    series_id: str,
    returns: pd.Series,
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
    significance_level: float = SIGNIFICANCE_LEVEL,
    ljung_box_lags: tuple[int, ...] = LJUNG_BOX_LAGS,
    arch_lags: tuple[int, ...] = ARCH_LAGS,
) -> dict[str, object]:
    """Compute stylised-fact diagnostics for an already prepared return series.

    This shared entry point lets simulated runs and empirical benchmark series
    pass through the same empirical-finance tests. Keeping the statistical
    treatment identical is important for thesis interpretation because any
    difference in conclusions then comes from the data-generating process, not
    from different diagnostic methods.
    """

    finite_returns = pd.to_numeric(returns, errors="coerce")
    finite_returns = finite_returns[np.isfinite(finite_returns)].reset_index(drop=True)
    result: dict[str, object] = {
        "run_id": series_id,
        "phase": phase,
        "price_column": price_column,
        "observation_count": int(len(finite_returns)),
        "diagnostic_status": "completed",
    }

    if len(finite_returns) < 50:
        result.update(
            {
                "diagnostic_status": "insufficient_observations",
                "diagnostic_message": "At least 50 finite log returns are required.",
            }
        )
        return result

    values = finite_returns.to_numpy(dtype=float)
    if not np.isfinite(values).all() or np.nanstd(values) <= 0:
        result.update(
            {
                "diagnostic_status": "undefined_returns",
                "diagnostic_message": "Finite returns with positive variance are required.",
            }
        )
        return result

    jb_statistic, jb_p_value, skewness, kurtosis = jarque_bera(values)
    excess_kurtosis = float(kurtosis - 3.0)

    result.update(
        {
            "mean_log_return": float(np.mean(values)),
            "log_return_std_dev": float(np.std(values, ddof=1)),
            "skewness": float(skewness),
            "kurtosis": float(kurtosis),
            "excess_kurtosis": excess_kurtosis,
            "jarque_bera_statistic": float(jb_statistic),
            "jarque_bera_p_value": float(jb_p_value),
        }
    )

    result.update(_run_ljung_box(values, ljung_box_lags, significance_level))
    result.update(_run_arch_lm(values, arch_lags, significance_level))
    result.update(_estimate_garch(values))

    result["autocorrelation_conclusion"] = _interpret_autocorrelation(
        result.get("minimum_ljung_box_p_value"),
        significance_level,
    )
    result["fat_tail_conclusion"] = _interpret_fat_tails(
        excess_kurtosis,
        float(jb_p_value),
        significance_level,
    )
    result["volatility_clustering_conclusion"] = _interpret_volatility_clustering(
        result.get("minimum_arch_lm_p_value"),
        result.get("garch_available"),
        result.get("garch_alpha1"),
        result.get("garch_beta1"),
        significance_level,
    )

    return result


def run_asset_stylised_fact_diagnostics(
    run_dir: Path | str,
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> list[dict[str, object]]:
    """Compute stylised-fact diagnostics separately for every traded asset.

    Each asset is screened with exactly the same tests, so a two-asset run
    yields two independent verdicts rather than one verdict for whichever asset
    is nominated primary. Rows carry ``asset`` and ``is_primary_asset`` so the
    report and the calibration objective can name the market they describe.

    Runs archived before the multi-asset extension have no per-asset artefact;
    those fall back to the single-asset ``step_timeseries.csv`` view and return
    one row, keeping pre-existing reports unchanged.
    """

    run_path = Path(run_dir).expanduser().resolve()
    returns_by_asset = build_asset_return_series(run_path, phase=phase)
    if not returns_by_asset:
        row = run_stylised_fact_diagnostics(
            run_path,
            phase=phase,
            price_column=price_column,
        )
        row["asset"] = ""
        row["is_primary_asset"] = True
        return [row]

    primary_asset = load_multi_asset_configuration(run_path).primary_asset
    # summary_metrics.csv records drawdown and volume for the primary asset
    # only, so they are recomputed here per asset. Without them the robustness
    # layer would fall back to the run-level column and report one market's
    # path statistics for the other.
    path_metrics = compute_asset_path_metrics(run_path, phase=phase)
    rows: list[dict[str, object]] = []
    for asset, returns in returns_by_asset.items():
        row = diagnose_return_series(
            asset_series_id(run_path.name, asset),
            returns,
            phase=phase,
            price_column=price_column,
        )
        row["run_id"] = run_path.name
        row["asset"] = asset
        row["is_primary_asset"] = asset == primary_asset
        row.update(path_metrics.get(asset, {}))
        rows.append(row)
    return rows


def build_stylised_fact_diagnostics(
    run_dirs: list[Path],
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> pd.DataFrame:
    """Run stylised-fact diagnostics for every discovered run."""

    rows = [
        run_stylised_fact_diagnostics(
            run_dir,
            phase=phase,
            price_column=price_column,
        )
        for run_dir in run_dirs
    ]
    return pd.DataFrame(rows)


def build_asset_stylised_fact_diagnostics(
    run_dirs: list[Path],
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> pd.DataFrame:
    """Run per-asset stylised-fact diagnostics for every discovered run."""

    rows: list[dict[str, object]] = []
    for run_dir in run_dirs:
        rows.extend(
            run_asset_stylised_fact_diagnostics(
                run_dir,
                phase=phase,
                price_column=price_column,
            )
        )
    return pd.DataFrame(rows)


def build_return_series_by_run(
    run_dirs: list[Path],
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> dict[str, pd.Series]:
    """Load finite log-return series for each run."""

    return {
        run_dir.name: prepare_return_series(run_dir, phase=phase, price_column=price_column)
        for run_dir in run_dirs
    }


def build_return_series_by_asset(
    run_dirs: list[Path],
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> dict[str, pd.Series]:
    """Load finite log-return series for each (run, asset) pair.

    Keys are composite series ids from :func:`asset_series_id`, so runs and
    assets share one flat namespace and the distribution figures can plot every
    market of every selected run side by side.
    """

    series: dict[str, pd.Series] = {}
    for run_dir in run_dirs:
        returns_by_asset = build_asset_return_series(run_dir, phase=phase)
        if not returns_by_asset:
            series[run_dir.name] = prepare_return_series(
                run_dir,
                phase=phase,
                price_column=price_column,
            )
            continue
        for asset, returns in returns_by_asset.items():
            series[asset_series_id(run_dir.name, asset)] = returns
    return series


def build_pairwise_ks_table(return_series_by_run: dict[str, pd.Series]) -> pd.DataFrame:
    """Compare return distributions using SciPy's two-sample K-S test."""

    rows: list[dict[str, object]] = []
    for run_id_a, run_id_b in combinations(sorted(return_series_by_run), 2):
        values_a = return_series_by_run[run_id_a].to_numpy(dtype=float)
        values_b = return_series_by_run[run_id_b].to_numpy(dtype=float)
        if len(values_a) == 0 or len(values_b) == 0:
            rows.append(
                {
                    "run_id_a": run_id_a,
                    "run_id_b": run_id_b,
                    "ks_statistic": np.nan,
                    "ks_p_value": np.nan,
                    "n_a": len(values_a),
                    "n_b": len(values_b),
                    "status": "insufficient_observations",
                }
            )
            continue

        test_result = stats.ks_2samp(values_a, values_b, alternative="two-sided", method="auto")
        rows.append(
            {
                "run_id_a": run_id_a,
                "run_id_b": run_id_b,
                "ks_statistic": float(test_result.statistic),
                "ks_p_value": float(test_result.pvalue),
                "n_a": len(values_a),
                "n_b": len(values_b),
                "status": "completed",
            }
        )
    return pd.DataFrame(rows)


def _run_ljung_box(
    returns: np.ndarray,
    lags: tuple[int, ...],
    significance_level: float,
) -> dict[str, object]:
    valid_lags = [lag for lag in lags if lag < len(returns)]
    if not valid_lags:
        return {
            "minimum_ljung_box_p_value": np.nan,
            "ljung_box_status": "insufficient_observations",
        }

    table = acorr_ljungbox(returns, lags=valid_lags, return_df=True)
    result: dict[str, object] = {"ljung_box_status": "completed"}
    p_values: list[float] = []
    for lag in valid_lags:
        statistic = float(table.loc[lag, "lb_stat"])
        p_value = float(table.loc[lag, "lb_pvalue"])
        result[f"ljung_box_lag_{lag}_statistic"] = statistic
        result[f"ljung_box_lag_{lag}_p_value"] = p_value
        p_values.append(p_value)

    result["minimum_ljung_box_p_value"] = float(np.nanmin(p_values))
    result["ljung_box_rejects_no_autocorrelation"] = (
        result["minimum_ljung_box_p_value"] < significance_level
    )
    return result


def _run_arch_lm(
    returns: np.ndarray,
    lags: tuple[int, ...],
    significance_level: float,
) -> dict[str, object]:
    valid_lags = [lag for lag in lags if lag < max(2, len(returns) // 3)]
    if not valid_lags:
        valid_lags = [min(10, max(1, len(returns) // 4))]

    result: dict[str, object] = {"arch_lm_status": "completed"}
    p_values: list[float] = []
    demeaned_returns = returns - np.mean(returns)
    for lag in valid_lags:
        lm_statistic, lm_p_value, f_statistic, f_p_value = het_arch(
            demeaned_returns,
            nlags=lag,
            ddof=0,
        )
        result[f"arch_lm_lag_{lag}_statistic"] = float(lm_statistic)
        result[f"arch_lm_lag_{lag}_p_value"] = float(lm_p_value)
        result[f"arch_lm_lag_{lag}_f_statistic"] = float(f_statistic)
        result[f"arch_lm_lag_{lag}_f_p_value"] = float(f_p_value)
        p_values.append(float(lm_p_value))

    result["minimum_arch_lm_p_value"] = float(np.nanmin(p_values))
    result["arch_lm_rejects_no_arch_effects"] = (
        result["minimum_arch_lm_p_value"] < significance_level
    )
    return result


def _estimate_garch(returns: np.ndarray) -> dict[str, object]:
    """Estimate a Student-t GARCH(1,1) model using the ``arch`` package."""

    try:
        # Scaling to percentage returns improves numerical conditioning without
        # changing alpha/beta persistence interpretation.
        scaled_returns = returns * 100.0
        model = arch_model(
            scaled_returns,
            mean="Constant",
            vol="GARCH",
            p=1,
            q=1,
            dist="StudentsT",
            rescale=False,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            warnings.filterwarnings("ignore", category=ConvergenceWarning)
            fitted = model.fit(update_freq=0, disp="off", show_warning=False)
        params = fitted.params
        alpha1 = float(params.get("alpha[1]", np.nan))
        beta1 = float(params.get("beta[1]", np.nan))
        return {
            "garch_available": True,
            "garch_source": "arch.arch_model",
            "garch_omega": float(params.get("omega", np.nan)),
            "garch_alpha1": alpha1,
            "garch_beta1": beta1,
            "garch_persistence": float(alpha1 + beta1),
            "garch_student_t_nu": float(params.get("nu", np.nan)),
            "garch_log_likelihood": float(fitted.loglikelihood),
            "garch_aic": float(fitted.aic),
            "garch_bic": float(fitted.bic),
            "garch_convergence_flag": int(fitted.convergence_flag),
        }
    # arch_model.fit() raises these for degenerate or non-converging return
    # series; anything else indicates a real bug and should propagate instead
    # of being reported as "GARCH unavailable".
    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:  # pragma: no cover - depends on optimiser state.
        return {
            "garch_available": False,
            "garch_source": "arch.arch_model",
            "garch_message": str(exc),
        }


def _interpret_autocorrelation(
    minimum_p_value: object,
    significance_level: float,
) -> str:
    if pd.isna(minimum_p_value):
        return "Autocorrelation evidence is unavailable"
    if float(minimum_p_value) > significance_level:
        return "Consistent with absence of autocorrelation"
    return "Evidence of return autocorrelation"


def _interpret_fat_tails(
    excess_kurtosis: float,
    jarque_bera_p_value: float,
    significance_level: float,
) -> str:
    if excess_kurtosis > 0 and jarque_bera_p_value < significance_level:
        return "Consistent with fat-tailed returns"
    if excess_kurtosis > 0:
        return "Positive excess kurtosis, but normality is not rejected"
    if jarque_bera_p_value < significance_level:
        return "Normality is rejected, but fat-tail evidence is mixed"
    return "Fat-tail evidence is weak or mixed"


def _interpret_volatility_clustering(
    minimum_arch_p_value: object,
    garch_available: object,
    alpha1: object,
    beta1: object,
    significance_level: float,
) -> str:
    arch_rejected = not pd.isna(minimum_arch_p_value) and float(minimum_arch_p_value) < significance_level
    garch_persistent = (
        bool(garch_available)
        and not pd.isna(alpha1)
        and not pd.isna(beta1)
        and float(alpha1) > 0
        and float(beta1) > 0
    )
    if arch_rejected and garch_persistent:
        return "Consistent with volatility clustering"
    if arch_rejected:
        return "ARCH evidence supports volatility clustering"
    if garch_persistent:
        return "GARCH persistence exists, but ARCH evidence is weak"
    return "Volatility-clustering evidence is weak"
