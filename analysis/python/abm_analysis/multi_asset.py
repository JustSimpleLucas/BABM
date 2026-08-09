"""Per-asset and cross-asset analytics for multi-asset ABM runs.

The simulator writes one long-format row per (step, asset) to
``asset_timeseries.csv``. This module reshapes that artefact into the wide
per-asset panels the report figures consume, and derives the cross-asset
quantities that only exist once a second risky asset is present: rolling return
correlation, the relative price ratio, and the cross-sectional portfolio
composition of the agent population.

Every loader degrades gracefully on single-asset archives, and on archives
written before the multi-asset extension, so that reports for pre-existing runs
render exactly as they did before.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .archives import build_run_archive, resolve_artifact_path
from .timeseries import load_asset_timeseries

# Rolling window used for realised volatility and cross-asset correlation.
# Fifty steps matches the simulator's default ``covariance_window``, so the
# reported correlation is on the same footing as the covariance the agents
# themselves estimate when solving the Markowitz problem.
DEFAULT_ROLLING_WINDOW = 50

# Minimum observations required before a rolling statistic is reported. Short
# windows produce correlations that are numerically defined but statistically
# meaningless, so they are left missing rather than plotted.
MIN_ROLLING_OBSERVATIONS = 10


@dataclass(frozen=True)
class AssetConfiguration:
    """Resolved generating parameters for one configured asset."""

    name: str
    enabled: bool
    fundamental_process: str
    initial_price: float
    initial_stock: float
    price_tick_size: float
    fundamental_shock_std_dev: float
    fundamental_drift_per_step: float
    minimum_fundamental_value: float

    @property
    def process_label(self) -> str:
        """Return a human-readable name for the fundamental process."""

        return {
            "random_walk": "Arithmetic random walk",
            "gbm": "Geometric Brownian motion",
        }.get(self.fundamental_process, self.fundamental_process)

    @property
    def parameter_units(self) -> str:
        """Return the units of the drift and shock parameters.

        The units differ by process, and conflating them is the most likely
        configuration error, so the report always states them explicitly.
        """

        if self.fundamental_process == "gbm":
            return "per-step log return"
        return "price units"


@dataclass(frozen=True)
class MultiAssetConfiguration:
    """Asset-level configuration recovered from a run's ``config.json``."""

    primary_asset: str = ""
    fundamental_correlation: float | None = None
    covariance_window: int | None = None
    assets: tuple[AssetConfiguration, ...] = field(default_factory=tuple)
    disabled_assets: tuple[AssetConfiguration, ...] = field(default_factory=tuple)

    @property
    def is_multi_asset(self) -> bool:
        """Return ``True`` when more than one asset actually traded."""

        return len(self.assets) > 1

    @property
    def has_configuration(self) -> bool:
        """Return ``True`` when asset definitions were recovered at all."""

        return bool(self.assets or self.disabled_assets)


def _coerce_float(value: object, default: float = float("nan")) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _parse_asset_definition(entry: dict, *, enabled_default: bool) -> AssetConfiguration:
    return AssetConfiguration(
        name=str(entry.get("name", "")),
        enabled=bool(entry.get("enabled", enabled_default)),
        # Archives written before per-asset processes existed had exactly one
        # process, the arithmetic random walk, so that is the correct default.
        fundamental_process=str(entry.get("fundamental_process", "random_walk")),
        initial_price=_coerce_float(entry.get("initial_price")),
        initial_stock=_coerce_float(entry.get("initial_stock")),
        price_tick_size=_coerce_float(entry.get("price_tick_size")),
        fundamental_shock_std_dev=_coerce_float(entry.get("fundamental_shock_std_dev")),
        fundamental_drift_per_step=_coerce_float(entry.get("fundamental_drift_per_step")),
        minimum_fundamental_value=_coerce_float(entry.get("minimum_fundamental_value")),
    )


def load_multi_asset_configuration(run_dir: Path | str) -> MultiAssetConfiguration:
    """Read the asset block from a run's ``config.json``.

    Returns an empty configuration when the archive has no ``config.json`` or
    the file predates the multi-asset schema, so callers can always call this
    without first checking the archive vintage.
    """

    run_path = Path(run_dir)
    config_path = resolve_artifact_path(run_path, "config.json")
    if config_path is None:
        return MultiAssetConfiguration()

    try:
        with config_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return MultiAssetConfiguration()

    assets_block = payload.get("assets")
    if not isinstance(assets_block, dict):
        return MultiAssetConfiguration()

    definitions = assets_block.get("definitions")
    disabled = assets_block.get("disabled_definitions")
    correlation = assets_block.get("fundamental_correlation")
    covariance_window = assets_block.get("covariance_window")

    return MultiAssetConfiguration(
        primary_asset=str(assets_block.get("primary", "")),
        fundamental_correlation=(
            _coerce_float(correlation) if correlation is not None else None
        ),
        covariance_window=(
            int(covariance_window) if isinstance(covariance_window, (int, float)) else None
        ),
        assets=tuple(
            _parse_asset_definition(entry, enabled_default=True)
            for entry in (definitions if isinstance(definitions, list) else [])
            if isinstance(entry, dict)
        ),
        disabled_assets=tuple(
            _parse_asset_definition(entry, enabled_default=False)
            for entry in (disabled if isinstance(disabled, list) else [])
            if isinstance(entry, dict)
        ),
    )


