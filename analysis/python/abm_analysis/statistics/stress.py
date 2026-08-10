"""Crisis and stress-regime diagnostics for simulated and empirical series."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from abm_analysis.archive.benchmarks import BenchmarkSeries
from abm_analysis.archive.data import compute_log_returns, load_step_timeseries


DEFAULT_STRESS_ROLLING_WINDOW = 30
DEFAULT_STRESS_VOLATILITY_QUANTILE = 0.80
DEFAULT_STRESS_DRAWDOWN_THRESHOLD = 0.10


def annotate_stress_regimes(
    time_series: pd.DataFrame,
    *,
    price_column: str = "market_price",
    return_column: str = "computed_log_return",
    rolling_window: int = DEFAULT_STRESS_ROLLING_WINDOW,
    volatility_quantile: float = DEFAULT_STRESS_VOLATILITY_QUANTILE,
    drawdown_threshold: float = DEFAULT_STRESS_DRAWDOWN_THRESHOLD,
) -> pd.DataFrame:
    """Add rolling volatility, drawdown, and stress-regime flags.

    The default rule marks stress when rolling volatility is in the top quintile
    of the analysed series or drawdown reaches 10%. This is deliberately
    symmetric for simulated and empirical data so regime comparisons are
    methodologically consistent.
    """

    if price_column not in time_series.columns:
        raise KeyError(f"Price column is unavailable for stress diagnostics: {price_column}")

    result = time_series.copy().reset_index(drop=True)
    if "row_index" not in result.columns:
        result["row_index"] = np.arange(len(result))
    prices = pd.to_numeric(result[price_column], errors="coerce")
    if return_column in result.columns:
        returns = pd.to_numeric(result[return_column], errors="coerce")
    else:
        returns = compute_log_returns(prices)
    result["stress_log_return"] = returns

    min_periods = max(5, min(rolling_window, max(1, len(result) // 5)))
    result["rolling_volatility"] = returns.rolling(
        rolling_window,
        min_periods=min_periods,
    ).std()
    rolling_peak = prices.cummax()
    result["drawdown"] = (rolling_peak - prices) / rolling_peak.replace(0.0, np.nan)
    volatility_values = result["rolling_volatility"].replace([np.inf, -np.inf], np.nan).dropna()
    volatility_threshold = (
        float(volatility_values.quantile(volatility_quantile))
        if not volatility_values.empty
        else np.nan
    )
    result["stress_volatility_threshold"] = volatility_threshold
    volatility_stress = (
        result["rolling_volatility"] >= volatility_threshold
        if np.isfinite(volatility_threshold)
        else False
    )
    drawdown_stress = result["drawdown"] >= drawdown_threshold
    result["stress_regime"] = (volatility_stress | drawdown_stress).fillna(False)
    return result


def build_simulation_stress_diagnostics(
    experiment_dir: Path | str,
    run_ids: list[str],
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> pd.DataFrame:
    """Build normal-vs-stress diagnostics for selected simulation runs."""

    experiment_path = Path(experiment_dir).expanduser().resolve()
    rows: list[dict[str, object]] = []
    for run_id in run_ids:
        time_series = load_step_timeseries(experiment_path / run_id, price_column=price_column)
        time_series = _filter_phase(time_series, phase)
        annotated = annotate_stress_regimes(time_series, price_column=price_column)
        rows.extend(_stress_summary_rows(annotated, series_id=run_id, source_type="simulation"))
    return pd.DataFrame(rows)


def build_benchmark_stress_diagnostics(
    benchmarks: dict[str, BenchmarkSeries],
) -> pd.DataFrame:
    """Build normal-vs-stress diagnostics for empirical market benchmarks."""

    rows: list[dict[str, object]] = []
    for benchmark_id, benchmark in benchmarks.items():
        annotated = annotate_stress_regimes(
            benchmark.data,
            price_column="market_price",
            return_column="computed_log_return",
        )
        rows.extend(
            _stress_summary_rows(
                annotated,
                series_id=benchmark_id,
                source_type="benchmark",
                source_file=benchmark.source_file,
            )
        )
    return pd.DataFrame(rows)


def _stress_summary_rows(
    annotated: pd.DataFrame,
    *,
    series_id: str,
    source_type: str,
    source_file: str | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    regimes = [
        ("all", annotated),
        ("normal", annotated[~annotated["stress_regime"]]),
        ("stress", annotated[annotated["stress_regime"]]),
    ]
    stress_share = float(annotated["stress_regime"].mean()) if len(annotated) else np.nan
    for regime, subset in regimes:
        row: dict[str, object] = {
            "series_id": series_id,
            "source_type": source_type,
            "regime": regime,
            "observation_count": int(len(subset)),
            "stress_observation_share": stress_share,
        }
        if source_type == "simulation":
            row["run_id"] = series_id
        else:
            row["benchmark_id"] = series_id
        if source_file is not None:
            row["source_file"] = source_file
        row.update(_regime_metrics(subset))
        rows.append(row)
    return rows


def _regime_metrics(data: pd.DataFrame) -> dict[str, float]:
    returns = pd.to_numeric(data.get("stress_log_return"), errors="coerce").dropna()
    drawdown = pd.to_numeric(data.get("drawdown"), errors="coerce").dropna()
    result: dict[str, float] = {
        "mean_log_return": float(returns.mean()) if not returns.empty else np.nan,
        "log_return_std_dev": float(returns.std(ddof=1)) if len(returns) > 1 else np.nan,
        "min_log_return": float(returns.min()) if not returns.empty else np.nan,
        "max_abs_log_return": float(returns.abs().max()) if not returns.empty else np.nan,
        "max_drawdown": float(drawdown.max()) if not drawdown.empty else np.nan,
        "mean_rolling_volatility": _mean_column(data, "rolling_volatility"),
    }
    result["mean_traded_volume"] = _mean_column(data, "traded_volume")
    result["mean_bid_ask_spread"] = _mean_column(data, "bid_ask_spread")
    result["mean_executed_trades"] = _mean_column(data, "executed_trades")
    result["mean_cancelled_orders"] = _mean_column(data, "cancelled_orders")
    result["mean_expired_orders"] = _mean_column(data, "expired_orders")
    if {"bid_depth", "ask_depth"}.issubset(data.columns):
        bid_depth = pd.to_numeric(data["bid_depth"], errors="coerce").fillna(0.0)
        ask_depth = pd.to_numeric(data["ask_depth"], errors="coerce").fillna(0.0)
        total_depth = bid_depth + ask_depth
        imbalance = (bid_depth - ask_depth) / total_depth.replace(0.0, np.nan)
        result["mean_total_depth"] = float(total_depth.mean())
        result["mean_depth_imbalance"] = float(imbalance.mean())
    else:
        result["mean_total_depth"] = np.nan
        result["mean_depth_imbalance"] = np.nan
    if {"submitted_limit_orders", "submitted_market_orders"}.issubset(data.columns):
        limit_orders = pd.to_numeric(data["submitted_limit_orders"], errors="coerce").fillna(0.0)
        market_orders = pd.to_numeric(data["submitted_market_orders"], errors="coerce").fillna(0.0)
        submitted_total = (limit_orders + market_orders).replace(0.0, np.nan)
        result["mean_market_order_share"] = float((market_orders / submitted_total).mean())
    else:
        result["mean_market_order_share"] = np.nan
    return result


def _mean_column(data: pd.DataFrame, column: str) -> float:
    if column not in data.columns:
        return np.nan
    values = pd.to_numeric(data[column], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


def _filter_phase(time_series: pd.DataFrame, phase: str) -> pd.DataFrame:
    if phase.lower() == "all" or "phase" not in time_series.columns:
        return time_series
    filtered = time_series[time_series["phase"].astype(str).str.lower() == phase.lower()]
    return filtered if not filtered.empty else time_series
