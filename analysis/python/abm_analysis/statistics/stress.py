"""Crisis and stress-regime diagnostics for simulated and empirical series."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from abm_analysis.archive.benchmarks import BenchmarkSeries
from abm_analysis.archive.data import compute_log_returns, load_step_timeseries
from abm_analysis.archive.timeseries import load_asset_timeseries, step_axis_column
from abm_analysis.statistics.multi_asset import has_asset_timeseries, list_assets


DEFAULT_STRESS_ROLLING_WINDOW = 30
DEFAULT_STRESS_VOLATILITY_QUANTILE = 0.80
DEFAULT_STRESS_DRAWDOWN_THRESHOLD = 0.10


@dataclass(frozen=True)
class StressFrame:
    """One traded asset's series, annotated with the stress diagnostics.

    ``step_column`` names the column that keys the rows to the chart's x-axis.
    It is carried with the frame because it is not always the same: per-asset
    artefacts are keyed by ``simulation_step``, while a single-asset step series
    that includes warm-up rows has to fall back to ``row_index`` — the simulator
    leaves ``simulation_step`` blank before the simulation phase begins.
    """

    asset: str
    step_column: str
    data: pd.DataFrame


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


def compute_log_mispricing(prices: pd.Series, fundamentals: pd.Series) -> pd.Series:
    """Return ``ln(price / fundamental)``, the scale-free gap to fundamental value.

    A log ratio rather than a difference, so a market priced at 50 against a
    fundamental of 100 reads the same as one priced at 5 against 10, and equal
    proportional over- and under-valuation sit symmetrically about zero. The gap
    is the quantity behind the excess-volatility argument of Shiller (1981):
    when prices wander persistently from the value the fundamentals justify,
    something other than news is moving them.

    A non-positive or missing price or fundamental yields ``NaN`` rather than an
    exception, because a crashed market can legitimately print a zero price.
    """

    price = pd.to_numeric(prices, errors="coerce")
    fundamental = pd.to_numeric(fundamentals, errors="coerce")
    valid = np.isfinite(price) & np.isfinite(fundamental) & (price > 0) & (fundamental > 0)
    mispricing = pd.Series(np.nan, index=price.index, dtype="float64")
    mispricing.loc[valid] = np.log(price.loc[valid] / fundamental.loc[valid])
    return mispricing


def find_stress_intervals(
    stress_flags: pd.Series | np.ndarray,
    step_values: pd.Series | np.ndarray,
) -> list[tuple[float, float]]:
    """Return the first and last step of every unbroken run of stress rows.

    The runs are found on the full-resolution flag. A chart thins a long series
    to a point cap before drawing it, and thinning the *flag* instead would drop
    any stress window shorter than the stride — which are precisely the brief,
    violent episodes a crisis chart exists to show.

    Args:
        stress_flags: One boolean per row, true where the row is in stress.
        step_values: The step each row belongs to, in the same order.

    Returns:
        ``(first_step, last_step)`` pairs, both ends inclusive. A single stressed
        row yields a pair whose two ends are equal.
    """

    flags = pd.Series(stress_flags).fillna(False).to_numpy(dtype=bool)
    steps = pd.to_numeric(pd.Series(step_values), errors="coerce").to_numpy(dtype=float)
    if flags.size != steps.size:
        raise ValueError(
            f"Stress flags ({flags.size}) and step values ({steps.size}) must be the same length."
        )

    # Pad both ends with "not stressed" so a run touching either edge still has a
    # rising and a falling edge; the changes then alternate start, stop, start...
    padded = np.concatenate(([False], flags, [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    starts, stops = changes[0::2], changes[1::2] - 1
    return [
        (float(steps[first]), float(steps[last]))
        for first, last in zip(starts, stops, strict=True)
        if np.isfinite(steps[first]) and np.isfinite(steps[last])
    ]


def build_step_stress_frame(
    time_series: pd.DataFrame,
    *,
    asset: str,
    price_column: str = "market_price",
) -> StressFrame:
    """Annotate a single-asset step series with stress diagnostics.

    Takes the frame ``load_step_timeseries`` produced, already restricted to the
    analysed phase, so the volatility quantile that defines stress is taken over
    exactly the rows the reader is looking at.
    """

    annotated = annotate_stress_regimes(time_series, price_column=price_column)
    annotated["log_mispricing"] = compute_log_mispricing(
        annotated[price_column],
        annotated["fundamental_price"]
        if "fundamental_price" in annotated.columns
        else pd.Series(np.nan, index=annotated.index),
    )
    return StressFrame(asset=asset, step_column=step_axis_column(annotated), data=annotated)


def build_asset_stress_frames(
    run_dir: Path | str,
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> dict[str, StressFrame]:
    """Annotate every traded asset of a multi-asset run with stress diagnostics.

    ``asset_timeseries.csv`` is read once and split by asset, rather than pivoted
    column by column, because each stress frame carries a dozen columns (volume,
    spread, depth, order mix) for the normal-versus-stress comparison.

    Rows without a ``simulation_step`` are dropped, which is the same restriction
    ``load_asset_panel`` applies: the simulator leaves the step blank on initial
    and warm-up rows, so per-asset series always cover the simulation phase. The
    per-asset return column is the simulator's own ``log_return``, matching the
    per-asset diagnostics, so the returns behind the shading are the returns
    behind the stylised-fact verdicts.

    Returns:
        Stress frames keyed by asset name in declared order, or an empty mapping
        for a run with no per-asset artefact.
    """

    if not has_asset_timeseries(run_dir):
        return {}
    asset_data = load_asset_timeseries(run_dir)
    if "asset" not in asset_data.columns:
        return {}

    if phase.lower() != "all" and "phase" in asset_data.columns:
        phase_rows = asset_data[asset_data["phase"].astype(str).str.lower() == phase.lower()]
        if not phase_rows.empty:
            asset_data = phase_rows

    step_column = "simulation_step" if "simulation_step" in asset_data.columns else "row_index"
    asset_data = asset_data.copy()
    asset_data[step_column] = pd.to_numeric(asset_data[step_column], errors="coerce")
    asset_data = asset_data.dropna(subset=[step_column])

    frames: dict[str, StressFrame] = {}
    for asset in list_assets(run_dir):
        rows = (
            asset_data[asset_data["asset"].astype(str) == asset]
            .drop_duplicates(subset=step_column, keep="last")
            .sort_values(step_column)
            .reset_index(drop=True)
        )
        if rows.empty:
            continue
        resolved_price_column = price_column if price_column in rows.columns else "market_price"
        annotated = annotate_stress_regimes(
            rows,
            price_column=resolved_price_column,
            return_column="log_return",
        )
        annotated["log_mispricing"] = compute_log_mispricing(
            annotated[resolved_price_column],
            annotated["fundamental_price"]
            if "fundamental_price" in annotated.columns
            else pd.Series(np.nan, index=annotated.index),
        )
        frames[asset] = StressFrame(asset=asset, step_column=step_column, data=annotated)
    return frames


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
        rows.extend(summarise_stress_regimes(annotated, series_id=run_id, source_type="simulation"))
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
            summarise_stress_regimes(
                annotated,
                series_id=benchmark_id,
                source_type="benchmark",
                source_file=benchmark.source_file,
            )
        )
    return pd.DataFrame(rows)


def summarise_stress_regimes(
    annotated: pd.DataFrame,
    *,
    series_id: str,
    source_type: str,
    source_file: str | None = None,
) -> list[dict[str, object]]:
    """Summarise an annotated series over all rows, normal rows, and stress rows.

    Public so the dashboard's normal-versus-stress table and the CSV builders
    above are one implementation: a number read on the page and the same number
    in an exported table cannot disagree.
    """

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