def has_asset_timeseries(run_dir: Path | str) -> bool:
    """Return ``True`` when the archive carries a per-asset time series."""

    try:
        archive = build_run_archive(run_dir)
    except (FileNotFoundError, ValueError):
        return False
    return archive.asset_timeseries_csv is not None


def list_assets(run_dir: Path | str) -> list[str]:
    """Return the traded asset names for a run, in first-appearance order.

    First-appearance order in the long-format artefact is the simulator's
    declared asset order, which keeps Asset A ahead of Asset B in every figure
    legend rather than sorting them alphabetically.
    """

    if not has_asset_timeseries(run_dir):
        return []
    asset_data = load_asset_timeseries(run_dir)
    if "asset" not in asset_data.columns:
        return []
    return list(dict.fromkeys(asset_data["asset"].dropna().astype(str)))


def load_asset_panel(
    run_dir: Path | str,
    column: str,
    *,
    phase: str | None = "simulation",
) -> pd.DataFrame:
    """Reshape one long-format column into a wide per-asset panel.

    :param run_dir: Archived run directory.
    :param column: Column of ``asset_timeseries.csv`` to pivot.
    :param phase: Run phase to keep, or ``None`` for every phase.
    :returns: Frame indexed by ``simulation_step`` with one column per asset,
        ordered as the assets were declared. Empty when the run has no
        per-asset artefact or the column is absent.
    """

    if not has_asset_timeseries(run_dir):
        return pd.DataFrame()

    asset_data = load_asset_timeseries(run_dir)
    if column not in asset_data.columns or "asset" not in asset_data.columns:
        return pd.DataFrame()

    if phase is not None and "phase" in asset_data.columns:
        phase_rows = asset_data[asset_data["phase"].astype(str).str.lower() == phase.lower()]
        if not phase_rows.empty:
            asset_data = phase_rows

    index_column = "simulation_step" if "simulation_step" in asset_data.columns else "row_index"
    asset_data = asset_data.copy()
    asset_data[column] = pd.to_numeric(asset_data[column], errors="coerce")
    asset_data[index_column] = pd.to_numeric(asset_data[index_column], errors="coerce")
    asset_data = asset_data.dropna(subset=[index_column])

    panel = asset_data.pivot_table(
        index=index_column,
        columns="asset",
        values=column,
        aggfunc="last",
    )
    ordered = [name for name in list_assets(run_dir) if name in panel.columns]
    if ordered:
        panel = panel[ordered]
    panel.index.name = index_column
    panel.columns.name = None
    return panel.sort_index()


