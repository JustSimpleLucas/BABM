"""Time-series loading and return preparation for ABM archives."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from abm_analysis.archive.archives import build_run_archive


PRICE_COLUMN_CANDIDATES = [
    "market_price",
    "close",
    "Close",
    "closing_price",
    "ClosingPrice",
    "Adj.Close",
    "adj_close",
    "price",
    "Price",
]


def read_csv_if_exists(path: Path | None) -> pd.DataFrame:
    """Read a CSV if present, otherwise return an empty frame."""

    if path is None or not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def select_price_column(market_data: pd.DataFrame, requested_price_column: str | None) -> str:
    """Resolve the price column used for return diagnostics."""

    if requested_price_column:
        if requested_price_column not in market_data.columns:
            available = ", ".join(map(str, market_data.columns))
            raise KeyError(
                f"Requested price column '{requested_price_column}' was not found. "
                f"Available columns: {available}"
            )
        return requested_price_column

    for candidate in PRICE_COLUMN_CANDIDATES:
        if candidate in market_data.columns:
            return candidate
    raise KeyError(f"No recognised price column found. Expected one of {PRICE_COLUMN_CANDIDATES}")


def load_step_timeseries(run_dir: Path | str, price_column: str = "market_price") -> pd.DataFrame:
    """Load one run's time series and add computed log-return columns.

    Report generation reads the same ``step_timeseries.csv`` once per figure,
    so parsed frames are memoised per file generation (path, mtime, size).
    Callers receive an independent copy and may mutate it freely.
    """

    archive = build_run_archive(run_dir)
    file_stat = archive.step_timeseries_csv.stat()
    market_data = _load_step_timeseries_cached(
        str(archive.step_timeseries_csv),
        file_stat.st_mtime_ns,
        file_stat.st_size,
        price_column,
    ).copy()
    market_data["run_id"] = archive.run_id
    return market_data


def load_asset_timeseries(run_dir: Path | str, asset: str | None = None) -> pd.DataFrame:
    """Load one run's long-format per-asset time series.

    The frame holds one row per (row_index, asset). When ``asset`` is given,
    only that asset's rows are returned. Raises ``FileNotFoundError`` when the
    archive has no ``asset_timeseries.csv`` (runs created before the
    multi-asset extension).
    """

    archive = build_run_archive(run_dir)
    if archive.asset_timeseries_csv is None:
        raise FileNotFoundError(
            f"Run archive has no asset_timeseries.csv: {archive.run_dir}"
        )

    asset_data = pd.read_csv(archive.asset_timeseries_csv)
    if "row_index" in asset_data.columns:
        asset_data = asset_data.sort_values("row_index").reset_index(drop=True)
    if asset is not None:
        available_assets = sorted(asset_data["asset"].dropna().unique())
        if asset not in available_assets:
            available_text = ", ".join(map(str, available_assets))
            raise KeyError(
                f"Asset '{asset}' not present in asset_timeseries.csv. "
                f"Available assets: {available_text}"
            )
        asset_data = asset_data[asset_data["asset"] == asset].reset_index(drop=True)
    asset_data["run_id"] = archive.run_id
    return asset_data


@lru_cache(maxsize=32)
def _load_step_timeseries_cached(
    csv_path: str,
    file_mtime_ns: int,
    file_size: int,
    price_column: str | None,
) -> pd.DataFrame:
    """Parse and enrich one step-timeseries CSV for the current file generation.

    ``file_mtime_ns`` and ``file_size`` are part of the cache key so a re-run
    simulation invalidates the memoised frame automatically. The returned frame
    is shared across callers and must never be mutated here; the public loader
    hands out defensive copies.
    """

    market_data = pd.read_csv(csv_path)
    if "row_index" in market_data.columns:
        market_data = market_data.sort_values("row_index").reset_index(drop=True)

    resolved_price_column = select_price_column(market_data, price_column)
    market_data["computed_log_return"] = compute_log_returns(market_data[resolved_price_column])
    if "fundamental_price" in market_data.columns:
        market_data["computed_fundamental_log_return"] = compute_log_returns(
            market_data["fundamental_price"]
        )
    return market_data


def prepare_return_series(
    run_dir: Path | str,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> pd.Series:
    """Return finite log returns for one run and analysis phase."""

    time_series = load_step_timeseries(run_dir, price_column=price_column)
    if phase.lower() != "all" and "phase" in time_series.columns:
        time_series = time_series[time_series["phase"] == phase]

    returns = pd.to_numeric(time_series["computed_log_return"], errors="coerce")
    return returns[np.isfinite(returns)].reset_index(drop=True)


def compute_log_returns(price_series: Iterable[float]) -> pd.Series:
    """Compute ``log(P_t / P_{t-1})`` and return missing values for invalid prices."""

    prices = pd.to_numeric(pd.Series(price_series), errors="coerce")
    previous_prices = prices.shift(1)
    valid = (
        np.isfinite(prices)
        & np.isfinite(previous_prices)
        & (prices > 0)
        & (previous_prices > 0)
    )
    returns = pd.Series(np.nan, index=prices.index, dtype="float64")
    returns.loc[valid] = np.log(prices.loc[valid] / previous_prices.loc[valid])
    return returns