def compute_asset_log_returns(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> pd.DataFrame:
    """Return per-asset log returns as reported by the simulator.

    The simulator already records ``log_return`` per (step, asset), so it is
    used directly rather than recomputed from prices: it is the return actually
    realised by the matching engine, including steps where no trade occurred.
    """

    return load_asset_panel(run_dir, "log_return", phase=phase)


def asset_series_id(run_id: str, asset: str) -> str:
    """Return the identifier naming one run's series for a single asset.

    Report figures, diagnostics tables, and calibration scores are all keyed by
    series rather than by run, so that every asset of a multi-asset run is a
    first-class series instead of an appendix to the primary one. The separator
    is chosen so the composite id survives being used as a CSV cell, a plot
    legend entry, and a dictionary key.
    """

    return f"{run_id} · {asset}"


def build_asset_return_series(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> dict[str, pd.Series]:
    """Return finite log returns for each asset, keyed by asset name.

    Returns an empty mapping for archives with no per-asset artefact, so
    callers can fall back to the single-asset ``step_timeseries.csv`` view.
    """

    returns = compute_asset_log_returns(run_dir, phase=phase)
    if returns.empty:
        return {}

    series_by_asset: dict[str, pd.Series] = {}
    for asset in returns.columns:
        values = pd.to_numeric(returns[asset], errors="coerce")
        series_by_asset[str(asset)] = (
            values[np.isfinite(values)].reset_index(drop=True).rename(str(asset))
        )
    return series_by_asset


def compute_asset_path_metrics(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> dict[str, dict[str, float]]:
    """Return per-asset maximum drawdown and total traded volume.

    These are the two run-level summary metrics the robustness layer consumes
    that ``summary_metrics.csv`` only records for the primary asset. Recomputing
    them per asset is what stops one market's drawdown being reported as the
    other's. Drawdown is measured from each asset's own starting price, so a
    100-unit and a 40-unit asset are directly comparable.
    """

    prices = load_asset_panel(run_dir, "market_price", phase=phase)
    volume = load_asset_panel(run_dir, "traded_volume", phase=phase)
    if prices.empty and volume.empty:
        return {}

    assets = list(dict.fromkeys([*prices.columns, *volume.columns]))
    metrics: dict[str, dict[str, float]] = {}
    for asset in assets:
        asset_metrics: dict[str, float] = {}
        if asset in prices.columns:
            values = pd.to_numeric(prices[asset], errors="coerce")
            positive = values.where(values > 0)
            running_peak = positive.cummax()
            drawdown = (running_peak - positive) / running_peak
            asset_metrics["max_drawdown"] = float(drawdown.max(skipna=True))
        if asset in volume.columns:
            asset_metrics["total_traded_volume"] = float(
                pd.to_numeric(volume[asset], errors="coerce").sum(skipna=True)
            )
        if asset_metrics:
            metrics[str(asset)] = asset_metrics
    return metrics


def prepare_asset_return_series(
    run_dir: Path | str,
    asset: str,
    *,
    phase: str | None = "simulation",
) -> pd.Series:
    """Return finite log returns for one named asset.

    :raises KeyError: when the run has no series for ``asset``.
    """

    series_by_asset = build_asset_return_series(run_dir, phase=phase)
    if asset not in series_by_asset:
        available = ", ".join(sorted(series_by_asset)) or "none"
        raise KeyError(f"Run has no return series for asset '{asset}'. Available: {available}")
    return series_by_asset[asset]


def compute_realised_volatility(
    run_dir: Path | str,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    phase: str | None = "simulation",
) -> pd.DataFrame:
    """Return rolling realised volatility per asset.

    Realised volatility is the rolling standard deviation of one-period log
    returns, the standard estimator for stylised-fact work because it measures
    dispersion in return space rather than in price-level space.
    """

    returns = compute_asset_log_returns(run_dir, phase=phase)
    if returns.empty:
        return returns
    minimum_periods = min(window, max(MIN_ROLLING_OBSERVATIONS, window // 2))
    return returns.rolling(window=window, min_periods=minimum_periods).std()


def compute_rolling_correlation(
    run_dir: Path | str,
    asset_a: str | None = None,
    asset_b: str | None = None,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    phase: str | None = "simulation",
) -> pd.Series:
    """Return the rolling correlation between two assets' log returns.

    :param asset_a: First asset; defaults to the first declared asset.
    :param asset_b: Second asset; defaults to the second declared asset.
    :returns: Correlation series indexed by simulation step, empty when the run
        has fewer than two assets.

    Realised return correlation is distinct from the configured ``rho_AB`` on
    the fundamentals: prices are set by order flow, so trading behaviour can
    amplify or dampen the underlying fundamental co-movement. Comparing the two
    is the point of the cross-asset panel.
    """

    returns = compute_asset_log_returns(run_dir, phase=phase)
    if returns.empty or returns.shape[1] < 2:
        return pd.Series(dtype="float64")

    columns = list(returns.columns)
    first = asset_a if asset_a in columns else columns[0]
    second = asset_b if asset_b in columns else columns[1]
    if first == second:
        return pd.Series(dtype="float64")

    minimum_periods = min(window, max(MIN_ROLLING_OBSERVATIONS, window // 2))
    correlation = (
        returns[first]
        .rolling(window=window, min_periods=minimum_periods)
        .corr(returns[second])
    )
    correlation.name = f"corr({first}, {second})"
    # A flat price path gives a zero-variance window, where the correlation is
    # undefined rather than zero; pandas surfaces that as +/-inf.
    return correlation.replace([np.inf, -np.inf], np.nan)


def compute_price_ratio(
    run_dir: Path | str,
    asset_a: str | None = None,
    asset_b: str | None = None,
    *,
    phase: str | None = "simulation",
) -> pd.Series:
    """Return the relative price ratio ``p_A / p_B``.

    The ratio is the cleanest single summary of relative valuation between two
    assets: a trend indicates one asset persistently outperforming, while
    mean reversion indicates cross-asset arbitrage by the agent population.
    """

    prices = load_asset_panel(run_dir, "market_price", phase=phase)
    if prices.empty or prices.shape[1] < 2:
        return pd.Series(dtype="float64")

    columns = list(prices.columns)
    first = asset_a if asset_a in columns else columns[0]
    second = asset_b if asset_b in columns else columns[1]
    if first == second:
        return pd.Series(dtype="float64")

    numerator = pd.to_numeric(prices[first], errors="coerce")
    denominator = pd.to_numeric(prices[second], errors="coerce")
    ratio = numerator / denominator.where(denominator > 0)
    ratio.name = f"{first} / {second}"
    return ratio.replace([np.inf, -np.inf], np.nan)


def compute_portfolio_composition(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> pd.DataFrame:
    """Return mean agent portfolio weights in each asset and in cash.

    The simulator records the cross-sectional mean weight per asset directly,
    averaged over agents with strictly positive wealth. Because the mean is a
    linear operator, the mean cash weight is recovered exactly as
    ``1 - sum_j mean_weight_j`` and needs no separate column.

    :returns: Frame indexed by simulation step with one column per asset plus a
        trailing ``cash`` column. Empty when the run predates the portfolio
        weight columns.
    """

    weights = load_asset_panel(run_dir, "mean_agent_portfolio_weight", phase=phase)
    if weights.empty:
        return weights

    composition = weights.copy()
    composition["cash"] = 1.0 - composition.sum(axis=1)
    return composition
